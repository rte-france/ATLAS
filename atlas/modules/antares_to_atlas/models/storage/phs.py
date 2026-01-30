"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Any

from antares.craft.model.study import Study
from loguru import logger

from atlas.enum import StorageType
from atlas.models.equipment.storage import Storage
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def convert_phs(
    study: Study,
    parameters: AntaresToAtlasParameters,
    shared_state: dict[str, Any],
) -> list[Storage]:
    """Convert pumped hydro storage from Antares to Atlas."""
    logger.info("Converting pumped hydro storage (BP23)")

    areas = study.get_areas()
    nodes_dict = shared_state.get("nodes_dict", {})
    portfolios_dict = shared_state.get("portfolios_dict", {})

    phs_units = []
    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]
        st_storages = area.get_st_storages()

        for storage_id, storage in st_storages.items():
            # Filter for PHS (by name)
            if "phs" not in storage.name.lower() and "step" not in storage.name.lower():
                continue

            props = storage.properties
            logger.debug(f"Processing PHS: {storage.name}")

            phs = Storage(
                name=storage.name,
                node=nodes_dict.get(area_name),
                portfolio=portfolios_dict.get(
                    f"generator_{area_name}"
                    if parameters.consumption_production_separation
                    else f"portfolio_{area_name}"
                ),
                storage_type=StorageType.PUMPED_HYDRAULIC_STORAGE,
                charge_efficiency=props.efficiency if hasattr(props, "efficiency") else 0.75,
                discharge_efficiency=props.efficiency if hasattr(props, "efficiency") else 0.9,
                # TODO: Extract properties
            )

            phs_units.append(phs)

    logger.info(f"Converted {len(phs_units)} PHS units")
    return phs_units
