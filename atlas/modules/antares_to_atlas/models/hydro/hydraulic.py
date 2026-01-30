"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Hydraulic/hydro generation units conversion.
"""

import csv
from typing import Any

from antares.craft.model.study import Study
from loguru import logger

from atlas.models.equipment.hydro import Hydro
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def load_hydro_reservoirs(parameters: AntaresToAtlasParameters) -> dict:
    """Load hydro reservoir parameters from configuration file."""
    hydro_reservoirs = {}

    if parameters.hydro_reservoirs_file and parameters.hydro_reservoirs_file.exists():
        logger.debug(f"Loading hydro reservoirs from {parameters.hydro_reservoirs_file}")
        with open(parameters.hydro_reservoirs_file) as f:
            reader = csv.reader(f, delimiter=";")
            headers = next(reader)

            for i, header in enumerate(headers[1:], start=1):
                hydro_reservoirs[header.strip()] = {}

            for row in reader:
                if len(row) < len(headers):
                    continue
                param_name = row[0]
                for i, header in enumerate(headers[1:], start=1):
                    try:
                        hydro_reservoirs[header.strip()][param_name] = float(row[i])
                    except (ValueError, IndexError):
                        pass

    return hydro_reservoirs


def convert_hydro_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    shared_state: dict[str, Any],
) -> list[Hydro]:
    """Convert hydro generation units from Antares to Atlas."""
    logger.info("Converting hydro generation units")

    hydro_reservoirs = load_hydro_reservoirs(parameters)
    areas_dict = shared_state.get("areas", study.get_areas())
    nodes_dict = shared_state.get("nodes_dict", {})
    portfolios_dict = shared_state.get("portfolios_dict", {})

    hydro_units = []
    for area_name in parameters.market_areas:
        if area_name not in areas_dict:
            continue

        area = areas_dict[area_name]
        hydro = area.hydro

        logger.debug(f"Processing hydro in area {area_name}")

        # TODO: Check if hydro has capacity/data
        # if no hydro data, skip

        # Create Atlas Hydro equipment
        equipment = Hydro(
            name=f"{area_name}_hydro",
            node=nodes_dict.get(area_name),
            portfolio=portfolios_dict.get(
                f"generator_{area_name}" if parameters.consumption_production_separation else f"portfolio_{area_name}"
            ),
            # TODO: Extract timeseries data from area.hydro:
            # maximum_power=extract_from(hydro.get_maxpower()),
            # minimum_power=...,
            # maximum_energy=...,
            # minimum_energy=...,
            # inflows=extract_from(hydro.get_mod_series()),
            # energy_target=...,
            # TODO: Set frequencies
            # inflow_frequency=InflowFrequency.Daily,
            # energy_target_frequency=InflowFrequency.Daily,
        )

        # Apply reservoir data if available
        if area_name in hydro_reservoirs and "ReservoirCapacity" in hydro_reservoirs[area_name]:
            # equipment.maximum_energy = create_constant_timeseries(hydro_reservoirs[area_name]["ReservoirCapacity"])
            pass

        hydro_units.append(equipment)

    logger.info(f"Converted {len(hydro_units)} hydro units")
    return hydro_units
