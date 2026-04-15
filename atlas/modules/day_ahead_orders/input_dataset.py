"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import TypeVar

from atlas.abstract_class.dataset import AbstractDataset
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.day_ahead_orders.input_objects.hydro import HydroDAO
from atlas.modules.day_ahead_orders.input_objects.load import LoadDAO
from atlas.modules.day_ahead_orders.input_objects.portfolio import PortfolioDAO
from atlas.modules.day_ahead_orders.input_objects.solar import SolarDAO
from atlas.modules.day_ahead_orders.input_objects.storage import StorageDAO
from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.input_objects.wind import WindDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.objects.equipment.other_non_dispatchable import OtherNonDispatchable
from atlas.objects.market.market_area import MarketArea
from atlas.objects.network_operator.control_block import ControlBlock

T = TypeVar("T")


def convert_with_portfolio_map(
    equipment_list: list, dao_class: type[T], portfolio_map: dict[str, PortfolioDAO]
) -> list[T]:
    result = []
    for obj in equipment_list:
        obj_dict = dict(obj)
        obj_dict["portfolio"] = portfolio_map[obj.portfolio.name]
        result.append(dao_class(**obj_dict))
    return result


class DayAheadOrdersInputDataset(AbstractDataset[DayAheadOrdersParameters]):
    def __init__(self, raw_data: AtlasDataset, parameters: DayAheadOrdersParameters):
        self.parameters: DayAheadOrdersParameters = parameters
        self.control_block: list[ControlBlock] = raw_data.control_block.all()
        self.other_non_dispatchable: list[OtherNonDispatchable] = raw_data.other_non_dispatchable.all()
        self.market_area: list[MarketArea] = [MarketArea(**dict(obj)) for obj in raw_data.market_area]

        # Create portfolio mapping to avoid duplicate instantiation
        portfolio_map: dict[str, PortfolioDAO] = {}
        for portfolio in raw_data.portfolio:
            portfolio_dict = dict(portfolio)
            portfolio_dict["market_area"] = MarketArea(**dict(portfolio.market_area))  # type: ignore [arg-type]
            portfolio_map[portfolio.name] = PortfolioDAO(**portfolio_dict)

        self.portfolio: list[PortfolioDAO] = list(portfolio_map.values())

        self.wind: list[WindDAO] = convert_with_portfolio_map(raw_data.wind.all(), WindDAO, portfolio_map)
        self.storage: list[StorageDAO] = convert_with_portfolio_map(raw_data.storage.all(), StorageDAO, portfolio_map)
        self.hydro: list[HydroDAO] = convert_with_portfolio_map(raw_data.hydro.all(), HydroDAO, portfolio_map)
        self.solar: list[SolarDAO] = convert_with_portfolio_map(raw_data.solar.all(), SolarDAO, portfolio_map)
        self.thermal: list[ThermalDAO] = convert_with_portfolio_map(raw_data.thermal.all(), ThermalDAO, portfolio_map)
        self.load: list[LoadDAO] = convert_with_portfolio_map(raw_data.load.all(), LoadDAO, portfolio_map)
