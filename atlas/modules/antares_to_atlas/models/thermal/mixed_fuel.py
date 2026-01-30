"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Mixed fuel thermal units - BP23 specific.
Handles thermal units that can use multiple fuel types.
"""

from typing import Any

from antares.craft.model.study import Study
from loguru import logger

from atlas.models.equipment.thermal import Thermal
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def convert_mixed_fuel(
    study: Study,
    parameters: AntaresToAtlasParameters,
    shared_state: dict[str, Any],
) -> list[Thermal]:
    """Convert mixed fuel thermal units.

    Mixed fuel units are thermal clusters that can operate on different fuel types.
    This is typically identified by specific naming patterns or groups.
    """
    logger.info("Converting mixed fuel thermal units (BP23)")

    areas = study.get_areas()
    nodes_dict = shared_state.get("nodes_dict", {})
    portfolios_dict = shared_state.get("portfolios_dict", {})

    mixed_fuel_units = []
    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]
        thermals = area.get_thermals()

        for thermal_id, thermal in thermals.items():
            props = thermal.properties

            # Identify mixed fuel units (e.g., units with "mixed" in name or specific groups)
            if "mixed" not in thermal.name.lower():
                continue

            if not props.enabled or props.nominal_capacity * props.unit_count == 0.0:
                continue

            logger.debug(f"Processing mixed fuel unit: {thermal.name}")

            # Mixed fuel units need special handling - they can switch between fuel types
            # TODO: This might require multiple Thermal objects or special attributes
            # For now, create as regular thermal with note

            mixed_fuel_units.append(thermal.name)

    logger.info(f"Processed {len(mixed_fuel_units)} mixed fuel units")
    return []  # Return empty for now - needs clarification on Atlas model
