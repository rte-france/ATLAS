"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pytest

from atlas.enums import CouplingType, ThermalStrategy
from atlas.io_utils.container import Container
from atlas.io_utils.utils import diff_business_model
from atlas.modules.day_ahead_orders.steps.result import BiddingResult
from atlas.modules.day_ahead_orders.steps.hydro import HydraulicBidding
from atlas.modules.day_ahead_orders.steps.load import LoadBidding
from atlas.modules.day_ahead_orders.steps.non_dispatchable import NonDispatchableBidding
from atlas.modules.day_ahead_orders.steps.renewables import WindPVBidding
from atlas.modules.day_ahead_orders.steps.thermal.base_orders import ThermalBaseLoadOrders
from atlas.modules.day_ahead_orders.steps.thermal.peak_orders import ThermalPeakLoadOrders
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling
from atlas.timing import generate_datetimes

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _orders_time(parameters):
    return generate_datetimes(
        parameters.temporal.start_date,
        parameters.penultimate_date,
        parameters.temporal.timestep,
    )


def _meaningful_diff(obj, other) -> dict:
    """Return diff between two BusinessModel instances, ignoring auto-generated names."""
    return {k: v for k, v in diff_business_model(obj, other).items() if k != "name"}


def _assert_orders_match(result: BiddingResult, expected: Container[Order], equipment_names: set[str]) -> None:
    remaining = [o for o in result.orders if o.equipment.name in equipment_names]

    unmatched = []
    for gen_order in remaining[:]:
        try:
            exp_order = expected.get(gen_order.name)
        except KeyError:
            continue
        diff = _meaningful_diff(gen_order, exp_order)
        if not diff:
            remaining.remove(gen_order)
        else:
            unmatched.append({"order": repr(gen_order), "diff": diff})
            remaining.remove(gen_order)

    assert not unmatched, f"Expected orders not found in generated:\n{unmatched}"
    assert not remaining, f"Generated orders not in expected:\n{remaining}"


def _assert_couplings_match(generated: list[OrderCoupling], expected: list[OrderCoupling]) -> None:
    expected_by_name = {c.name: c for c in expected}
    remaining = list(generated)

    unmatched = []
    for gen_coupling in remaining[:]:
        exp_coupling = expected_by_name.get(gen_coupling.name)
        if exp_coupling is None:
            continue
        diff = _meaningful_diff(gen_coupling, exp_coupling)
        if not diff:
            remaining.remove(gen_coupling)
        else:
            unmatched.append({"coupling": repr(gen_coupling), "diff": diff})
            remaining.remove(gen_coupling)

    assert not unmatched, f"Expected couplings not found in generated:\n{unmatched}"
    assert not remaining, f"Generated couplings not in expected:\n{remaining}"


# ---------------------------------------------------------------------------
# Load step
# ---------------------------------------------------------------------------

LOAD_EQUIPMENT = {"a_baseload", "a_power_to_gas_1", "b_baseload", "b_power_to_gas_1"}


class TestLoadBidding:
    @pytest.fixture(scope="class")
    def result(self, steps_output_dataset, steps_parameters) -> BiddingResult:
        return LoadBidding(steps_output_dataset, _orders_time(steps_parameters), steps_parameters).formulate()

    def test_orders_match_expected(self, result, expected_orders):
        _assert_orders_match(result, expected_orders, LOAD_EQUIPMENT)

    def test_order_count(self, result, expected_orders):
        expected_count = sum(1 for o in expected_orders if o.equipment.name in LOAD_EQUIPMENT)
        assert len(result.orders) == expected_count

    def test_no_order_couplings(self, result):
        assert result.order_couplings == []


# ---------------------------------------------------------------------------
# NonDispatchable step
# ---------------------------------------------------------------------------

NON_DISPATCHABLE_EQUIPMENT = {"a_other_non_dispatchable", "b_other_non_dispatchable"}


class TestNonDispatchableBidding:
    @pytest.fixture(scope="class")
    def result(self, steps_output_dataset, steps_parameters) -> BiddingResult:
        return NonDispatchableBidding(steps_output_dataset, _orders_time(steps_parameters), steps_parameters).formulate()

    def test_orders_match_expected(self, result, expected_orders):
        _assert_orders_match(result, expected_orders, NON_DISPATCHABLE_EQUIPMENT)

    def test_order_count(self, result, expected_orders):
        expected_count = sum(1 for o in expected_orders if o.equipment.name in NON_DISPATCHABLE_EQUIPMENT)
        assert len(result.orders) == expected_count

    def test_no_order_couplings(self, result):
        assert result.order_couplings == []


# ---------------------------------------------------------------------------
# Wind / PV step
# ---------------------------------------------------------------------------

