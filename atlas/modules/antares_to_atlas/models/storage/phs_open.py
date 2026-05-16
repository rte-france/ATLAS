"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import TYPE_CHECKING, cast

import numpy as np
from antares.craft import Frequency, MCIndLinksDataType
from antares.craft.model.st_storage import STStorage, STStorageGroup
from antares.craft.model.study import Study
from loguru import logger
from pendulum import duration

from atlas.enums import StorageType
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.models.hydro.inflows import _load_inflows_from_csv, _match_inflows_to_scenarios
from atlas.modules.antares_to_atlas.models.storage._helpers import get_minimum_soc
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.modules.antares_to_atlas.utils import get_binding_constraint_for_phs, get_portfolio
from atlas.objects.equipment.hydro import Hydro
from atlas.objects.equipment.storage import Storage

if TYPE_CHECKING:
    from antares.craft.model.area import Area


def convert_phs_open_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Convert open-loop PHS units from Antares st_storage (PSP_open group) to Atlas.

    Each PSP_open STS is split into two components:
    - A closed PHS Storage equipment (the symmetric pump/turbine part)
    - An open part added to the corresponding hydro equipment (power, energy, inflows)

    The split is derived from the per-timestep difference between withdrawal and injection
    nominal capacity timeseries.
    """
    logger.info("Converting open-loop PHS units")

    areas = study.get_areas()
    phs_open_list: list[Storage] = []

    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        if area_name.lower() == "fr":
            continue

        area = areas[area_name]

        for storage in area.get_st_storages().values():
            if storage.properties.group != STStorageGroup.PSP_OPEN.value:
                continue

            logger.debug(f"Processing open PHS {storage.id} for area {area.id}")

            phs = _create_open_phs(
                storage=storage,
                area=area,
                study=study,
                parameters=parameters,
                atlas_dataset=atlas_dataset,
            )

            if phs is not None:
                phs_open_list.append(phs)

    atlas_dataset.storage.add(phs_open_list)
    return atlas_dataset


def _create_open_phs(
    storage: STStorage,
    area: "Area",
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> Storage | None:
    """Create open-loop PHS Storage and update the corresponding hydro equipment.

    The open STS capacity is split into:
    - Closed part (symmetric injection/withdrawal) → PHS Storage equipment
    - Open part (excess withdrawal over injection) → added to hydro MaximumPower and MaximumEnergy
    """
    props = storage.properties

    if props.reservoir_capacity == 0.0:
        logger.debug(f"Skipping open PHS {storage.id} in {area.id}: zero reservoir capacity")
        return None

    mapping_mc_ts = study.get_output(parameters.output_name).get_st_storage_inflows_numbers(area.id, storage.id)
    scenario = mapping_mc_ts.get(parameters.scenario)

    # Injection and withdrawal power arrays for the selected scenario
    if scenario is not None:
        try:
            inj_arr = (
                np.asarray(storage.get_pmax_injection()[scenario - 1], dtype=float)
                * props.injection_nominal_capacity
            )
            wdr_arr = (
                np.asarray(storage.get_pmax_withdrawal()[scenario - 1], dtype=float)
                * props.withdrawal_nominal_capacity
            )
        except Exception as e:
            logger.warning(f"Cannot get pmax timeseries for {storage.id}: {e}, using nominal capacity")
            inj_arr = np.full(8760, props.injection_nominal_capacity)
            wdr_arr = np.full(8760, props.withdrawal_nominal_capacity)
    else:
        logger.warning(f"Scenario {parameters.scenario} not in mapping for {storage.id}, using nominal capacity")
        inj_arr = np.full(8760, float(props.injection_nominal_capacity))
        wdr_arr = np.full(8760, float(props.withdrawal_nominal_capacity))

    # closed_delta = excess withdrawal that goes to hydro (open part)
    closed_delta_arr = np.maximum(0.0, wdr_arr - inj_arr)
    # closed_ratio = fraction of withdrawal capacity that is "open" (goes to hydro)
    closed_ratio_arr = np.where(wdr_arr > 0.0, closed_delta_arr / wdr_arr, 0.0)

    # PHS MaximumPower = symmetric part (min of injection and withdrawal)
    max_power_arr = np.minimum(inj_arr, wdr_arr)

    minimum_soc_ts = get_minimum_soc(storage=storage, scenario=scenario, parameters=parameters)

    # --- Update hydro equipment with the open part ---
    hydro = cast(Hydro, atlas_dataset.get("hydro", f"{area.id}_hydro"))
    if hydro is not None:
        delta_ts = Timeseries.from_values(parameters.start_date, frequency="1h", values=closed_delta_arr)
        hydro.maximum_power = hydro.maximum_power + delta_ts if hydro.maximum_power is not None else delta_ts

        additional_energy_arr = np.round(props.reservoir_capacity * closed_ratio_arr)
        additional_energy_ts = Timeseries.from_values(
            parameters.start_date, frequency="1h", values=additional_energy_arr
        )
        hydro.maximum_energy = (
            hydro.maximum_energy + additional_energy_ts if hydro.maximum_energy is not None else additional_energy_ts
        )

        _update_hydro_inflows_from_phs_csv(area.id, storage, hydro, mapping_mc_ts, parameters)
    else:
        logger.debug(f"No hydro '{area.id}_hydro' found; open part of PHS will not be added to hydro.")
        additional_energy_arr = np.zeros_like(closed_ratio_arr)

    phs_max_energy_arr = np.round(props.reservoir_capacity - additional_energy_arr)

    phs = Storage(
        name=f"{area.id}_phs_open",
        node=atlas_dataset.get("node", area.id),
        portfolio=get_portfolio(atlas_dataset, parameters, area.id),
        storage_type=StorageType.PUMPED_HYDRAULIC_STORAGE,
        maximum_power=Timeseries.from_values(parameters.start_date, frequency="1h", values=max_power_arr),
        minimum_power=Timeseries.from_values(parameters.start_date, frequency="1h", values=-inj_arr),
        maximum_energy=Timeseries.from_values(
            parameters.start_date, frequency="1h", values=phs_max_energy_arr.tolist()
        ),
        minimum_state_of_charge=minimum_soc_ts,
        charge_efficiency=props.efficiency,
        discharge_efficiency=1.0,
        storage_initial_level=parameters.storage.phs_initial_level,
        transition_duration=duration(hours=0),
    )

    logger.debug(f"Created open PHS {storage.id} for area {area.id}")
    return phs


def _update_hydro_inflows_from_phs_csv(
    area_id: str,
    storage: STStorage,
    hydro: Hydro,
    mapping_mc_ts: dict[int, int],
    parameters: AntaresToAtlasParameters,
) -> None:
    """Add PHS inflow profiles (from {area_id}_phs.csv) to the hydro equipment inflows.

    Matches each water-value scenario to the closest CSV profile by total energy,
    using the STS natural inflows as the reference modulation series.
    Only the first matched scenario is added to hydro.inflows (same convention as
    add_inflows_from_csv for regular hydro).
    """
    if parameters.hydro.path_inflows is None:
        logger.debug(f"path_inflows not configured, skipping PHS inflows for {area_id}")
        return

    if parameters.hydro.water_value_scenarios == "all":
        logger.warning(f"'all' water value scenarios not supported for PHS inflows ({area_id}), skipping")
        return

    scenarios: list[str] = parameters.hydro.water_value_scenarios
    if not scenarios:
        return

    csv_path = parameters.hydro.path_inflows / f"{area_id}_phs.csv"
    if not csv_path.exists():
        logger.debug(f"No PHS inflow CSV at {csv_path}, skipping inflows update")
        return

    inflows_csv = _load_inflows_from_csv(csv_path, parameters)
    sts_inflows_df = storage.get_storage_inflows()

    if len(inflows_csv) < len(scenarios):
        logger.warning(
            f"There are {len(scenarios)} water value scenarios but only "
            f"{len(inflows_csv)} PHS inflow profiles for {area_id}. Results may be invalid."
        )

    inflows_dictionary = _match_inflows_to_scenarios(
        scenarios=scenarios,
        inflows_csv_timeseries=inflows_csv,
        modulation_df=sts_inflows_df,
        mapping_mc_ts=mapping_mc_ts,
        parameters=parameters,
    )

    if not inflows_dictionary:
        return

    first_inflows = next(iter(inflows_dictionary.values()))
    hydro.inflows = hydro.inflows + first_inflows if hydro.inflows is not None else first_inflows


def convert_phs_open_fr(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Convert open-loop PHS for France (special case).

    France's open PHS uses the fr_x_open_turb link directly and does not
    split into a hydro component.
    """
    if "fr" not in parameters.market_areas:
        return atlas_dataset

    logger.info("Converting FR open-loop PHS")

    areas = study.get_areas()
    links = study.get_links()

    if "fr" not in areas:
        return atlas_dataset

    link = links.get("fr_x_open_turb", None)
    if not link:
        logger.debug("No open turb link 'fr_x_open_turb' found for FR")
        return atlas_dataset

    fr_reservoir = parameters.hydro.reservoirs.get("fr")
    if fr_reservoir is None:
        logger.warning("No hydro reservoir config found for FR, skipping FR open PHS")
        return atlas_dataset

    charge_efficiency, discharge_efficiency = get_binding_constraint_for_phs(study, "fr")

    turb_cap_df = link.get_capacity_indirect()[0]

    maximum_power_ts = Timeseries.from_values(parameters.start_date, frequency="1h", values=turb_cap_df)
    minimum_power_ts = Timeseries.from_values(
        parameters.start_date, frequency="1h", values=turb_cap_df * -1.0
    )

    try:
        transit_series = study.get_output(parameters.output_name).get_mc_ind_link(
            parameters.scenario,
            frequency=Frequency.HOURLY,
            data_type=MCIndLinksDataType.VALUES,
            area_from=link.area_from_id,
            area_to=link.area_to_id,
        )[("FLOW LIN.", "MWh")]
        power_ts = Timeseries.from_values(
            parameters.start_date, frequency="1h", values=transit_series * -1.0
        )
        power_fm = ForecastingMatrix().add(power_ts, parameters.execution_date)
    except Exception as e:
        logger.warning(f"Could not get power transit for FR open PHS: {e}")
        power_fm = None

    phs = Storage(
        name="fr_phs_open",
        node=atlas_dataset.get("node", "fr"),
        portfolio=get_portfolio(atlas_dataset, parameters, "fr"),
        storage_type=StorageType.PUMPED_HYDRAULIC_STORAGE,
        maximum_power=maximum_power_ts,
        minimum_power=minimum_power_ts,
        maximum_energy=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=float(fr_reservoir.open_loop_capacity),
        ),
        minimum_state_of_charge=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=0.0,
        ),
        charge_efficiency=charge_efficiency,
        discharge_efficiency=discharge_efficiency,
        storage_initial_level=parameters.storage.phs_initial_level,
        transition_duration=duration(hours=0),
        is_v2g=False,
        power=power_fm,
    )

    atlas_dataset.storage.add(phs)

    logger.debug("Created FR open PHS")
    return atlas_dataset
