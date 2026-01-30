"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Power-to-Gas conversion - BP23 specific.
"""

from typing import Any

from antares.craft.model.study import Study
from loguru import logger

from atlas.models.equipment.storage import Storage
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def convert_p2g(
    study: Study,
    parameters: AntaresToAtlasParameters,
    shared_state: dict[str, Any],
) -> list[Storage]:
    """Convert Power-to-Gas units.

    P2G converts electricity to gas (hydrogen, methane, etc.).
    May be modeled as st_storage or special thermal/renewable clusters.
    """
    logger.info("Converting power-to-gas units (BP23)")

    areas = study.get_areas()
    nodes_dict = shared_state.get("nodes_dict", {})
    portfolios_dict = shared_state.get("portfolios_dict", {})

    p2g_units = []
    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]

        # Check st_storages for P2G
        st_storages = area.get_st_storages()
        for storage_id, storage in st_storages.items():
            if "p2g" in storage.name.lower() or "hydrogen" in storage.name.lower() or "h2" in storage.name.lower():
                props = storage.properties
                logger.debug(f"Found P2G: {storage.name}")

                # TODO: Create appropriate model for P2G
                # Might be Storage or custom equipment type

        # Check renewables for P2G (sometimes modeled as negative load)
        renewables = area.get_renewables()
        for renewable_id, renewable in renewables.items():
            if "p2g" in renewable.name.lower() or "electrolyz" in renewable.name.lower():
                logger.debug(f"Found P2G in renewables: {renewable.name}")

    logger.info(f"Processed {len(p2g_units)} P2G units")
    return []
