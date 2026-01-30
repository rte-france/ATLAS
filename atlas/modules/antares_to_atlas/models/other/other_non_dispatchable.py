"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Any

from antares.craft.model.study import Study
from loguru import logger

from atlas.models.equipment.other_non_dispatchable import OtherNonDispatchable
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def convert_other_non_dispatchable_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    shared_state: dict[str, Any],
) -> list[OtherNonDispatchable]:
    """Convert other non-dispatchable generation units from Antares to Atlas."""
    logger.info("Converting non-dispatchable generation units")

    areas_dict = shared_state.get("areas", study.get_areas())
    nodes_dict = shared_state.get("nodes_dict", {})
    portfolios_dict = shared_state.get("portfolios_dict", {})

    non_disp_units = []
    for area_name in parameters.market_areas:
        if area_name not in areas_dict:
            continue

        area = areas_dict[area_name]
        renewables = area.get_renewables()

        for renewable_id, renewable in renewables.items():
            name_lower = renewable.name.lower()
            if any(keyword in name_lower for keyword in ["wind", "vent", "solar", "pv"]):
                continue

            props = renewable.properties
            logger.debug(f"Processing non-dispatchable: {renewable.name}")

            equipment = OtherNonDispatchable(
                name=renewable.name,
                node=nodes_dict.get(area_name),
                portfolio=portfolios_dict.get(
                    f"generator_{area_name}"
                    if parameters.consumption_production_separation
                    else f"portfolio_{area_name}"
                ),
                installed_capacity=props.nominal_capacity,
            )

            non_disp_units.append(equipment)

    logger.info(f"Converted {len(non_disp_units)} non-dispatchable units")
    return non_disp_units
