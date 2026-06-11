"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.study import Study
from loguru import logger

from atlas.core.io_utils.atlas_dataset import AtlasDataset
from atlas.core.math.timeseries import Timeseries
from atlas.enums import CouplingType
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.objects.market.market_border import MarketBorder


def convert_links(study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
    """Convert inter-area transmission links from Antares to Atlas."""
    logger.info("Converting inter-area links")

    links = study.get_links()
    market_borders: list[MarketBorder] = []

    for link_name, link in links.items():
        logger.debug(f"Processing link: {link_name}")
        uphill_node = link.area_from_id
        downhill_node = link.area_to_id

        if not (uphill_node in parameters.market_areas and downhill_node in parameters.market_areas):
            continue
        if link.get_capacity_direct()[0].abs().max() == 0 and link.get_capacity_indirect()[0].abs().max() == 0.0:
            continue

        node_1 = atlas_dataset.get("market_area", uphill_node)
        node_2 = atlas_dataset.get("market_area", downhill_node)
        ctrl_block_1 = atlas_dataset.get("control_block", uphill_node)
        ctrl_block_2 = atlas_dataset.get("control_block", downhill_node)

        market_borders.append(
            MarketBorder(
                name=link_name.replace(" / ", "_"),
                uphill_market_area=node_1,
                downhill_market_area=node_2,
                uphill_control_block=ctrl_block_1,
                downhill_control_block=ctrl_block_2,
                coupling_type=CouplingType.ATC,
                loss_factor=0.0,
                time_resolution=0.0,
                maximum_flow=Timeseries.from_values(
                    parameters.start_date, frequency="1h", values=link.get_capacity_direct()[0]
                ),
                minimum_flow=Timeseries.from_values(
                    parameters.start_date, frequency="1h", values=link.get_capacity_indirect()[0]
                )
                * (-1),
            )
        )

    logger.info(f"Converted {len(market_borders)} inter-area links")
    atlas_dataset.market_border.add(market_borders)

    return atlas_dataset
