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
from atlas.modules.market_clearing.result import MarketClearingResult
from atlas.orchestrator.change_set import UpdateObject
from tests.utils import check_execution_time


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
    def test_one_local_balance_per_market_area_over_the_horizon(
        self,
        input_dataset: MarketClearingInputDataset,
        result: tuple[MarketClearingResult, float],
    ) -> None:
        assert result[0].local_balances.keys() == input_dataset.market_areas.keys()
        for balance in result[0].local_balances.values():
            assert balance.index == input_dataset.times

    def test_one_market_price_per_market_area_over_the_horizon(
        self,
        input_dataset: MarketClearingInputDataset,
        result: tuple[MarketClearingResult, float],
    ) -> None:
        assert result[0].market_prices.keys() == input_dataset.market_areas.keys()
        for price in result[0].market_prices.values():
            assert price.index == input_dataset.times

    def test_one_border_exchange_per_border_over_the_horizon(
        self,
        input_dataset: MarketClearingInputDataset,
        result: tuple[MarketClearingResult, float],
    ) -> None:
        assert result[0].border_exchanges.keys() == input_dataset.market_borders.keys()
        for exchange in result[0].border_exchanges.values():
            assert exchange.index == input_dataset.times

    def test_accepted_powers_reference_known_orders(
        self,
        input_dataset: MarketClearingInputDataset,
        result: tuple[MarketClearingResult, float],
    ) -> None:
        for area_name, order_name in result[0].accepted_powers:
            assert area_name in input_dataset.market_areas
            assert order_name in input_dataset.orders
            assert input_dataset.orders[order_name].market_area.name == area_name


class TestOutputValues:
    def test_all_output_values_are_finite(self, result: tuple[MarketClearingResult, float]) -> None:
        for outputs in (result[0].local_balances, result[0].market_prices, result[0].border_exchanges):
            for ts in outputs.values():
                assert all(_is_finite(value) for value in ts.values)
        for value in result[0].accepted_powers.values():
            assert _is_finite(value)

    def test_border_exchanges_respect_capacity_bounds(
        self,
        input_dataset: MarketClearingInputDataset,
        result: tuple[MarketClearingResult, float],
    ) -> None:
        tolerance = input_dataset.parameters.allowed_round_off_error
        for border_name, exchanges in result[0].border_exchanges.items():
            border = input_dataset.market_borders[border_name]
            for time, exchange in exchanges.iter_rows():
                assert exchange <= border.max_flow.get_value(time) + tolerance
                assert exchange >= border.min_flow.get_value(time) - tolerance

    def test_market_prices_within_area_price_bounds(
        self,
        input_dataset: MarketClearingInputDataset,
        result: tuple[MarketClearingResult, float],
    ) -> None:
        tolerance = input_dataset.parameters.allowed_round_off_error
        for area_name, prices in result[0].market_prices.items():
            market_area = input_dataset.market_areas[area_name]
            for time, price in prices.iter_rows():
                assert price <= market_area.max_price.get_value(time) + tolerance
                assert price >= market_area.min_price.get_value(time) - tolerance


class TestChangeSets:
    def test_run_produces_non_empty_change_sets(self, result: tuple[MarketClearingResult, float]) -> None:
        assert isinstance(result[0].change_sets, list)
        assert len(result[0].change_sets) > 0

    def test_every_equipment_of_the_perimeter_gets_a_da_cleared_quantity(
        self,
        input_dataset: MarketClearingInputDataset,
        result: tuple[MarketClearingResult, float],
    ) -> None:
        expected = _perimeter_equipment_names(input_dataset)
        assert expected, "No equipment in the cleared perimeter, test dataset is not relevant anymore"

        updated = {
            change_set.data["name"]
            for change_set in result[0].change_sets
            if isinstance(change_set, UpdateObject) and "da_cleared_quantity" in change_set.data
        }
        assert not expected - updated

    def test_da_cleared_quantity_covers_the_whole_clearing_horizon(
        self,
        input_dataset: MarketClearingInputDataset,
        result: tuple[MarketClearingResult, float],
    ) -> None:
        expected_times = set(input_dataset.times)
        perimeter = _perimeter_equipment_names(input_dataset)

        for change_set in result[0].change_sets:
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


@pytest.mark.perf
def test_execution_time_within_threshold(result):
    _, elapsed = result
    check_execution_time("MarketClearing", elapsed, "MarketClearing")


@pytest.mark.perf
def test_execution_time_within_threshold_id(result_id):
    _, elapsed = result_id
    check_execution_time("MarketClearingId", elapsed, "MarketClearingId")
