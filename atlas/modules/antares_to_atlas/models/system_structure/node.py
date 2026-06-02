"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Node, MarketArea, Portfolio and ControlBlock conversion.
"""

from antares.craft import Frequency, MCIndAreasDataType
from antares.craft.model.study import Study
from loguru import logger

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.objects.market.market_area import MarketArea
from atlas.objects.market_operator.portfolio import Portfolio
from atlas.objects.network.node import Node
from atlas.objects.network_operator.control_block import ControlBlock


def convert_system_structure(
    study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset
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
    :return: atlas_dataset with converted nodes, market areas, portfolios, and control blocks
    :rtype: AtlasDataset
    """
    logger.info(f"Converting nodes for areas: {', '.join(parameters.market_areas)}")

    areas = study.get_areas()

    nodes: list[Node] = []
    market_areas: list[MarketArea] = []
    portfolios: list[Portfolio] = []
    control_blocks: list[ControlBlock] = []
    study_output = study.get_output(parameters.output_name)

    for area_name in parameters.market_areas:
        if area_name not in areas:
            logger.warning(f"Area '{area_name}' not found in study")
            continue

        area = areas[area_name]
        logger.debug(f"Processing area: {area.id}")

        # Create Control Block
        ctrl_block = ControlBlock(name=area_name, volume_uncertainty=False)

        try:
            marginal_price = study_output.get_mc_ind_area(
                parameters.scenario, frequency=Frequency.HOURLY, data_type=MCIndAreasDataType.VALUES, area=area.id
            )[(parameters.output.marginal_price_column, "Euro")]
        except Exception as e:
            logger.warning(
                f"Could not get marginal price for area {area_name} (scenario {parameters.scenario}): {e}. Skipping area."
            )
            continue

        control_blocks.append(ctrl_block)

        market_area = MarketArea(
            name=area_name,
            control_block=ctrl_block,
            price_forecast_medium=ForecastingMatrix().add(
                index=parameters.execution_date,
                timeseries=Timeseries.from_values(
                    start_date=parameters.start_date, frequency="1h", values=marginal_price
                ),
            ),
            minimum_price=Timeseries.from_index(
                parameters.start_date,
                frequency="1y",
                end_date=parameters.start_date.add(years=1),
                default_value=parameters.minimum_price,
            ),
            maximum_price=Timeseries.from_index(
                parameters.start_date,
                frequency="1y",
                end_date=parameters.start_date.add(years=1),
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

    atlas_dataset.control_block.add(control_blocks)
    atlas_dataset.node.add(nodes)
    atlas_dataset.portfolio.add(portfolios)
    atlas_dataset.market_area.add(market_areas)

    return atlas_dataset
