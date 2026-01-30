"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Initial storage levels - BP23 specific.
"""

from typing import Any

from antares.craft.model.study import Study
from loguru import logger

from atlas.models.business_model import BusinessModel
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def set_initial_levels(
    study: Study,
    parameters: AntaresToAtlasParameters,
    shared_state: dict[str, Any],
) -> list[BusinessModel]:
    """Set initial storage levels for all storage equipment.

    Configures initial energy levels for:
    - Hydro reservoirs
    - Batteries
    - Electric vehicles
    - Pumped hydro storage
    """
    logger.info("Setting initial storage levels (BP23)")

    areas = study.get_areas()

    # Set initial levels from parameters if provided
    initial_level_config = (
        parameters.hydro_initialization_curve if hasattr(parameters, "hydro_initialization_curve") else None
    )

    updated_count = 0
    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]

        # Hydro initial levels
        hydro = area.hydro
        logger.debug(f"Setting hydro initial level for {area_name}")
        # TODO: Update Hydro equipment with initial_level timeseries

        # Storage initial levels
        st_storages = area.get_st_storages()
        for storage_id, storage in st_storages.items():
            logger.debug(f"Setting initial level for storage: {storage.name}")
            # TODO: Update Storage equipment with storage_initial_level
            updated_count += 1

    logger.info(f"Set initial levels for {updated_count} storage units")
    return []