WIND_PV_EQUIPMENT = {"a_wind_1", "b_wind_1", "a_photovoltaic_1", "b_photovoltaic_1"}


class TestWindPVBidding:
    @pytest.fixture(scope="class")
    def result(self, steps_output_dataset, steps_parameters) -> BiddingResult:
        return WindPVBidding(steps_output_dataset, _orders_time(steps_parameters), steps_parameters).formulate()

    def test_orders_match_expected(self, result, expected_orders):
        _assert_orders_match(result, expected_orders, WIND_PV_EQUIPMENT)

    def test_order_count(self, result, expected_orders):
        expected_count = sum(1 for o in expected_orders if o.equipment.name in WIND_PV_EQUIPMENT)
        assert len(result.orders) == expected_count

    def test_no_order_couplings(self, result):
        assert result.order_couplings == []


# ---------------------------------------------------------------------------
# Hydraulic step
# ---------------------------------------------------------------------------

HYDRO_EQUIPMENT = {"a_hydraulic", "b_hydraulic"}


class TestHydraulicBidding:
    @pytest.fixture(scope="class")
    def result(self, steps_output_dataset, steps_parameters) -> BiddingResult:
        return HydraulicBidding(steps_output_dataset, _orders_time(steps_parameters), steps_parameters).formulate()

    def test_orders_match_expected(self, result, expected_orders):
        _assert_orders_match(result, expected_orders, HYDRO_EQUIPMENT)

    def test_order_count(self, result, expected_orders):
        expected_count = sum(1 for o in expected_orders if o.equipment.name in HYDRO_EQUIPMENT)
        assert len(result.orders) == expected_count

    def test_complement_couplings(self, result, expected_couplings):
        expected_complements = [c for c in expected_couplings if c.coupling_type == CouplingType.COMPLEMENT]
        _assert_couplings_match(result.order_couplings, expected_complements)


# ---------------------------------------------------------------------------
# Thermal formulator unit tests (Base and Peak)
# ---------------------------------------------------------------------------

THERMAL_BASE_EQUIPMENT = {"a_thermal_base_1", "b_thermal_base_1"}
THERMAL_PEAK_EQUIPMENT = {"a_thermal_peak_1", "b_thermal_peak_1"}


class TestThermalBaseOrders:
    @pytest.fixture(scope="class")
    def result(self, steps_output_dataset, steps_parameters) -> BiddingResult:
        orders_time = _orders_time(steps_parameters)
        r = BiddingResult()
        for unit in [t for t in steps_output_dataset.thermal if t.strategy == ThermalStrategy.BASE]:
            unit_orders, unit_couplings = ThermalBaseLoadOrders(orders_time, steps_parameters).formulate(unit)
            r.orders.extend(unit_orders)
            r.order_couplings.extend(unit_couplings)
        return r

    def test_orders_match_expected(self, result, expected_orders):
        _assert_orders_match(result, expected_orders, THERMAL_BASE_EQUIPMENT)

    def test_order_count(self, result, expected_orders):
        expected_count = sum(1 for o in expected_orders if o.equipment.name in THERMAL_BASE_EQUIPMENT)
        assert len(result.orders) == expected_count

    def test_couplings_match_expected(self, result, expected_couplings):
        expected = [c for c in expected_couplings if any(o.equipment.name in THERMAL_BASE_EQUIPMENT for o in c.orders)]
        _assert_couplings_match(result.order_couplings, expected)


class TestThermalPeakOrders:
    @pytest.fixture(scope="class")
    def result(self, steps_output_dataset, steps_parameters) -> BiddingResult:
        orders_time = _orders_time(steps_parameters)
        r = BiddingResult()
        for unit in [t for t in steps_output_dataset.thermal if t.strategy == ThermalStrategy.PEAK]:
            unit_orders, unit_couplings = ThermalPeakLoadOrders(orders_time, steps_parameters).formulate(unit)
            r.orders.extend(unit_orders)
            r.order_couplings.extend(unit_couplings)
        return r

    def test_orders_match_expected(self, result, expected_orders):
        _assert_orders_match(result, expected_orders, THERMAL_PEAK_EQUIPMENT)

    def test_order_count(self, result, expected_orders):
        expected_count = sum(1 for o in expected_orders if o.equipment.name in THERMAL_PEAK_EQUIPMENT)
        assert len(result.orders) == expected_count

    def test_couplings_match_expected(self, result, expected_couplings):
        expected = [c for c in expected_couplings if any(o.equipment.name in THERMAL_PEAK_EQUIPMENT for o in c.orders)]
        _assert_couplings_match(result.order_couplings, expected)
