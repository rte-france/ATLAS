"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

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


def convert_phs_closed_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Convert closed-loop Pumped Hydraulic Storage from Antares to Atlas.

    Closed PHS are created from links to virtual nodes:
    - x_closed_turb: turbining capacity
    - x_closed_pump: pumping capacity

    The function processes both links and creates/updates a single PHS equipment.
    """
    logger.info("Converting closed-loop PHS units")

    areas = study.get_areas()
    links = study.get_links()
    phs_closed_list: list[Storage] = []

    # First pass: create PHS from turb links
    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]

        if (
            area_name not in parameters.hydro.reservoirs
            or parameters.hydro.reservoirs[area_name].closed_loop_capacity == 0.0
        ):
            continue

        logger.debug(f"Processing closed PHS for area {area.id}")

        # Look for turb link
        turb_link = links.get(f"{area.id}_x_closed_turb")

        if turb_link:
            phs = _create_phs_from_turb_link(
                area=area,
                link=turb_link,
                study=study,
                parameters=parameters,
                atlas_dataset=atlas_dataset,
            )
            if phs:
                phs_closed_list.append(phs)

    # Second pass: update PHS with pump links
    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]

        if (
            area_name not in parameters.hydro.reservoirs
            or parameters.hydro.reservoirs[area_name].closed_loop_capacity == 0.0
        ):
            continue

        pump_link = links.get(f"{area.id}_x_closed_pump")
        if pump_link:
            # Find existing PHS or create new one
            existing_phs = None
            for phs in phs_closed_list:
                if phs.name == f"{area.id}_phs":
                    existing_phs = phs
                    break

            if existing_phs:
                _update_phs_with_pump_link(
                    phs=existing_phs,
                    link=pump_link,
                    parameters=parameters,
                    study=study,
                )
            else:
                # Create PHS from pump link if turb link didn't exist
                logger.warning(f"No turb link found for closed PHS in area {area.id}, creating from pump link")
                phs = _create_phs_from_pump_link(
                    area=area,
                    link=pump_link,
                    study=study,
                    parameters=parameters,
                    atlas_dataset=atlas_dataset,
                )
                if phs:
                    phs_closed_list.append(phs)

    atlas_dataset.storage.add(phs_closed_list)

    return atlas_dataset


def _create_phs_from_turb_link(
    area: Area,
    link: Link,
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> Storage | None:
    """Create PHS equipment from turbining link."""
    # Check if capacity is non-zero
    scenario = (
        study.get_output(parameters.output_name)
        .get_link_ts_numbers(link.area_from_id, link.area_to_id)
        .get(parameters.scenario, None)
    )
    if scenario is None:
        return None

    capacity_df = link.get_capacity_indirect()[scenario - 1]
    if capacity_df.abs().max().max() == 0.0:
        return None

    maximum_power_ts = Timeseries.from_values(parameters.start_date, frequency="1h", values=capacity_df)

    charge_efficiency, discharge_efficiency = get_binding_constraint_for_phs(study, area.id)

    transit_df = study.get_output(parameters.output_name).get_mc_ind_link(
        parameters.scenario,
        frequency=Frequency.HOURLY,
        data_type=MCIndLinksDataType.VALUES,
        area_from=link.area_from_id,
        area_to=link.area_to_id,
    )[("FLOW LIN.", "MWh")]

    power_ts = Timeseries.from_values(parameters.start_date, frequency="1h", values=transit_df * -1.0)
    power_fm = ForecastingMatrix()
    power_fm.add(power_ts, parameters.execution_date)

    phs = Storage(
        name=f"{area.id}_phs",
        node=atlas_dataset.get("node", area.id),
        portfolio=atlas_dataset.get(
            "portfolio",
            f"generator_{area.id}" if parameters.consumption_production_separation else f"portfolio_{area.id}",
        ),
        storage_type=StorageType.PUMPED_HYDRAULIC_STORAGE,
        maximum_power=maximum_power_ts,
        maximum_energy=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=parameters.hydro.reservoirs[area.id].closed_loop_capacity,
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
        power=power_fm,
    )

    logger.debug(f"Created closed PHS from turb link for area: {area.id}")
    return phs


def _create_phs_from_pump_link(
    area: Area,
    link: Link,
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> Storage | None:
    """Create PHS equipment from pumping link (fallback when turb link doesn't exist)."""
    # Check if capacity is non-zero
    scenario = (
        study.get_output(parameters.output_name)
        .get_link_ts_numbers(link.area_from_id, link.area_to_id)
        .get(parameters.scenario, None)
    )
    if scenario is None:
        return None

    capacity_df = link.get_capacity_direct()[scenario - 1]
    if capacity_df.abs().max().max() == 0.0:
        return None

    minimum_power_ts = Timeseries.from_values(parameters.start_date, frequency="1h", values=capacity_df * -1.0)

    charge_efficiency, discharge_efficiency = get_binding_constraint_for_phs(study, area.id)

    transit_df = study.get_output(parameters.output_name).get_mc_ind_link(
        parameters.scenario,
        frequency=Frequency.HOURLY,
        data_type=MCIndLinksDataType.VALUES,
        area_from=link.area_from_id,
        area_to=link.area_to_id,
    )[("FLOW LIN.", "MWh")]

    power_ts = Timeseries.from_values(parameters.start_date, frequency="1h", values=transit_df * -1.0)
    power_fm = ForecastingMatrix()
    power_fm.add(power_ts, parameters.execution_date)

    phs = Storage(
        name=f"{area.id}_phs",
        node=atlas_dataset.get("node", area.id),
        portfolio=atlas_dataset.get(
            "portfolio",
            f"generator_{area.id}" if parameters.consumption_production_separation else f"portfolio_{area.id}",
        ),
        storage_type=StorageType.PUMPED_HYDRAULIC_STORAGE,
        minimum_power=minimum_power_ts,
        maximum_energy=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=parameters.hydro.reservoirs[area.id].closed_loop_capacity,
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
        power=power_fm,
    )

    logger.debug(f"Created closed PHS from pump link for area: {area.id}")
    return phs


def _update_phs_with_pump_link(phs: Storage, link: Link, parameters: AntaresToAtlasParameters, study: Study) -> None:
    """Update existing PHS equipment with pumping capacity."""

    scenario = (
        study.get_output(parameters.output_name)
        .get_link_ts_numbers(link.area_from_id, link.area_to_id)
        .get(parameters.scenario, None)
    )
    if scenario is not None:
        capacity_df = link.get_capacity_direct()[scenario - 1]
        if capacity_df.abs().max().max() == 0.0:
            return

        minimum_power_ts = Timeseries.from_values(parameters.start_date, frequency="1h", values=capacity_df * -1.0)
        phs.minimum_power = minimum_power_ts

        transit_df = study.get_output(parameters.output_name).get_mc_ind_link(
            parameters.scenario,
            frequency=Frequency.HOURLY,
            data_type=MCIndLinksDataType.VALUES,
            area_from=link.area_from_id,
            area_to=link.area_to_id,
        )[("FLOW LIN.", "MWh")]

        power_ts = Timeseries.from_values(parameters.start_date, frequency="1h", values=transit_df * -1.0)

        if phs.power is not None:
            fm = phs.power
            exec_key = parameters.execution_date.format(fm.date_format)
            if isinstance(fm, ForecastingMatrix) and exec_key in fm.indexes:
                prev_ts = fm[exec_key]
                fm.replace(parameters.execution_date, prev_ts + power_ts)
            else:
                fm.add(power_ts, parameters.execution_date)
        else:
            power_fm = ForecastingMatrix()
            power_fm.add(power_ts, parameters.execution_date)
            phs.power = power_fm
    else:
        logger.warning("Could not update PHS with pump link: scenario not found for link")
