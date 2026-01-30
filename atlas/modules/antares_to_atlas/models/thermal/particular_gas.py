"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Particular mid/peak gas units - BP23 specific.
"""

from typing import Any

from antares.craft.model.study import Study
from loguru import logger

from atlas.models.equipment.thermal import Thermal
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def convert_particular_mid_peak(
    study: Study,
    parameters: AntaresToAtlasParameters,
    shared_state: dict[str, Any],
) -> list[Thermal]:
    """Convert particular mid/peak gas generation units.

    These are specific gas units used for mid-merit or peak operation.
    Identified by naming patterns or operational characteristics.
    """
    logger.info("Converting particular mid/peak gas units (BP23)")

    areas = study.get_areas()
    nodes_dict = shared_state.get("nodes_dict", {})
    portfolios_dict = shared_state.get("portfolios_dict", {})

    mid_peak_units = []
    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]
        thermals = area.get_thermals()

        for thermal_id, thermal in thermals.items():
            props = thermal.properties

            # Look for mid/peak specific units
            name_lower = thermal.name.lower()
            if not any(keyword in name_lower for keyword in ["mid", "peak", "ocgt"]):
                continue

            if props.group != "gas":
                continue

            if not props.enabled or props.nominal_capacity * props.unit_count == 0.0:
                continue

            logger.debug(f"Processing mid/peak gas: {thermal.name}")

            # These units might need special start-up characteristics or bid strategies
            # Already created in main thermal converter, this might just tag/modify them

    logger.info(f"Processed {len(mid_peak_units)} mid/peak gas units")
    return []
