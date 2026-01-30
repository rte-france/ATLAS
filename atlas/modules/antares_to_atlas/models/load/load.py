"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Any

from antares.craft.model.study import Study
from loguru import logger

from atlas.models.equipment.load import Load
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def convert_load_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    shared_state: dict[str, Any],
) -> list[Load]:
    """Convert load data from Antares to Atlas."""
    logger.info("Converting load data")

    areas_dict = shared_state.get("areas", study.get_areas())
    nodes_dict = shared_state.get("nodes_dict", {})
    portfolios_dict = shared_state.get("portfolios_dict", {})

    loads = []
    for area_name in parameters.market_areas:
        if area_name not in areas_dict:
            continue

        logger.debug(f"Processing load for area {area_name}")

        equipment = Load(
            name=f"{area_name}_load",
            node=nodes_dict.get(area_name),
            portfolio=portfolios_dict.get(
                f"supplier_{area_name}" if parameters.consumption_production_separation else f"portfolio_{area_name}"
            ),
            # TODO: Extract load timeseries from area
            # Load data should be available from area object
        )

        loads.append(equipment)

    logger.info(f"Converted {len(loads)} load units")
    return loads
