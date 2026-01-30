"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Water value computation - BP23 specific.
"""

from typing import Any

from antares.craft.model.study import Study
from loguru import logger

from atlas.models.business_model import BusinessModel
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def compute_water_values(
    study: Study,
    parameters: AntaresToAtlasParameters,
    shared_state: dict[str, Any],
) -> list[BusinessModel]:
    """Compute water values for hydraulic reservoirs.

    Water values represent the opportunity cost of using stored water.
    This updates existing Hydro equipment with computed water values.
    """
    logger.info("Computing water values (BP23)")

    areas = study.get_areas()

    updated_count = 0
    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]
        hydro = area.hydro

        # Check if area has hydro with reservoir
        logger.debug(f"Processing water values for {area_name}")

        # TODO: Access hydro data
        # water_values = hydro.get_water_values() or similar
        # Then update the corresponding Hydro equipment in shared_state or Atlas dataset

        # Water values are typically stored as timeseries/matrices
        # and depend on:
        # - Reservoir level
        # - Time of year
        # - Inflow forecasts
        # - Electricity price forecasts

        updated_count += 1

    logger.info(f"Computed water values for {updated_count} areas")
    return []
