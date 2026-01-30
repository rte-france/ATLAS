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


def convert_electric_vehicles(
    study: Study,
    parameters: AntaresToAtlasParameters,
    shared_state: dict[str, Any],
) -> list[Storage]:
    """Convert electric vehicle storage from Antares to Atlas."""
    logger.info("Converting electric vehicle storage (BP23)")

    areas = study.get_areas()
    nodes_dict = shared_state.get("nodes_dict", {})
    portfolios_dict = shared_state.get("portfolios_dict", {})

    evs = []
    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]
        st_storages = area.get_st_storages()

        for storage_id, storage in st_storages.items():
            # Filter for EVs (by name)
            if "ev" not in storage.name.lower() and "vehicle" not in storage.name.lower():
                continue

            props = storage.properties
            logger.debug(f"Processing EV: {storage.name}")

            ev = Storage(
                name=storage.name,
                node=nodes_dict.get(area_name),
                portfolio=portfolios_dict.get(
                    f"supplier_{area_name}"
                    if parameters.consumption_production_separation
                    else f"portfolio_{area_name}"
                ),
                storage_type=StorageType.ELECTRIC_VEHICLE,
                is_v2g=True,  # BP23 specific
                charge_efficiency=props.efficiency if hasattr(props, "efficiency") else 0.9,
                discharge_efficiency=props.efficiency if hasattr(props, "efficiency") else 0.9,
                # TODO: Extract properties
                # displacement_energy=...,
            )

            evs.append(ev)

    logger.info(f"Converted {len(evs)} electric vehicles")
    return evs
