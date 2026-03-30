"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, field_validator, model_validator

from atlas.abstract_class.abstract_module import AbstractModule
from atlas.modules.day_ahead_orders.module import DayAheadOrdersModule
from atlas.modules.market_clearing.module import MarketClearingModule
from atlas.modules.portfolio_optimisation.module import PortfolioOptimisationModule

class ModuleRegistry(Enum):
    """Registry mapping module names to their implementation classes."""

    MarketClearing = MarketClearingModule
    PortfolioOptimisation = PortfolioOptimisationModule
    DayAheadOrders = DayAheadOrdersModule

    @classmethod
    def get(cls, name: str) -> type[AbstractModule]:
        try:
            return cls[name].value
        except KeyError:
            valid = [m.name for m in cls]
            raise ValueError(f"Unknown module: '{name}'. Valid modules are: {valid}") from None

    @classmethod
    def has_name(cls, name: str) -> bool:
        return name in cls._member_names_


class Step(BaseModel):
    """Definition of a single step

    :param name: Name identifying the step. Defaults to the module name if not provided.
    :type name: str
    :param parameters_path: Path to the parameters file for the step.
    :type parameters_path: str
    """

    name: str | None = None
    module: ModuleRegistry
    parameters_path: Path

    @field_validator("module", mode="before")
    @classmethod
    def coerce_module(cls, v: Any) -> ModuleRegistry:
        if isinstance(v, str):
            return ModuleRegistry(ModuleRegistry.get(v))
        return v

    @model_validator(mode="after")
    def set_default_name(self) -> Step:
        if self.name is None:
            self.name = self.module.name
        return self
