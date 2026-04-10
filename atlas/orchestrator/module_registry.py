"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from enum import Enum

from atlas.abstract_class.module import AbstractModule
from atlas.modules.day_ahead_orders.module import DayAheadOrdersModule
from atlas.modules.intraday_price_forecast.module import IntradayPriceForecastModule
from atlas.modules.market_clearing.module import MarketClearingModule
from atlas.modules.portfolio_optimisation.module import PortfolioOptimisationModule


class ModuleRegistry(Enum):
    """Registry mapping module names to their implementation classes."""

    MarketClearing = MarketClearingModule
    PortfolioOptimisation = PortfolioOptimisationModule
    DayAheadOrders = DayAheadOrdersModule
    IntradayPriceForecast = IntradayPriceForecastModule

    @classmethod
    def get(cls, name: str) -> type[AbstractModule]:
        try:
            return cls[name].value
        except KeyError:
            valid = [m.name for m in cls]
            raise ValueError(f"Unknown module: '{name}'. Valid modules are: {valid}") from None

    @classmethod
    def get_names(cls) -> list[str]:
        """Return list of valid module names for CLI choices."""
        return [m.name for m in cls]
