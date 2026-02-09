"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import os

from antares.craft.model.area import Area
from antares.craft.model.study import Study
from loguru import logger
from pendulum import duration

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.hydro import Hydro
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def convert_hydraulic_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> tuple[AtlasDataset, dict, dict]:
    """Convert Hydraulic reservoir units from Antares to Atlas.

    Hydraulic units are complex equipment with:
    - Reservoir capacity management
    - Inflow profiles
    - Daily energy constraints
    - Water value calculation
    - Fragment prices and volumes

    :return: Tuple of (atlas_dataset, inflows_dictionary, hydro_reservoirs)
    """
    logger.info("Converting Hydraulic units")

    # Load hydraulic reservoirs data from CSV
    hydro_reservoirs = _load_hydro_reservoirs(parameters)
    inflows_dictionary = {}

    areas = study.get_areas()
    hydro_units: list[Hydro] = []

    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]
        logger.debug(f"Processing hydraulic unit for area {area.id}")

        # TODO: Verify how to access HydroReservoir from area
        # In old code: antares_node.HydroReservoir
        try:
            # TODO: Get hydro reservoir data from area
            # hydro_reservoir = area.get_hydro_reservoir()
            # sc_hydro = hydro_reservoir.hydro_selected_scenario[parameters.scenario - 1]
            pass
        except Exception as e:
            logger.warning(f"Could not access hydro reservoir for area {area.id}: {e}")
            continue

        # TODO: Check if hydraulic equipment should be created
        # In old code: checks CalculatedStorageProduction, GeneratingMaxPower, ReservoirCapacity
        # if not _should_create_hydro(area, parameters, hydro_reservoirs):
        #     continue

        hydro = _create_hydraulic_equipment(
            area=area,
            study=study,
            parameters=parameters,
            atlas_dataset=atlas_dataset,
            hydro_reservoirs=hydro_reservoirs,
            inflows_dictionary=inflows_dictionary,
        )

        if hydro:
            hydro_units.append(hydro)

    atlas_dataset.hydro = hydro_units

    return atlas_dataset, inflows_dictionary, hydro_reservoirs


def _load_hydro_reservoirs(parameters: AntaresToAtlasParameters) -> dict:
    """Load hydraulic reservoirs data from CSV file.

    Returns dict with node names as keys and reservoir properties as values:
    - ReservoirCapacity
    - OpenLoopCapacity
    - ClosedLoopCapacity
    """
    hydro_reservoirs = {}

    if not os.path.isfile(parameters.hydro_reservoirs_file):
        logger.warning(f"Hydro reservoirs file not found: {parameters.hydro_reservoirs_file}")
        return hydro_reservoirs

    logger.debug(f"Loading hydro reservoirs from: {parameters.hydro_reservoirs_file}")

    try:
        with open(parameters.hydro_reservoirs_file) as f:
            lines_list = f.readlines()

        hydro_index = {}
        headers = []

        for row_index, line in enumerate(lines_list):
            if row_index == 0:
                # Parse headers
                headers = line.split(";")
                for i in range(1, len(headers)):
                    node_name = headers[i].strip()
                    hydro_reservoirs[node_name] = {}
                    hydro_index[node_name] = i
            else:
                # Parse data rows
                splitted_line = line.split(";")
                if len(splitted_line) != len(headers):
                    msg = (
                        f"Invalid number of columns on line {row_index + 1}. "
                        "Please modify the HydraulicReservoirs file."
                    )
                    raise ValueError(msg)

                property_name = splitted_line[0]
                for node_name, column_index in hydro_index.items():
                    hydro_reservoirs[node_name][property_name] = float(splitted_line[column_index])

        logger.debug(f"Loaded hydro reservoirs for {len(hydro_reservoirs)} nodes")

    except Exception as e:
        logger.error(f"Error loading hydro reservoirs file: {e}")
        return {}

    return hydro_reservoirs


def _create_hydraulic_equipment(
    area: Area,
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    hydro_reservoirs: dict,
    inflows_dictionary: dict,
) -> Hydro | None:
    """Create a Hydraulic equipment for an area."""
    # TODO: Get hydro reservoir from area
    # In old code: area.HydroReservoir
    try:
        # TODO: Verify how to access hydro reservoir properties
        # - GeneratingMaxPower
        # - ReservoirCapacity
        # - CalculatedStorageProduction
        # - Modulation (inflows)
        # - ReservoirManagement
        # - HydroSelectedScenario
        pass
    except Exception as e:
        logger.warning(f"Could not create hydro equipment for area {area.id}: {e}")
        return None

    # TODO: Check if we should create the equipment
    # if generating_max_power.abs().max() == 0.0:
    #     return None
    # if area.id in hydro_reservoirs and hydro_reservoirs[area.id].get("ReservoirCapacity", 0) == 0:
    #     return None

    # Get reservoir capacity
    # TODO: Verify how to get ReservoirCapacity from hydro reservoir
    reservoir_capacity = 0.0
    if area.id in hydro_reservoirs:
        reservoir_capacity = hydro_reservoirs[area.id].get("ReservoirCapacity", 0.0)
    # else:
    #     reservoir_capacity = hydro_reservoir.reservoir_capacity

    if reservoir_capacity == 0:
        logger.warning(
            f"Reservoir capacity of {area.id}_hydro is 0. Water values won't be calculated for this equipment"
        )

    # TODO: Get maximum power from hydro reservoir
    # In old code: antares_node.HydroReservoir.GeneratingMaxPower
    maximum_power_ts = Timeseries.from_index(
        start_date=parameters.start_date,
        frequency="1h",
        end_date=parameters.start_date + duration(years=1),
        default_value=0.0,
    )

    # Create Hydro equipment
    hydro = Hydro(
        name=f"{area.id}_hydro",
        node=atlas_dataset.get("node", area.id),
        portfolio=atlas_dataset.get(
            "portfolio",
            f"generator_{area.id}" if parameters.consumption_production_separation else f"portfolio_{area.id}",
        ),
        maximum_power=maximum_power_ts,
        minimum_power=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=0.0,
        ),
        maximum_energy=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=reservoir_capacity,
        ),
        minimum_energy=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=0.0,
        ),
        # energy_target_frequency="Daily",  # TODO: Verify field name
        # inflow_frequency="Daily",  # TODO: Verify field name
    )

    # TODO: Set inflows or energy target
    # Logic depends on use_hydro_heuristic, ReservoirManagement, and use_water_value
    # if (parameters.use_hydro_heuristic or reservoir_management) and parameters.use_water_value:
    #     # Use inflows
    #     if reservoir_management:
    #         hydro.inflows = modulation_ts
    #         node_inflows_dictionary = _prepare_inflows_for_water_values(area, parameters)
    #     else:
    #         node_inflows_dictionary = _add_inflows_from_csv(area, hydro, modulation_ts, parameters)
    #     inflows_dictionary[area.id] = node_inflows_dictionary
    # else:
    #     # Use energy target
    #     hydro.energy_target = modulation_ts

    # TODO: Set daily energy constraints
    # In old code: uses CalculatedStorageProduction to calculate daily min/max energy
    # hydro.has_daily_energy_constraint = True
    # hydro.minimum_daily_energy = ...
    # hydro.maximum_daily_energy = ...
    # See old code lines 157-180

    # TODO: Set fragment prices and volumes
    # In old code: from parameters.fragment_prices and parameters.fragment_volumes
    # hydro.fragment_prices.add(...)
    # hydro.fragment_volumes.add(...)
    # See old code lines 182-195

    logger.debug(f"Created hydraulic equipment for area: {area.id}")
    return hydro
