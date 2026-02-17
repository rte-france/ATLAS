"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import PortfolioOptimisationModule
from atlas.abstract_class.abstract_module import AbstractModule
from atlas.modules.market_clearing.module import MarketClearingModule


class WorkflowHelper:
    """Utilities for workflow objects"""

    MODULE_REGISTRY: dict[str, type[AbstractModule]] = {
        "MarketClearing": MarketClearingModule,
        "PortfolioOptimisation": PortfolioOptimisationModule,
    }
