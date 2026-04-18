"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import re

from atlas.io_utils.container import Container
from atlas.io_utils.utils import diff_business_model
from atlas.modules.day_ahead_orders.steps.abstract_step import StepResult
from atlas.modules.day_ahead_orders.steps.hydro import HydraulicStep
from atlas.modules.day_ahead_orders.steps.load import LoadStep
from atlas.modules.day_ahead_orders.steps.non_dispatchable import NonDispatchableStep
from atlas.modules.day_ahead_orders.steps.renewables import WindPVStep
from atlas.modules.day_ahead_orders.steps.thermal.thermal_bidding_step import ThermalBiddingStep
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


def _assert_orders_match(result: StepResult, expected: Container[Order], equipment_names: set[str]) -> None:
    remaining = [o for o in result.orders if o.equipment.name in equipment_names]

    unmatched = []
    for gen_order in remaining[:]:
        try:
            normalized_name = re.sub(
                r"(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})[+\-]\d{2}:\d{2}",
                r"\3_\2_\1_\4_\5_\6",
                gen_order.name,
            )
            exp_order = expected.get(normalized_name)
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


class TestLoadStep:
    def test_orders_match_expected(self, steps_output_dataset, steps_parameters, expected_orders):
        result = LoadStep(steps_output_dataset, _orders_time(steps_parameters), steps_parameters).formulate()
        _assert_orders_match(result, expected_orders, LOAD_EQUIPMENT)

    def test_order_count(self, steps_output_dataset, steps_parameters, expected_orders):
        result = LoadStep(steps_output_dataset, _orders_time(steps_parameters), steps_parameters).formulate()
        expected_count = sum(1 for o in expected_orders if o.equipment.name in LOAD_EQUIPMENT)
        assert len(result.orders) == expected_count

    def test_no_order_couplings(self, steps_output_dataset, steps_parameters):
        result = LoadStep(steps_output_dataset, _orders_time(steps_parameters), steps_parameters).formulate()
        assert result.order_couplings == []


# ---------------------------------------------------------------------------
# NonDispatchable step
# ---------------------------------------------------------------------------

NON_DISPATCHABLE_EQUIPMENT = {"a_other_non_dispatchable", "b_other_non_dispatchable"}


class TestNonDispatchableStep:
    def test_orders_match_expected(self, steps_output_dataset, steps_parameters, expected_orders):
        result = NonDispatchableStep(steps_output_dataset, _orders_time(steps_parameters), steps_parameters).formulate()
        _assert_orders_match(result, expected_orders, NON_DISPATCHABLE_EQUIPMENT)

    def test_order_count(self, steps_output_dataset, steps_parameters, expected_orders):
        result = NonDispatchableStep(steps_output_dataset, _orders_time(steps_parameters), steps_parameters).formulate()
        expected_count = sum(1 for o in expected_orders if o.equipment.name in NON_DISPATCHABLE_EQUIPMENT)
        assert len(result.orders) == expected_count

    def test_no_order_couplings(self, steps_output_dataset, steps_parameters):
        result = NonDispatchableStep(steps_output_dataset, _orders_time(steps_parameters), steps_parameters).formulate()
        assert result.order_couplings == []


# ---------------------------------------------------------------------------
# Wind / PV step
# ---------------------------------------------------------------------------

WIND_PV_EQUIPMENT = {"a_wind_1", "b_wind_1", "a_photovoltaic_1", "b_photovoltaic_1"}


class TestWindPVStep:
    def test_orders_match_expected(self, steps_output_dataset, steps_parameters, expected_orders):
        result = WindPVStep(steps_output_dataset, _orders_time(steps_parameters), steps_parameters).formulate()
        _assert_orders_match(result, expected_orders, WIND_PV_EQUIPMENT)

    def test_order_count(self, steps_output_dataset, steps_parameters, expected_orders):
        result = WindPVStep(steps_output_dataset, _orders_time(steps_parameters), steps_parameters).formulate()
        expected_count = sum(1 for o in expected_orders if o.equipment.name in WIND_PV_EQUIPMENT)
        assert len(result.orders) == expected_count

    def test_no_order_couplings(self, steps_output_dataset, steps_parameters):
        result = WindPVStep(steps_output_dataset, _orders_time(steps_parameters), steps_parameters).formulate()
        assert result.order_couplings == []


# ---------------------------------------------------------------------------
# Hydraulic step
# ---------------------------------------------------------------------------

HYDRO_EQUIPMENT = {"a_hydraulic", "b_hydraulic"}


class TestHydraulicStep:
    def test_orders_match_expected(self, steps_output_dataset, steps_parameters, expected_orders):
        result = HydraulicStep(steps_output_dataset, _orders_time(steps_parameters), steps_parameters).formulate()
        _assert_orders_match(result, expected_orders, HYDRO_EQUIPMENT)

    def test_order_count(self, steps_output_dataset, steps_parameters, expected_orders):
        result = HydraulicStep(steps_output_dataset, _orders_time(steps_parameters), steps_parameters).formulate()
        expected_count = sum(1 for o in expected_orders if o.equipment.name in HYDRO_EQUIPMENT)
        assert len(result.orders) == expected_count

    def test_complement_couplings(self, steps_output_dataset, steps_parameters, expected_couplings):
        from atlas.enums import CouplingType

        result = HydraulicStep(steps_output_dataset, _orders_time(steps_parameters), steps_parameters).formulate()

        expected_complements = [c for c in expected_couplings if c.coupling_type == CouplingType.COMPLEMENT]

        _assert_couplings_match(result.order_couplings, expected_complements)


# ---------------------------------------------------------------------------
# Thermal step (Base and Peak only)
# ---------------------------------------------------------------------------

THERMAL_BASE_PEAK_EQUIPMENT = {"a_thermal_base_1", "b_thermal_base_1", "a_thermal_peak_1", "b_thermal_peak_1"}


class TestThermalBiddingStep:
    def test_orders_match_expected(self, steps_output_dataset, steps_parameters, expected_orders):
        result = ThermalBiddingStep(steps_output_dataset, _orders_time(steps_parameters), steps_parameters).formulate()
        _assert_orders_match(result, expected_orders, THERMAL_BASE_PEAK_EQUIPMENT)

    def test_order_count(self, steps_output_dataset, steps_parameters, expected_orders):
        result = ThermalBiddingStep(steps_output_dataset, _orders_time(steps_parameters), steps_parameters).formulate()
        expected_count = sum(1 for o in expected_orders if o.equipment.name in THERMAL_BASE_PEAK_EQUIPMENT)
        assert len([o for o in result.orders if o.equipment.name in THERMAL_BASE_PEAK_EQUIPMENT]) == expected_count
