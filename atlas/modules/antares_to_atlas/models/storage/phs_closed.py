"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.area import Area
from antares.craft.model.link import Link
from antares.craft.model.study import Study
from loguru import logger
from pendulum import duration

from atlas.enums import StorageType
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.storage import Storage
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def convert_phs_closed_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    hydro_reservoirs: dict,
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

        # TODO: Verify how to access hydro reservoir capacity
        # In old code: hydro_reservoirs[node_name]["ClosedLoopCapacity"]
        if area_name not in hydro_reservoirs or hydro_reservoirs[area_name].get("ClosedLoopCapacity", 0.0) == 0.0:
            continue

        logger.debug(f"Processing closed PHS for area {area.id}")

        # Look for turb link
        turb_link = _find_link_to_virtual_node(links, area.id, "x_closed_turb")
        if turb_link:
            phs = _create_phs_from_turb_link(
                area=area,
                link=turb_link,
                study=study,
                parameters=parameters,
                atlas_dataset=atlas_dataset,
                hydro_reservoirs=hydro_reservoirs,
            )
            if phs:
                phs_closed_list.append(phs)

    # Second pass: update PHS with pump links
    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]

        if area_name not in hydro_reservoirs or hydro_reservoirs[area_name].get("ClosedLoopCapacity", 0.0) == 0.0:
            continue

        # Look for pump link
        pump_link = _find_link_to_virtual_node(links, area.id, "x_closed_pump")
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
                    hydro_reservoirs=hydro_reservoirs,
                )
                if phs:
                    phs_closed_list.append(phs)

    atlas_dataset.storage.add(phs_closed_list)

    return atlas_dataset


def _find_link_to_virtual_node(links: dict[str, Link], area_id: str, virtual_node: str) -> Link | None:
    """Find link connecting an area to a virtual node."""
    link_name = f"{area_id}_{virtual_node}"

    # TODO: Verify if links are indexed by name or by ID
    # May need to check link.area_from and link.area_to
    for link_id, link_obj in links.items():
        if link_name.lower() in link_id.lower():
            return link_obj
    return None


def _get_binding_constraint_for_phs(study: Study, area_id: str) -> tuple[float, float]:
    """Get charge and discharge efficiency from binding constraint.

    Returns:
        tuple: (charge_efficiency, discharge_efficiency)
    """

    binding_constraints = study.get_binding_constraints()
    bc_name = f"{area_id}_phs_closed"  # TODO define properly
    bc_obj = binding_constraints.get(bc_name, None)
    if bc_obj:
        bc_terms = bc_obj.get_terms()
        term_name = f"{area_id}_phs_closed_charge_efficiency"  # TODO define properly
        term = bc_terms.get(term_name, None)
        if term:
            charge_efficiency = term.weight  # TODO not sure how to access
            discharge_efficiency = term.offset

    return charge_efficiency, discharge_efficiency


def _create_phs_from_turb_link(
    area: Area,
    link: Link,
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    hydro_reservoirs: dict,
) -> Storage | None:
    """Create PHS equipment from turbining link."""
    # Check if capacity is non-zero
    try:
        # TODO: Verify how to get IndirectTransferCapacity
        # In old code: link.IndirectTransferCapacity.GetTimeSeriesByName("1")
        capacity_df = link.get_capacity_indirect()
        if capacity_df.abs().max().max() == 0.0:
            return None

        maximum_power_ts = Timeseries(capacity_df)
    except Exception as e:
        logger.warning(f"Could not get turb capacity for PHS in area {area.id}: {e}")
        return None

    # Get efficiencies from binding constraint
    charge_efficiency, discharge_efficiency = _get_binding_constraint_for_phs(study, link, area.id)

    # Get power time series
    try:
        # TODO: Verify how to get CalculatedTransit time series
        # In old code: link.CalculatedTransit.GetTimeSeriesByName(str(p.scenario))
        transit_df = link.get_capacity_direct()  # TODO: Get correct transit data
        power_ts = Timeseries(transit_df * -1.0)
    except Exception as e:
        logger.warning(f"Could not get transit data for turb link in area {area.id}: {e}")
        power_ts = Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=0.0,
        )

    # Create PHS equipment
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
            default_value=float(hydro_reservoirs[area.id]["ClosedLoopCapacity"]),
        ),
        minimum_state_of_charge=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=0.0,
        ),
        charge_efficiency=charge_efficiency,
        discharge_efficiency=discharge_efficiency,
        storage_initial_level=parameters.phs_initial_level,
        transition_duration=duration(hours=0),
        # setup_delay=duration(hours=0),  # TODO: Verify if this field exists in new model
    )

    # TODO: Add power forecast
    # phs.power.add(parameters.execution_date, power_ts)

    logger.debug(f"Created closed PHS from turb link for area: {area.id}")
    return phs


def _create_phs_from_pump_link(
    area: Area,
    link: Link,
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    hydro_reservoirs: dict,
) -> Storage | None:
    """Create PHS equipment from pumping link (fallback when turb link doesn't exist)."""
    # Check if capacity is non-zero
    try:
        # TODO: Verify how to get DirectTransferCapacity
        # In old code: link.DirectTransferCapacity.GetTimeSeriesByName("1")
        capacity_df = link.get_capacity_direct()
        if capacity_df.abs().max().max() == 0.0:
            return None

        minimum_power_ts = Timeseries(capacity_df * -1.0)
    except Exception as e:
        logger.warning(f"Could not get pump capacity for PHS in area {area.id}: {e}")
        return None

    # Get efficiencies from binding constraint
    charge_efficiency, discharge_efficiency = _get_binding_constraint_for_phs(study, link, area.id)

    # Get power time series
    try:
        # TODO: Verify how to get CalculatedTransit time series
        transit_df = link.get_capacity_direct()  # TODO: Get correct transit data
        power_ts = Timeseries(transit_df * -1.0)
    except Exception as e:
        logger.warning(f"Could not get transit data for pump link in area {area.id}: {e}")
        power_ts = Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=0.0,
        )

    # Create PHS equipment
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
            default_value=float(hydro_reservoirs[area.id]["ClosedLoopCapacity"]),
        ),
        minimum_state_of_charge=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=0.0,
        ),
        charge_efficiency=charge_efficiency,
        discharge_efficiency=discharge_efficiency,
        storage_initial_level=parameters.phs_initial_level,
        transition_duration=duration(hours=0),
    )

    # TODO: Add power forecast
    # phs.power.add(parameters.execution_date, power_ts)

    logger.debug(f"Created closed PHS from pump link for area: {area.id}")
    return phs


def _update_phs_with_pump_link(
    phs: Storage,
    link: Link,
    parameters: AntaresToAtlasParameters,
) -> None:
    """Update existing PHS equipment with pumping capacity."""
    try:
        # TODO: Verify how to get DirectTransferCapacity
        capacity_df = link.get_capacity_direct()
        if capacity_df.abs().max().max() == 0.0:
            return

        minimum_power_ts = Timeseries(capacity_df * -1.0)
        phs.minimum_power = minimum_power_ts

        # TODO: Add pump power to existing power forecast
        # Get transit data and add to power
        # transit_df = link.get_calculated_transit(str(parameters.scenario))
        # power_pump_ts = Timeseries(transit_df * -1.0)
        # Merge with existing power time series

    except Exception as e:
        logger.warning(f"Could not update PHS with pump link: {e}")
