"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.modules.intraday_orders.input_objects.solar import SolarIDO
from atlas.modules.intraday_orders.orders_formulation.abstract_orders_with_curtailment import (
    AbstractOrdersFormulatorWithCurtailment,
)


class SolarOrdersFormulator(AbstractOrdersFormulatorWithCurtailment[SolarIDO]):
    EQUIPMENT_TYPE_NAME = "solar"
    ORDER_NAME_TEMPLATE = "pv_id_order_{}_{}_{}"
    CURTAILMENT_ORDER_NAME_TEMPLATE = "pv_curt_id_order_{}_{}_{}"
