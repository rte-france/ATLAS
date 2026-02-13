"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import PortfolioOptimisationModule
from atlas.modules.market_clearing.module import MarketClearingModule


class WorkflowHelper:
    """Utilities for workflow objects"""

    MODULE_REGISTRY = {"MarketClearing": MarketClearingModule, "PortfolioOptimisation": PortfolioOptimisationModule}
