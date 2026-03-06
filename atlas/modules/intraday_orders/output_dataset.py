"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import BusinessModel
from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters


class IntradayOrdersOutputDataset(AbstractDataset[IntradayOrdersParameters]):
    pass
