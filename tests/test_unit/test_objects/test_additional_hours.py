"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
import pytest
from pydantic import ValidationError

from atlas.enums import MarketType
from atlas.objects.equipment.equipment import AdditionalHours
from atlas.objects.equipment.wind import Wind
from atlas.objects.market.market_area import MarketArea
from atlas.objects.market_operator.portfolio import Portfolio
from atlas.objects.network.node import Node
from atlas.objects.network_operator.control_block import ControlBlock

TIME_FRAMES = ["day_ahead", "intraday", "rr_activation", "mfrr_activation", "specific_activation"]


def _wind(additional_hours: object) -> Wind:
    control_block = ControlBlock(name="cb")
    market_area = MarketArea(name="ma", control_block=control_block)
    portfolio = Portfolio(name="pf", control_block=control_block, market_area=market_area)
    node = Node(name="node", control_block=control_block, market_area=market_area)
    return Wind(name="wind", node=node, portfolio=portfolio, additional_hours=additional_hours)


class TestParsing:
    @pytest.mark.parametrize("value", ["PT12H", " PT12H ", "12h", pendulum.duration(hours=12)])
    def test_single_duration_applies_to_every_time_frame(self, value):
        hours = AdditionalHours.model_validate(value)
        assert all(getattr(hours, name) == pendulum.duration(hours=12) for name in TIME_FRAMES)

    def test_key_value_string(self):
        hours = AdditionalHours.model_validate("day_ahead=PT12H| intraday = P2D")
        assert hours.day_ahead == pendulum.duration(hours=12)
        assert hours.intraday == pendulum.duration(days=2)
        assert hours.rr_activation is None
        assert hours.mfrr_activation is None
        assert hours.specific_activation is None

    def test_keyword_arguments(self):
        hours = AdditionalHours(rr_activation="PT1H")
        assert hours.rr_activation == pendulum.duration(hours=1)
        assert hours.day_ahead is None

    @pytest.mark.parametrize(
        "value",
        [
            "unknown=PT1H",
            "day_ahead=PT1H|day_ahead=PT2H",
            "day_ahead=PT1H|PT2H",
            "day_ahead=-PT1H",
        ],
    )
    def test_invalid_values_raise(self, value):
        with pytest.raises(ValidationError):
            AdditionalHours.model_validate(value)

    def test_uniform(self):
        hours = AdditionalHours.uniform(pendulum.duration(hours=3))
        assert all(getattr(hours, name) == pendulum.duration(hours=3) for name in TIME_FRAMES)


class TestSerialization:
    @pytest.mark.parametrize(
        ("hours", "expected"),
        [
            (AdditionalHours.uniform(pendulum.duration(hours=12)), "PT12H"),
            (AdditionalHours.uniform(pendulum.duration(days=2)), "P2D"),
            (AdditionalHours(day_ahead="PT12H", intraday="PT6H"), "day_ahead=PT12H|intraday=PT6H"),
            (
                AdditionalHours(day_ahead="PT1H", intraday="PT1H", rr_activation="PT1H", mfrr_activation="PT1H"),
                "day_ahead=PT1H|intraday=PT1H|rr_activation=PT1H|mfrr_activation=PT1H",
            ),
            (AdditionalHours(), None),
        ],
    )
    def test_json_dump(self, hours, expected):
        assert hours.model_dump(mode="json") == expected

    @pytest.mark.parametrize("text", ["PT12H", "day_ahead=PT12H|intraday=PT6H", "rr_activation=P6D"])
    def test_round_trip(self, text):
        hours = AdditionalHours.model_validate(text)
        assert AdditionalHours.model_validate(hours.model_dump(mode="json")) == hours

    def test_python_dump_keeps_fields(self):
        hours = AdditionalHours(day_ahead="PT12H")
        assert hours.model_dump()["day_ahead"] == pendulum.duration(hours=12)

    def test_equipment_json_dump_is_a_single_string(self):
        wind = _wind("day_ahead=PT12H|intraday=PT6H")
        assert wind.model_dump(mode="json")["additional_hours"] == "day_ahead=PT12H|intraday=PT6H"


class TestEquipmentField:
    def test_string_is_parsed_on_equipment(self):
        assert _wind("PT12H").additional_hours == AdditionalHours.uniform(pendulum.duration(hours=12))

    def test_none_is_kept(self):
        assert _wind(None).additional_hours is None

    def test_assignment_of_a_duration_is_parsed(self):
        wind = _wind(None)
        wind.additional_hours = pendulum.duration(hours=2)  # type: ignore[assignment]
        assert wind.additional_hours == AdditionalHours.uniform(pendulum.duration(hours=2))


class TestForMarket:
    @pytest.mark.parametrize(
        ("market", "expected_hours"),
        [
            (MarketType.dayahead, 1),
            (MarketType.intraday, 2),
            (MarketType.rr_activation, 3),
            (MarketType.mfrr_activation, 4),
        ],
    )
    def test_returns_matching_time_frame(self, market, expected_hours):
        hours = AdditionalHours(
            day_ahead="PT1H", intraday="PT2H", rr_activation="PT3H", mfrr_activation="PT4H", specific_activation="PT5H"
        )
        assert hours.for_market(market) == pendulum.duration(hours=expected_hours)

    def test_returns_none_when_undefined(self):
        assert AdditionalHours(day_ahead="PT1H").for_market(MarketType.intraday) is None


class TestFillMissing:
    def test_only_undefined_time_frames_are_filled(self):
        hours = AdditionalHours(day_ahead="PT1H").fill_missing(pendulum.duration(hours=12))
        assert hours.day_ahead == pendulum.duration(hours=1)
        assert all(getattr(hours, name) == pendulum.duration(hours=12) for name in TIME_FRAMES[1:])

    def test_original_is_not_modified(self):
        hours = AdditionalHours(day_ahead="PT1H")
        hours.fill_missing(pendulum.duration(hours=12))
        assert hours.intraday is None
