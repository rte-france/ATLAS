"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.study import Study
from loguru import logger

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.timeseries import Timeseries
from atlas.models.market.market_border import MarketBorder
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def convert_links(study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
    """Convert inter-area transmission links from Antares to Atlas."""
    logger.info("Converting inter-area links")

    links = study.get_links()
    market_borders = []

    for link_name, link in links.items():
        logger.debug(f"Processing link: {link_name}")

        if not (link.UphillNode.Name in parameters.market_areas and link.DownhillNode.Name in parameters.market_areas):
            continue
        if (
            link.get_capacity_direct().abs().max().item() == 0
            and link.get_capacity_indirect().abs().max().item() == 0.0
        ):
            continue

        node_1 = atlas_dataset.get("node", link.UphillNode.Name)
        node_2 = atlas_dataset.get("node", link.DownhillNode.Name)
        ctrl_block_1 = atlas_dataset.get("control_block", link.UphillNode.Name)
        ctrl_block_2 = atlas_dataset.get("control_block", link.DownhillNode.Name)

        market_borders.append(
            MarketBorder(
                name=link_name,
                uphill_market_area=node_1,
                downhill_market_area=node_2,
                uphill_control_block=ctrl_block_1,
                downhill_control_block=ctrl_block_2,
                maximum_flow=Timeseries.from_values(
                    parameters.start_date, frequency="1h", values=link.get_capacity_direct()[0].to_list()
                ),
                minimum_flow=Timeseries.from_values(
                    parameters.start_date, frequency="1h", values=link.get_capacity_indirect()[0].to_list()
                )
                * (-1),
            )
        )
    atlas_dataset.market_border = market_borders

    return atlas_dataset
