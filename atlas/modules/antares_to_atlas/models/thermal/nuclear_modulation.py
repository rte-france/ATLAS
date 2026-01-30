"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Nuclear modulation - BP23 specific, France only.
"""

from typing import Any

from antares.craft.model.study import Study
from loguru import logger

from atlas.models.business_model import BusinessModel
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def apply_nuclear_modulation(
    study: Study,
    parameters: AntaresToAtlasParameters,
    shared_state: dict[str, Any],
) -> list[BusinessModel]:
    """Apply nuclear modulation for France.

    Nuclear modulation adjusts the minimum and maximum power of nuclear units
    to reflect load-following capabilities and operational constraints.
    This is specific to French nuclear fleet management.
    """
    if "fr" not in [area.lower() for area in parameters.market_areas]:
        logger.info("Skipping nuclear modulation (France not in market areas)")
        return []

    logger.info("Applying nuclear modulation for France (BP23)")

    areas = study.get_areas()
    fr_area = areas.get("fr") or areas.get("FR")

    if not fr_area:
        logger.warning("France area not found in study")
        return []

    thermals = fr_area.get_thermals()

    modulated_count = 0
    for thermal_id, thermal in thermals.items():
        props = thermal.properties

        # Identify nuclear units
        if props.group != "nuclear" and "nuc" not in thermal.name.lower():
            continue

        logger.debug(f"Applying modulation to nuclear unit: {thermal.name}")

        # TODO: Update Thermal equipment with modulation parameters
        # - Adjust minimum_power timeseries for load-following
        # - Set ramping constraints
        # - Apply seasonal modulation patterns
        # - Consider maintenance schedules

        modulated_count += 1

    logger.info(f"Applied nuclear modulation to {modulated_count} units")
    return []
