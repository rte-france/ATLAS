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
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.objects.equipment.storage import Storage


def convert_phs_open_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    hydro_reservoirs: dict,
    inflows_dictionary: dict,
) -> tuple[AtlasDataset, dict]:
    """Convert open-loop Pumped Hydraulic Storage from Antares to Atlas.

    Open PHS are modeled differently than closed PHS:
    - They connect to w_hydro_open_{node} virtual nodes
    - Part of the capacity is integrated into the hydro equipment
    - The remaining part becomes a PHS equipment

    The split is calculated based on the difference between:
    - Link capacity from PHS turb to w_hydro_open node
    - Link capacity from w_hydro_open node to actual node

    :return: Tuple of (updated atlas_dataset, updated inflows_dictionary)
    """
    logger.info("Converting open-loop PHS units")

    areas = study.get_areas()
    links = study.get_links()
    phs_open_list: list[Storage] = []

    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        # Skip France (handled separately in old code)
        if area_name.lower() == "fr":
            continue

        area = areas[area_name]

        # TODO: Verify how to access hydro reservoir capacity
        if area_name not in hydro_reservoirs or hydro_reservoirs[area_name].get("OpenLoopCapacity", 0.0) == 0.0:
            continue

        logger.debug(f"Processing open PHS for area {area.id}")

        # Look for link to x_open_turb from w_hydro_open_{node}
        # TODO: Need to find the w_hydro_open_{node} area and its link to x_open_turb
        # In old code: searches for links where DownhillNode.Name == "x_open_turb"
        # and UphillNode.Name contains the node name

        phs = _create_open_phs(
            area=area,
            study=study,
            parameters=parameters,
            atlas_dataset=atlas_dataset,
            hydro_reservoirs=hydro_reservoirs,
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
    hydro_reservoirs: dict,
    inflows_dictionary: dict,
    links: dict[str, Link],
) -> Storage | None:
    """Create open-loop PHS equipment.

    This is complex because:
    1. Find link from w_hydro_open_{node} to x_open_turb
    2. Find link from {node} to w_hydro_open_{node}
    3. Calculate the split between closed and open parts
    4. Update the hydro equipment with the open part
    5. Create PHS with the closed part
    """
    # TODO: Find the w_hydro_open_{area_name} virtual area
    areas_dict = study.get_areas()
    w_hydro_open_name = f"w_hydro_open_{area.id}"

    # In old code, the link naming is: area links to w_hydro_open_{area}
    # and w_hydro_open_{area} links to x_open_turb

    # Step 1: Find link from w_hydro_open to x_open_turb
    turb_link = None
    for link_id, link_obj in links.items():
        # TODO: Verify link naming and how to check endpoints
        if w_hydro_open_name.lower() in link_id.lower() and "x_open_turb" in link_id.lower():
            turb_link = link_obj
            break

    if not turb_link:
        logger.debug(f"No turb link found for open PHS in area {area.id}")
        return None

    # Check capacity
    try:
        # TODO: Verify how to get IndirectTransferCapacity
        turb_capacity_df = turb_link.get_capacity_indirect()
        if turb_capacity_df.abs().max().max() == 0.0:
            return None
        turb_capacity_ts = Timeseries(turb_capacity_df)
    except Exception as e:
        logger.warning(f"Could not get turb capacity for open PHS in area {area.id}: {e}")
        return None

    # Step 2: Find link from area to w_hydro_open
    w_hydro_open_link = None
    w_hydro_link_name = f"{area.id}_{w_hydro_open_name}"
    for link_id, link_obj in links.items():
        if w_hydro_link_name.lower() in link_id.lower():
            w_hydro_open_link = link_obj
            break

    if not w_hydro_open_link:
        logger.warning(f"No link found from {area.id} to {w_hydro_open_name}")
        return None

    # Get w_hydro link capacity
    try:
        # TODO: Verify how to get IndirectTransferCapacity
        w_hydro_capacity_df = w_hydro_open_link.get_capacity_indirect()
        w_hydro_capacity_ts = Timeseries(w_hydro_capacity_df)
    except Exception as e:
        logger.warning(f"Could not get w_hydro capacity for open PHS in area {area.id}: {e}")
        return None

    # Step 3: Get minimum power from DirectTransferCapacity
    try:
        # TODO: Verify how to get DirectTransferCapacity
        minimum_power_df = w_hydro_open_link.get_capacity_direct()
        minimum_power_ts = Timeseries(minimum_power_df * -1.0)
    except Exception as e:
        logger.warning(f"Could not get minimum power for open PHS in area {area.id}: {e}")
        minimum_power_ts = Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=0.0,
        )

    # Step 4: Calculate split between closed and open parts
    # TODO: This calculation is complex and involves:
    # - Calculating the difference between w_hydro capacity and turb capacity
    # - Using this to split the reservoir capacity
    # - Updating the hydro equipment with the open part
    # - Creating the PHS with the closed part
    # For now, leaving this with TODO comments

    binding_constraints = study.get_binding_constraints()
    bc_name = f"{area.id}_phs_open"  # TODO define properly
    bc_obj = binding_constraints.get(bc_name, None)
    if bc_obj:
        bc_terms = bc_obj.get_terms()
        term_name = f"{area.id}_phs_open_charge_efficiency"  # TODO define properly
        term = bc_terms.get(term_name, None)
        if term:
            charge_efficiency = term.weight
            discharge_efficiency = term.offset

    # TODO: Calculate the split ratio and update hydro equipment
    # This involves complex logic from the old code around lines 139-187

    # Create PHS equipment with closed part
    phs = Storage(
        name=f"{area.id}_phs_open",
        node=atlas_dataset.get("node", area.id),
        portfolio=atlas_dataset.get(
            "portfolio",
            f"generator_{area.id}" if parameters.consumption_production_separation else f"portfolio_{area.id}",
        ),
        storage_type=StorageType.PUMPED_HYDRAULIC_STORAGE,
        maximum_power=turb_capacity_ts,
        minimum_power=minimum_power_ts,
        maximum_energy=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=float(hydro_reservoirs[area.id]["OpenLoopCapacity"]),
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

    # TODO: Update hydro equipment with the open part
    # This involves:
    # - Getting or creating the hydro equipment
    # - Adding the open part of MaximumPower
    # - Adding the open part of MaximumEnergy
    # - Updating inflows from CSV files
    # - Updating daily energy constraints
    # See old code lines 67-309 for detailed logic

    # TODO: Update inflows_dictionary with PHS inflows from CSV
    # This requires reading CSV files and matching scenarios
    # See old code lines 192-286 for detailed logic

    logger.debug(f"Created open PHS for area: {area.id}")
    return phs


def convert_phs_open_fr(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    hydro_reservoirs: dict,
) -> AtlasDataset:
    """Convert open-loop PHS for France (special case).

    France's open PHS is modeled differently and doesn't split
    into hydro equipment.
    """
    if "fr" not in parameters.market_areas:
        return atlas_dataset

    logger.info("Converting FR open-loop PHS")

    areas = study.get_areas()
    links = study.get_links()

    if "fr" not in areas:
        return atlas_dataset

    area = areas["fr"]

    # Find link from fr to x_open_turb
    link = None
    for link_id, link_obj in links.items():
        if "fr_x_open_turb" in link_id.lower():
            link = link_obj
            break

    if not link:
        logger.debug("No open turb link found for FR")
        return atlas_dataset

    # Get efficiencies from binding constraint
    charge_efficiency = 1.0
    discharge_efficiency = 1.0

    binding_constraints = study.get_binding_constraints()
    bc_name = f"{area.id}_phs_open_fr"  # TODO define properly
    bc_obj = binding_constraints.get(bc_name, None)
    if bc_obj:
        bc_terms = bc_obj.get_terms()
        term_name = f"{area.id}_phs_open_fr_charge_efficiency"  # TODO define properly
        term = bc_terms.get(term_name, None)
        if term:
            charge_efficiency = term.weight  # TODO not sure how to access
            discharge_efficiency = term.offset

    # Get capacities
    try:
        # TODO: Verify how to get IndirectTransferCapacity
        maximum_power_df = link.get_capacity_indirect()
        maximum_power_ts = Timeseries(maximum_power_df)

        minimum_power_df = link.get_capacity_indirect()
        minimum_power_ts = Timeseries(minimum_power_df * -1.0)
    except Exception as e:
        logger.warning(f"Could not get capacities for FR open PHS: {e}")
        return atlas_dataset

    # TODO: Get power time series from CalculatedTransit
    # power_transit_df = link.get_calculated_transit(str(parameters.scenario))
    # power_ts = Timeseries(power_transit_df * -1.0)

    # Create PHS equipment
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
            default_value=float(hydro_reservoirs["fr"]["OpenLoopCapacity"]),
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
        is_v2g=False,
    )

    # TODO: Add power forecast
    # phs.power.add(parameters.execution_date, power_ts)

    atlas_dataset.storage.add(phs)

    logger.debug("Created FR open PHS")
    return atlas_dataset
