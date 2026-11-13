"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.abstract_class.dataset import ModuleResult
from atlas.modules.balancing_markets_tso_orders.input_dataset import TSOOrdersInputDataset
from atlas.modules.balancing_markets_tso_orders.parameters import TSOOrdersParameters


class TSOOrdersResult(ModuleResult[TSOOrdersParameters]):
    def __init__(self, input_dataset: TSOOrdersInputDataset, parameters: TSOOrdersParameters) -> None:
        self.parameters: TSOOrdersParameters = input_dataset.parameters
