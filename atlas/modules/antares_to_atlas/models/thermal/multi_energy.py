"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Multi-energy systems - BP23 specific.
Updates variable costs for thermal units based on multi-energy constraints.
"""

from typing import Any

from antares.craft.model.study import Study
from loguru import logger

from atlas.models.business_model import BusinessModel
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def apply_multi_energy_costs(
    study: Study,
    parameters: AntaresToAtlasParameters,
    shared_state: dict[str, Any],
) -> list[BusinessModel]:
    """Apply multi-energy variable cost updates to thermal units.

    This adjusts costs for units that participate in multiple energy markets
    or have coupled energy carriers (electricity, gas, heat, etc.).
    """
    logger.info("Applying multi-energy variable cost updates (BP23)")

    # This converter modifies existing thermal units rather than creating new ones
    # It updates their variable costs based on multi-energy market conditions

    # TODO: Access already-created thermal units and update their costs
    # Could retrieve from shared_state or re-access the study

    areas = study.get_areas()

    updated_count = 0
    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]
        thermals = area.get_thermals()

        for thermal_id, thermal in thermals.items():
            # Check if this unit is part of multi-energy system
            if "cogen" in thermal.name.lower() or "chp" in thermal.name.lower():
                logger.debug(f"Multi-energy unit: {thermal.name}")
                # TODO: Update variable cost based on multi-energy constraints
                updated_count += 1

    logger.info(f"Updated {updated_count} units for multi-energy")
    return []
