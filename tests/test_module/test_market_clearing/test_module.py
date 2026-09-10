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

from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.output_dataset import MarketClearingOutputDataset
from atlas.orchestrator.change_set import UpdateObject
from tests.utils import load_threshold_for_module


def _is_finite(value: float) -> bool:
    return isinstance(value, float) and math.isfinite(value)


def _perimeter_equipment_names(input_dataset: MarketClearingInputDataset) -> set[str]:
    """Names of the equipment whose portfolio belongs to a cleared market area."""
    return {
        equipment.name
        for equipment in input_dataset.input_data.iter_by_equipments()
        if equipment.portfolio is not None
        and equipment.portfolio.market_area is not None
        and equipment.portfolio.market_area.name in input_dataset.market_areas
    }


class TestOutputShape:
    def test_one_local_balance_per_market_area_and_time(
        self,
        input_dataset: MarketClearingInputDataset,
        output_dataset: tuple[MarketClearingOutputDataset, float],
    ) -> None:
        expected_keys = {(area_name, time) for area_name in input_dataset.market_areas for time in input_dataset.times}
        assert set(output_dataset[0].local_balances) == expected_keys

    def test_one_market_price_per_market_area_and_time(
        self,
        input_dataset: MarketClearingInputDataset,
        output_dataset: tuple[MarketClearingOutputDataset, float],
    ) -> None:
        expected_keys = {(area_name, time) for area_name in input_dataset.market_areas for time in input_dataset.times}
        assert set(output_dataset[0].market_prices) == expected_keys

    def test_one_border_exchange_per_border_and_time(
        self,
        input_dataset: MarketClearingInputDataset,
        output_dataset: tuple[MarketClearingOutputDataset, float],
    ) -> None:
        expected_keys = {
            (border_name, time) for border_name in input_dataset.market_borders for time in input_dataset.times
        }
        assert set(output_dataset[0].border_exchanges) == expected_keys

    def test_accepted_powers_reference_known_orders(
        self,
        input_dataset: MarketClearingInputDataset,
        output_dataset: tuple[MarketClearingOutputDataset, float],
    ) -> None:
        for area_name, order_name in output_dataset[0].accepted_powers:
            assert area_name in input_dataset.market_areas
            assert order_name in input_dataset.orders
            assert input_dataset.orders[order_name].market_area.name == area_name


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
        for (border_name, time), exchange in output_dataset[0].border_exchanges.items():
            border = input_dataset.market_borders[border_name]
            assert exchange <= border.max_flow.get_value(time) + tolerance
            assert exchange >= border.min_flow.get_value(time) - tolerance

    def test_market_prices_within_area_price_bounds(
        self,
        input_dataset: MarketClearingInputDataset,
        output_dataset: tuple[MarketClearingOutputDataset, float],
    ) -> None:
        tolerance = input_dataset.parameters.allowed_round_off_error
        for (area_name, time), price in output_dataset[0].market_prices.items():
            market_area = input_dataset.market_areas[area_name]
            assert price <= market_area.max_price.get_value(time) + tolerance
            assert price >= market_area.min_price.get_value(time) - tolerance


class TestChangeSets:
    def test_run_produces_non_empty_change_sets(
        self, output_dataset: tuple[MarketClearingOutputDataset, float]
    ) -> None:
        assert isinstance(output_dataset[0].change_sets, list)
        assert len(output_dataset[0].change_sets) > 0

    def test_every_equipment_of_the_perimeter_gets_a_da_cleared_quantity(
        self,
        input_dataset: MarketClearingInputDataset,
        output_dataset: tuple[MarketClearingOutputDataset, float],
    ) -> None:
        expected = _perimeter_equipment_names(input_dataset)
        assert expected, "No equipment in the cleared perimeter, test dataset is not relevant anymore"

        updated = {
            change_set.data["name"]
            for change_set in output_dataset[0].change_sets
            if isinstance(change_set, UpdateObject) and "da_cleared_quantity" in change_set.data
        }
        assert not expected - updated

    def test_da_cleared_quantity_covers_the_whole_clearing_horizon(
        self,
        input_dataset: MarketClearingInputDataset,
        output_dataset: tuple[MarketClearingOutputDataset, float],
    ) -> None:
        expected_times = set(input_dataset.times)
        perimeter = _perimeter_equipment_names(input_dataset)

        for change_set in output_dataset[0].change_sets:
            if not isinstance(change_set, UpdateObject) or "da_cleared_quantity" not in change_set.data:
                continue
            if change_set.data["name"] not in perimeter:
                continue
            timeseries = change_set.data["da_cleared_quantity"]
            if isinstance(timeseries, LazyTimeseries):
                timeseries = timeseries.collect()
            assert not expected_times - set(timeseries.index), (
                f"{change_set.data['name']}: da_cleared_quantity does not cover the whole clearing horizon"
            )


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
