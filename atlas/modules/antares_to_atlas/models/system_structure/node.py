"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Node, MarketArea, Portfolio and ControlBlock conversion.
"""

from antares.craft.model.study import Study
from loguru import logger
from pendulum import duration

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.control_block import ControlBlock
from atlas.models.market.market_area import MarketArea
from atlas.models.node import Node
from atlas.models.portfolio import Portfolio
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def convert_system_structure(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
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
    :param atlas_dataset: Atlas dataset
    :type atlas_dataset: AtlasDataset
    :return: Tuple of (nodes, market_areas, portfolios, control_blocks)
    :rtype: tuple[list[Node], list[MarketArea], list[Portfolio], list[ControlBlock]]
    """
    logger.info(f"Converting nodes for areas: {', '.join(parameters.market_areas)}")

    areas = study.get_areas()

    nodes: list[Node] = []
    market_areas: list[MarketArea] = []
    portfolios: list[Portfolio] = []
    control_blocks: list[ControlBlock] = []

    for area_name in parameters.market_areas:
        if area_name not in areas:
            logger.warning(f"Area '{area_name}' not found in study")
            continue

        area = areas[area_name]
        logger.debug(f"Processing area: {area.name} (ID: {area.id})")

        # Create Control Block
        ctrl_block = ControlBlock(name=area_name)
        control_blocks.append(ctrl_block)

        if str(parameters.scenario) in area.CalculatedMarginalPrice.Index:
            market_area = MarketArea(
                name=area_name,
                control_block=ctrl_block,
                price_forecast_medium=ForecastingMatrix().add(
                    index=parameters.execution_date,
                    timeseries=area.CalculatedMarginalPrice.GetTimeSeriesByName(str(parameters.scenario)),  # TODO
                ),
                minimum_price=Timeseries.from_index(
                    parameters.start_date,
                    frequency="1h",
                    end_date=parameters.start_date + duration(years=1),
                    default_value=parameters.minimum_price,
                ),
                maximum_price=Timeseries.from_index(
                    parameters.start_date,
                    frequency="1h",
                    end_date=parameters.start_date + duration(years=1),
                    default_value=parameters.maximum_price,
                ),
            )
        market_areas.append(market_area)

        # Create Node
        node = Node(
            name=area_name,
            control_block=ctrl_block,
            market_area=market_area,
        )
        nodes.append(node)

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

            # Supplier portfolio
            portfolio_load = Portfolio(
                name=f"supplier_{area_name}",
                market_area=market_area,
                control_block=ctrl_block,
            )
            portfolios.append(portfolio_load)
        else:
            logger.debug(f"  Creating unified portfolio for {area_name}")
            portfolio = Portfolio(
                name=f"portfolio_{area_name}",
                market_area=market_area,
                control_block=ctrl_block,
            )
            portfolios.append(portfolio)

    logger.info(f"Converted {len(nodes)} nodes, {len(market_areas)} market areas, {len(portfolios)} portfolios")

    return AtlasDataset(control_block=control_blocks, node=nodes, portfolio=portfolios, market_area=market_areas)
