"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Demand-Side Response - BP23 specific.
"""

from typing import Any

from antares.craft.model.study import Study
from loguru import logger

from atlas.models.equipment.load import Load
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def convert_dsr(
    study: Study,
    parameters: AntaresToAtlasParameters,
    shared_state: dict[str, Any],
) -> list[Load]:
    """Convert demand-side response units.

    DSR is typically modeled as flexible load or could be in st_storages.
    """
    logger.info("Converting demand-side response (BP23)")

    areas = study.get_areas()
    nodes_dict = shared_state.get("nodes_dict", {})
    portfolios_dict = shared_state.get("portfolios_dict", {})

    dsr_units = []
    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]

        # Check st_storages for DSR-like units
        st_storages = area.get_st_storages()
        for storage_id, storage in st_storages.items():
            if "dsr" in storage.name.lower() or "demand" in storage.name.lower():
                logger.debug(f"Found DSR in storage: {storage.name}")
                # TODO: Create Load or Storage object for DSR

        # Check renewables for DSR (sometimes modeled there)
        renewables = area.get_renewables()
        for renewable_id, renewable in renewables.items():
            if "dsr" in renewable.name.lower():
                logger.debug(f"Found DSR in renewables: {renewable.name}")
                # TODO: Create Load object for DSR

    logger.info(f"Processed {len(dsr_units)} DSR units")
    return []
