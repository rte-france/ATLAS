"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Any

from antares.craft.model.study import Study
from loguru import logger

from atlas.models.equipment.solar import Solar
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def convert_pv_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    shared_state: dict[str, Any],
) -> list[Solar]:
    """Convert PV generation data from Antares to Atlas."""
    logger.info("Converting PV generation data")

    areas_dict = shared_state.get("areas", study.get_areas())
    nodes_dict = shared_state.get("nodes_dict", {})
    portfolios_dict = shared_state.get("portfolios_dict", {})

    pv_units = []
    for area_name in parameters.market_areas:
        if area_name not in areas_dict:
            continue

        area = areas_dict[area_name]
        renewables = area.get_renewables()

        for renewable_id, renewable in renewables.items():
            if "solar" not in renewable.name.lower() and "pv" not in renewable.name.lower():
                continue

            props = renewable.properties
            logger.debug(f"Processing PV: {renewable.name}")

            equipment = Solar(
                name=renewable.name,
                node=nodes_dict.get(area_name),
                portfolio=portfolios_dict.get(
                    f"generator_{area_name}"
                    if parameters.consumption_production_separation
                    else f"portfolio_{area_name}"
                ),
                installed_capacity=props.nominal_capacity,
                # TODO: curtailment parameters
                # maximum_curtailment_ratio=...,
                # curtailment_cost=...,
            )

            pv_units.append(equipment)

    logger.info(f"Converted {len(pv_units)} PV units")
    return pv_units
