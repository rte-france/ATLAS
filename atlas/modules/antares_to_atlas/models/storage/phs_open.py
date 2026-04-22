"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import numpy as np
from antares.craft import Frequency, MCIndLinksDataType
from antares.craft.model.area import Area
from antares.craft.model.link import Link
from antares.craft.model.study import Study
from loguru import logger
from pendulum import duration

from atlas.enums import StorageType
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.modules.antares_to_atlas.utils import get_binding_constraint_for_phs
from atlas.objects.equipment.storage import Storage


def convert_phs_open_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    inflows_dictionary: dict,
) -> tuple[AtlasDataset, dict]:
    """Convert open-loop Pumped Hydraulic Storage from Antares to Atlas.

    Open PHS are modeled differently than closed PHS:
    - They connect to w_hydro_open_{node} virtual nodes via link w_hydro_open_{node}_x_open_turb
    - Part of the capacity is integrated into the existing hydro equipment (open part)
    - The remaining part becomes a PHS storage equipment (closed part)

    The split is calculated from the difference between:
    - Link capacity from w_hydro_open to x_open_turb (turb capacity)
    - Link capacity from w_hydro_open to area node (w_hydro indirect capacity)

    :return: Tuple of (updated atlas_dataset, updated inflows_dictionary)
    """
    logger.info("Converting open-loop PHS units")

    areas = study.get_areas()
    links = study.get_links()
    phs_open_list: list[Storage] = []

    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        if area_name.lower() == "fr":
            continue

        area = areas[area_name]
        reservoir = parameters.hydro.reservoirs.get(area_name)

        if reservoir is None or reservoir.open_loop_capacity == 0.0:
            continue

        logger.debug(f"Processing open PHS for area {area.id}")

        phs = _create_open_phs(
            area=area,
            study=study,
            parameters=parameters,
            atlas_dataset=atlas_dataset,
            inflows_dictionary=inflows_dictionary,
            links=links,
        )

        if phs:
            phs_open_list.append(phs)

    atlas_dataset.storage.add(phs_open_list)

    return atlas_dataset, inflows_dictionary


