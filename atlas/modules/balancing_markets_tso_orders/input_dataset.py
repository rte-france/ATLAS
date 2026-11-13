"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import TypeVar

from atlas.abstract_class.dataset import AbstractDataset
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.balancing_markets_tso_orders.parameters import TSOOrdersParameters

T = TypeVar("T")


class TSOOrdersInputDataset(AbstractDataset[TSOOrdersParameters]):
    def __init__(self, input_data: AtlasDataset, parameters: TSOOrdersParameters):
        self.parameters: TSOOrdersParameters = parameters
