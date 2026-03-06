"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.abstract_class.abstract_dataset import AbstractModuleOutput
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters


class IntradayOrdersOutputDataset(AbstractModuleOutput[IntradayOrdersParameters]):
    def build_change_sets(self) -> None:
        pass
