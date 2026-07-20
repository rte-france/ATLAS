"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

End-to-end smoke + structural assertions on the MarketClearing module run.
This is the safety net for the upcoming module refactor: any change that
silently drops orders, scrambles output keys, or breaks change-set generation
should fail here.
"""

import math

import pytest

from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.input_objects.market_area import INITIAL_MAX_PRICE, INITIAL_MIN_PRICE
from atlas.modules.market_clearing.input_objects.market_border import get_max_flow, get_min_flow
from atlas.modules.market_clearing.output_dataset import MarketClearingOutputDataset
from tests.utils import load_threshold_for_module


def _is_finite(value: float) -> bool:
    return isinstance(value, float) and math.isfinite(value)


class TestOutputShape:
    def test_one_local_balance_per_market_area_and_time(
        self,
        input_dataset: MarketClearingInputDataset,
        output_dataset: tuple[MarketClearingOutputDataset, float],
    ) -> None:
        expected_keys = {
            (area_name, time_index)
            for area_name in input_dataset.mc_market_areas
            for time_index in range(len(input_dataset.times))
        }
        assert set(output_dataset[0].local_balances) == expected_keys

    def test_one_market_price_per_market_area_and_time(
        self,
        input_dataset: MarketClearingInputDataset,
        output_dataset: tuple[MarketClearingOutputDataset, float],
    ) -> None:
        expected_keys = {
            (area_name, time_index)
            for area_name in input_dataset.mc_market_areas
            for time_index in range(len(input_dataset.times))
        }
        assert set(output_dataset[0].market_prices) == expected_keys

    def test_one_border_exchange_per_border_and_time(
        self,
        input_dataset: MarketClearingInputDataset,
        output_dataset: tuple[MarketClearingOutputDataset, float],
    ) -> None:
        expected_keys = {
            (border_name, time_index)
            for border_name in input_dataset.mc_market_borders
            for time_index in range(len(input_dataset.times))
        }
        assert set(output_dataset[0].border_exchanges) == expected_keys

    def test_accepted_powers_reference_known_orders(
        self,
        input_dataset: MarketClearingInputDataset,
        output_dataset: tuple[MarketClearingOutputDataset, float],
    ) -> None:
        for area_name, order_name in output_dataset[0].accepted_powers:
            assert area_name in input_dataset.mc_market_areas
            assert order_name in input_dataset.mc_orders
            assert input_dataset.mc_orders[order_name].market_area.name == area_name


class TestOutputValues:
    def test_all_output_values_are_finite(self, output_dataset: tuple[MarketClearingOutputDataset, float]) -> None:
        for value in output_dataset[0].local_balances.values():
            assert _is_finite(value)
        for value in output_dataset[0].market_prices.values():
            assert _is_finite(value)
        for value in output_dataset[0].border_exchanges.values():
            assert _is_finite(value)
        for value in output_dataset[0].accepted_powers.values():
            assert _is_finite(value)

    def test_border_exchanges_respect_capacity_bounds(
        self,
        input_dataset: MarketClearingInputDataset,
        output_dataset: tuple[MarketClearingOutputDataset, float],
    ) -> None:
        tolerance = input_dataset.parameters.allowed_round_off_error
        for (border_name, time_index), exchange in output_dataset[0].border_exchanges.items():
            border = input_dataset.mc_market_borders[border_name]
            time = input_dataset.times[time_index]
            assert exchange <= get_max_flow(border, time) + tolerance
            assert exchange >= get_min_flow(border, time) - tolerance

    def test_market_prices_within_area_price_bounds(
        self,
        input_dataset: MarketClearingInputDataset,
        output_dataset: tuple[MarketClearingOutputDataset, float],
    ) -> None:
        tolerance = input_dataset.parameters.allowed_round_off_error
        for (area_name, time_index), price in output_dataset[0].market_prices.items():
            market_area = input_dataset.mc_market_areas[area_name]
            time = input_dataset.times[time_index]
            max_price = market_area.maximum_price.get_value(time) if market_area.maximum_price else INITIAL_MAX_PRICE
            min_price = market_area.minimum_price.get_value(time) if market_area.minimum_price else INITIAL_MIN_PRICE
            assert price <= max_price + tolerance
            assert price >= min_price - tolerance


class TestChangeSets:
    def test_run_produces_non_empty_change_sets(
        self, output_dataset: tuple[MarketClearingOutputDataset, float]
    ) -> None:
        assert isinstance(output_dataset[0].change_sets, list)
        assert len(output_dataset[0].change_sets) > 0


def test_execution_time_within_threshold(output_dataset):
    _, elapsed = output_dataset
    threshold = load_threshold_for_module("MarketClearing")
    if threshold is None:
        pytest.skip("No performance threshold defined for MarketClearing")
    assert elapsed <= threshold, f"MarketClearing took {elapsed:.2f}s, expected <= {threshold}s"


def test_execution_time_within_threshold_id(output_dataset_id):
    _, elapsed = output_dataset_id
    threshold = load_threshold_for_module("MarketClearingId")
    if threshold is None:
        pytest.skip("No performance threshold defined for MarketClearingId")
    assert elapsed <= threshold, f"MarketClearingId took {elapsed:.2f}s, expected <= {threshold}s"