def _create_open_phs(
    area: Area,
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    inflows_dictionary: dict,
    links: dict[str, Link],
) -> Storage | None:
    """Create open-loop PHS equipment and update the corresponding hydro equipment.

    The open PHS is split into two parts:
    - Closed part → becomes the PHS Storage equipment
    - Open part → is added to the hydro equipment (MaximumPower, MaximumEnergy)
    """
    open_loop_capacity = parameters.hydro.reservoirs[area.id].open_loop_capacity

    # Turb link: w_hydro_open_{area} → x_open_turb
    turb_link_name = f"w_hydro_open_{area.id}_x_open_turb"
    turb_link = links.get(turb_link_name, None)
    if not turb_link:
        logger.debug(f"No turb link '{turb_link_name}' found for open PHS in area {area.id}")
        return None

    # Capacity check on turb link indirect (first scenario = static capacity)
    turb_cap_df = turb_link.get_capacity_indirect()[0]
    if turb_cap_df.max() == 0.0:
        return None

    # w_hydro link: area → w_hydro_open_{area}
    w_hydro_link_name = f"{area.id}_w_hydro_open_{area.id}"
    w_hydro_open_link = links.get(w_hydro_link_name, None)
    if not w_hydro_open_link:
        logger.warning(f"No link '{w_hydro_link_name}' found for open PHS in area {area.id}")
        return None

    # w_hydro indirect capacity (power from w_hydro node to area)
    w_hydro_cap_df = w_hydro_open_link.get_capacity_indirect()[0]

    # MinimumPower from w_hydro direct capacity (charge direction)
    min_power_df = w_hydro_open_link.get_capacity_direct()[0]
    minimum_power_ts = Timeseries.from_values(
        parameters.start_date, frequency="1h", values=(np.asarray(min_power_df, dtype=float) * -1.0).tolist()
    )

    # Efficiencies from binding constraint (same lookup as closed PHS)
    charge_efficiency, discharge_efficiency = get_binding_constraint_for_phs(study, area.id)

    # --- Split calculation ---
    # closed_delta: how much capacity goes to the closed PHS (positive remainder)
    closed_delta_arr = np.maximum(0.0, w_hydro_cap_df - turb_cap_df)
    # closed_ratio: fraction of open_loop_capacity that stays with hydro (open part)
    closed_ratio_arr = np.where(w_hydro_cap_df > 0, closed_delta_arr / w_hydro_cap_df, 0.0)

    # --- Update existing hydro equipment with the open part ---
    hydro = atlas_dataset.get("hydro", f"{area.id}_hydro")
    if hydro is not None:
        # Add closed_delta to hydro MaximumPower
        delta_ts = Timeseries.from_values(parameters.start_date, frequency="1h", values=closed_delta_arr.tolist())
        if hydro.maximum_power is not None:
            hydro.maximum_power = hydro.maximum_power + delta_ts
        else:
            hydro.maximum_power = delta_ts

        # Add open part of reservoir capacity to hydro MaximumEnergy
        additional_energy_arr = np.round(open_loop_capacity * closed_ratio_arr)
        additional_energy_ts = Timeseries.from_values(
            parameters.start_date, frequency="1h", values=additional_energy_arr.tolist()
        )
        if hydro.maximum_energy is not None:
            hydro.maximum_energy = hydro.maximum_energy + additional_energy_ts
        else:
            hydro.maximum_energy = additional_energy_ts

        # --- TODO: Update hydro inflows from {area.id}_phs.csv ---
        # The legacy code reads {path_inflows}/{area.id}_phs.csv and matches scenarios
        # by closest total energy to w_hydro_open_node.HydroReservoir.Modulation[scenario].
        # This requires access to antares craft hydro modulation timeseries which is not yet mapped.
        # See add_inflows_from_csv in hydro/inflows.py for the pattern.

        # --- TODO: Update hydro daily energy constraints ---
        # The legacy code computes MaximumDailyEnergy and MinimumDailyEnergy from the
        # calculated transit on w_hydro_open_link scaled by closed_ratio.
        # The Hydro object doesn't have minimum_daily_energy / maximum_daily_energy fields
        # in the current data model — these need to be added or mapped to an equivalent.

    else:
        logger.debug(
            f"No hydro equipment '{area.id}_hydro' found in atlas_dataset; open part of PHS will not be added to hydro."
        )
        additional_energy_arr = np.zeros_like(closed_ratio_arr)

    # PHS MaximumEnergy = closed part of reservoir (total - open part added to hydro)
    phs_max_energy_arr = np.round(open_loop_capacity - (open_loop_capacity * closed_ratio_arr))

    phs = Storage(
        name=f"{area.id}_phs_open",
        node=atlas_dataset.get("node", area.id),
        portfolio=atlas_dataset.get(
            "portfolio",
            f"generator_{area.id}" if parameters.consumption_production_separation else f"portfolio_{area.id}",
        ),
        storage_type=StorageType.PUMPED_HYDRAULIC_STORAGE,
        maximum_power=Timeseries.from_values(parameters.start_date, frequency="1h", values=turb_cap_df),
        minimum_power=minimum_power_ts,
        maximum_energy=Timeseries.from_values(
            parameters.start_date, frequency="1h", values=phs_max_energy_arr.tolist()
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
    )

    logger.debug(f"Created open PHS for area: {area.id}")
    return phs


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

    # Capacities from indirect transfer capacity (first scenario = static)
    turb_cap_df = link.get_capacity_indirect()[0]
    turb_cap_arr = np.asarray(turb_cap_df, dtype=float)

    maximum_power_ts = Timeseries.from_values(parameters.start_date, frequency="1h", values=turb_cap_arr.tolist())
    # FR PHS: MinimumPower = -MaximumPower (symmetric, uses same indirect capacity)
    minimum_power_ts = Timeseries.from_values(
        parameters.start_date, frequency="1h", values=(turb_cap_arr * -1.0).tolist()
    )

    # Power forecast from MC output (CalculatedTransit on fr_x_open_turb link)
    try:
        transit_df = study.get_output(parameters.output_name).get_mc_ind_link(
            parameters.scenario,
            frequency=Frequency.HOURLY,
            data_type=MCIndLinksDataType.VALUES,
            area_from=link.area_from_id,
            area_to=link.area_to_id,
        )[("FLOW LIN.", "MWh")]
        power_ts = Timeseries.from_values(
            parameters.start_date, frequency="1h", values=(np.asarray(transit_df, dtype=float) * -1.0).tolist()
        )
        power_fm = ForecastingMatrix()
        power_fm.add(power_ts, parameters.execution_date)
    except Exception as e:
        logger.warning(f"Could not get power transit for FR open PHS: {e}")
        power_fm = None

    phs = Storage(
        name="fr_phs_open",
        node=atlas_dataset.get("node", "fr"),
        portfolio=atlas_dataset.get(
            "portfolio",
            "generator_fr" if parameters.consumption_production_separation else "portfolio_fr",
        ),
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
