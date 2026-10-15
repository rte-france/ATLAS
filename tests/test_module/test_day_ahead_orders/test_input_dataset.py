"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum

from atlas.modules.day_ahead_orders.input_dataset import _day_ahead_fields
from atlas.objects.equipment.equipment import AdditionalHours
from atlas.objects.equipment.wind import Wind
from atlas.objects.market.market_area import MarketArea
from atlas.objects.market_operator.portfolio import Portfolio
from atlas.objects.network.node import Node
from atlas.objects.network_operator.control_block import ControlBlock


def _wind(additional_hours: AdditionalHours | None) -> Wind:
    control_block = ControlBlock(name="cb")
    market_area = MarketArea(name="ma", control_block=control_block)
    portfolio = Portfolio(name="pf", control_block=control_block, market_area=market_area)
    node = Node(name="node", control_block=control_block, market_area=market_area)
    return Wind(name="wind", node=node, portfolio=portfolio, additional_hours=additional_hours)


def test_day_ahead_time_frame_is_always_selected():
    wind = _wind(AdditionalHours(day_ahead="PT12H", intraday="PT1H", rr_activation="PT2H"))
    assert _day_ahead_fields(wind)["additional_hours"] == pendulum.duration(hours=12)


def test_undefined_additional_hours_is_kept():
    assert _day_ahead_fields(_wind(None))["additional_hours"] is None
