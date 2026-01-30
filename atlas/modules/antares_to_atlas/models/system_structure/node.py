"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Node, MarketArea, Portfolio and ControlBlock conversion.
"""

from typing import Any

from antares.craft.model.study import Study
from loguru import logger

from atlas.models.control_block import ControlBlock
from atlas.models.market.market_area import MarketArea
from atlas.models.node import Node
from atlas.models.portfolio import Portfolio
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def convert_nodes(
    study: Study,
    parameters: AntaresToAtlasParameters,
    shared_state: dict[str, Any],
) -> tuple[list[Node], list[MarketArea], list[Portfolio], list[ControlBlock]]:
    """Convert nodes and related structures from Antares to Atlas.

    Creates:
    - Nodes (geographical locations)
    - Market Areas (economic zones)
    - Portfolios (producer/consumer/both)
    - Control Blocks (operational zones)

    :param study: Antares study object from antares_craft
    :type study: Study
    :param parameters: Conversion parameters
    :type parameters: AntaresToAtlasParameters
    :param shared_state: Shared state dictionary
    :type shared_state: dict[str, Any]
    :return: Tuple of (nodes, market_areas, portfolios, control_blocks)
    :rtype: tuple[list[Node], list[MarketArea], list[Portfolio], list[ControlBlock]]
    """
    logger.info(f"Converting nodes for areas: {', '.join(parameters.market_areas)}")

    # Get all areas from the study
    areas = study.get_areas()

    nodes = []
    market_areas = []
    portfolios = []
    control_blocks = []

    # Store dicts for easy lookup by other converters
    nodes_dict = {}
    market_areas_dict = {}
    portfolios_dict = {}
    control_blocks_dict = {}

    for area_name in parameters.market_areas:
        if area_name not in areas:
            logger.warning(f"Area '{area_name}' not found in study")
            continue

        area = areas[area_name]
        logger.debug(f"Processing area: {area.name} (ID: {area.id})")

        # Create Control Block
        ctrl_block = ControlBlock(name=area_name)
        control_blocks.append(ctrl_block)
        control_blocks_dict[area_name] = ctrl_block

        # Create Market Area
        market_area = MarketArea(
            name=area_name,
            control_block=ctrl_block,
            # TODO: Set price limits
            # minimum_price=parameters.minimum_price,
            # maximum_price=parameters.maximum_price,
            # TODO: Set price forecasts if available from area data
            # price_forecast_medium=...,
        )
        market_areas.append(market_area)
        market_areas_dict[area_name] = market_area

        # Create Node
        node = Node(
            name=area_name,
            control_block=ctrl_block,
            market_area=market_area,
        )
        nodes.append(node)
        nodes_dict[area_name] = node

        # Create Portfolio(s)
        if parameters.consumption_production_separation:
            logger.debug(f"  Creating separate producer/consumer portfolios for {area_name}")

            # Generator portfolio
            portfolio_gen = Portfolio(
                name=f"generator_{area_name}",
                market_area=market_area,
                control_block=ctrl_block,
            )
            portfolios.append(portfolio_gen)
            portfolios_dict[f"generator_{area_name}"] = portfolio_gen

            # Supplier portfolio
            portfolio_load = Portfolio(
                name=f"supplier_{area_name}",
                market_area=market_area,
                control_block=ctrl_block,
            )
            portfolios.append(portfolio_load)
            portfolios_dict[f"supplier_{area_name}"] = portfolio_load
        else:
            logger.debug(f"  Creating unified portfolio for {area_name}")
            portfolio = Portfolio(
                name=f"portfolio_{area_name}",
                market_area=market_area,
                control_block=ctrl_block,
            )
            portfolios.append(portfolio)
            portfolios_dict[f"portfolio_{area_name}"] = portfolio

    logger.info(f"Converted {len(nodes)} nodes, {len(market_areas)} market areas, {len(portfolios)} portfolios")

    # Store only lookup dicts in shared state for other converters
    shared_state["nodes_dict"] = nodes_dict
    shared_state["portfolios_dict"] = portfolios_dict

    return nodes, market_areas, portfolios, control_blocks
