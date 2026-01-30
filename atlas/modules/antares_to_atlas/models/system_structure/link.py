"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Any

from antares.craft.model.study import Study
from loguru import logger

from atlas.models.business_model import BusinessModel
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def convert_links(
    study: Study,
    parameters: AntaresToAtlasParameters,
    shared_state: dict[str, Any],
) -> list[BusinessModel]:
    """Convert inter-area transmission links from Antares to Atlas."""
    logger.info("Converting inter-area links")

    links = study.get_links()
    nodes_dict = shared_state.get("nodes_dict", {})

    links_created = []
    for link_id, link in links.items():
        logger.debug(f"Processing link: {link_id}")

        # TODO: Create Atlas Link object
        # Need to check atlas/models for Link class
        # atlas_link = Link(
        #     name=link_id,
        #     from_node=nodes_dict.get(area_from),
        #     to_node=nodes_dict.get(area_to),
        #     # Extract properties from link object
        # )

        # links_created.append(atlas_link)

    logger.info(f"Processed {len(links_created)} links")
    return links_created
