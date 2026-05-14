"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.modules.intraday_orders.input_objects.wind import WindIDO
from atlas.modules.intraday_orders.orders_formulation.abstract_orders_with_curtailment import (
    AbstractOrdersFormulatorWithCurtailment,
)


class WindOrdersFormulator(AbstractOrdersFormulatorWithCurtailment[WindIDO]):
    EQUIPMENT_TYPE_NAME = "wind"
    ORDER_NAME_TEMPLATE = "wind_IDOrder_{}_{}_{}"
    CURTAILMENT_ORDER_NAME_TEMPLATE = "wind_curt_IDOrder_{}_{}_{}"
