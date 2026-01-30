"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Thermal generation units conversion.
"""

import csv
from typing import Any

from antares.craft.model.study import Study
from loguru import logger
from pendulum import Duration

from atlas.models.control_block import ControlBlock
from atlas.models.equipment.thermal import Thermal
from atlas.models.market.market_area import MarketArea
from atlas.models.node import Node
from atlas.models.portfolio import Portfolio
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def load_thermic_parameters(parameters: AntaresToAtlasParameters) -> tuple[dict, list]:
    """Load thermic parameters from configuration file.

    :param parameters: Conversion parameters
    :return: Tuple of (thermic_parameter dict, thermic_properties list)
    """
    thermic_properties = [
        "MinimumStablePowerDuration",
        "StartupDelayProbability",
        "StartupDuration",
        "ShutdownDuration",
        "MaximumGradient",
        "Strategy",
        "SetupDelay",
    ]
    thermic_parameter = {}

    if parameters.thermic_config_file and parameters.thermic_config_file.exists():
        logger.debug(f"Loading thermic config from {parameters.thermic_config_file}")
        with open(parameters.thermic_config_file) as f:
            reader = csv.reader(f, delimiter=";")
            headers = next(reader)

            # Build index for properties we care about
            thermic_index = {}
            for i, header in enumerate(headers):
                if header.strip() in thermic_properties:
                    thermic_parameter[header.strip()] = {}
                    thermic_index[header.strip()] = i

            # Read data rows
            for row_index, row in enumerate(reader, start=2):
                if len(row) != len(headers):
                    logger.warning(f"Invalid number of columns on line {row_index} in thermic config file")
                    continue

                technology = row[0]
                for key, col_index in thermic_index.items():
                    if key == "Strategy":
                        thermic_parameter[key][technology] = row[col_index].strip()
                    else:
                        try:
                            thermic_parameter[key][technology] = float(row[col_index])
                        except ValueError:
                            logger.warning(f"Invalid value for {key} at line {row_index}: {row[col_index]}")

    return thermic_parameter, thermic_properties


def convert_thermal_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    shared_state: dict[str, Any],
) -> list[Thermal]:
    """Convert thermal generation units from Antares to Atlas.

    :param study: Antares study object from antares_craft
    :type study: Study
    :param parameters: Conversion parameters
    :type parameters: AntaresToAtlasParameters
    :param shared_state: Shared state dictionary containing nodes, portfolios, etc.
    :type shared_state: dict[str, Any]
    :return: List of created Thermal equipment
    :rtype: list[Thermal]
    """
    logger.info("Converting thermal generation units")

    # Load thermic parameters if config file is provided
    thermic_parameter, thermic_properties = load_thermic_parameters(parameters)

    # Get areas from shared state or study
    areas = study.get_areas()

    # Get created nodes, portfolios, etc from shared state
    # TODO: When atlas_dataset is available, get these from shared_state
    areas = study.get_areas()
    nodes_dict = shared_state.get("nodes_dict", {})  # Dict[str, Node]
    portfolios_dict = shared_state.get("portfolios_dict", {})  # Dict[str, Portfolio]

    thermal_units = []
    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]
        thermals = area.get_thermals()

        logger.debug(f"Processing {len(thermals)} thermal clusters in area {area_name}")

        for thermal_id, thermal in thermals.items():
            props = thermal.properties

            # Skip if group is excluded
            if props.group in parameters.excluded_thermic_groups:
                logger.debug(f"  Skipping {thermal.name} (excluded group: {props.group})")
                continue

            # Skip if no capacity
            if not props.enabled or props.nominal_capacity * props.unit_count == 0.0:
                logger.debug(f"  Skipping {thermal.name} (disabled or zero capacity)")
                continue

            logger.debug(f"  Processing thermal: {thermal.name}")
            logger.debug(f"    Group: {props.group}")
            logger.debug(f"    Nominal capacity: {props.nominal_capacity} MW")
            logger.debug(f"    Unit count: {props.unit_count}")
            logger.debug(f"    Installed capacity: {props.installed_capacity} MW")

            # Create Atlas Thermal equipment
            # Note: Duration fields need to be None or float (will be converted by validator)
            equipment = Thermal(
                name=thermal.name,
                node=nodes_dict.get(area_name),
                portfolio=portfolios_dict.get(
                    f"generator_{area_name}"
                    if parameters.consumption_production_separation
                    else f"portfolio_{area_name}"
                ),
                installed_capacity=props.installed_capacity,
                # minimum_power=props.min_stable_power * props.unit_count,  # TODO: Convert to Timeseries
                # maximum_power=...,  # TODO: Get from timeseries data
                co2_emission_factor=props.co2 if props.co2 else 0.0,
                minimum_time_off=Duration(hours=props.min_down_time) if props.min_down_time else None,
                minimum_time_on=Duration(hours=props.min_up_time) if props.min_up_time else None,
                # TODO: Add more properties:
                # - startup_cost
                # - variable_cost (from market_bid_cost or marginal_cost)
                # - outage properties
                # - Apply thermic_parameter overrides
            )

            # Apply thermic parameters from config file
            for param_name in thermic_parameter.keys():
                if thermal.name in thermic_parameter[param_name]:
                    value = thermic_parameter[param_name][thermal.name]
                elif props.group in thermic_parameter[param_name]:
                    value = thermic_parameter[param_name][props.group]
                else:
                    continue

                # TODO: Map parameter names to Thermal model attributes
                # if param_name == "MaximumGradient":
                #     equipment.maximum_gradient = value * props.unit_count
                # elif param_name == "Strategy":
                #     equipment.strategy = ThermalStrategy[value]
                # ...

            thermal_units.append(equipment)

    logger.info(f"Converted {len(thermal_units)} thermal units")
    return thermal_units
