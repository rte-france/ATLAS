"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pytest

from atlas.enums import ThermalStrategy
from atlas.io_utils.container import Container
from atlas.io_utils.utils import diff_business_model
from atlas.modules.intraday_orders.orders_formulation.abstract_orders import FormulatorResult
from atlas.modules.intraday_orders.orders_formulation.hydro import HydroOrdersFormulator
from atlas.modules.intraday_orders.orders_formulation.load import LoadOrdersFormulator
from atlas.modules.intraday_orders.orders_formulation.non_dispatchable import NonDispatchableOrdersFormulator
from atlas.modules.intraday_orders.orders_formulation.solar import SolarOrdersFormulator
from atlas.modules.intraday_orders.orders_formulation.storage import StorageOrdersFormulator
from atlas.modules.intraday_orders.orders_formulation.thermal import ThermalOrdersFormulator
from atlas.modules.intraday_orders.orders_formulation.wind import WindOrdersFormulator
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


# These fields are mutated during formulation; the expected fixture equipment objects don't carry
# the same state, so comparing them is meaningless.
_SKIP_EQUIPMENT_FIELDS = {
    "id_buy_submitted_volume",
    "id_sell_submitted_volume",
}

_FLOAT_RTOL = 1e-9


def _drop_skip_fields(d: dict) -> dict:
    cleaned = {}
    for k, v in d.items():
        if k in _SKIP_EQUIPMENT_FIELDS:
            continue
        if not isinstance(v, dict):
            cleaned[k] = v
        elif v.get("type") == "nested":
            inner = _drop_skip_fields(v.get("diffs", {}))
            if inner:
                cleaned[k] = {**v, "diffs": inner}
        elif "self" in v and "other" in v:
            s, o = v["self"], v["other"]
            if isinstance(s, float) and isinstance(o, float):
                if abs(s - o) <= _FLOAT_RTOL * max(abs(s), abs(o), 1.0):
                    continue
            cleaned[k] = v
        else:
            inner = _drop_skip_fields(v)
            if inner:
                cleaned[k] = inner
    return cleaned


def _meaningful_diff(obj, other) -> dict:
    raw = {k: v for k, v in diff_business_model(obj, other).items() if k != "name"}
    return _drop_skip_fields(raw)


def _assert_orders_match(result: FormulatorResult, expected: Container[Order], equipment_names: set[str]) -> None:
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

    assert not unmatched, f"Orders differ from expected:\n{unmatched}"
    assert not remaining, f"Generated orders not found in expected:\n{remaining}"


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

    assert not unmatched, f"Couplings differ from expected:\n{unmatched}"
    assert not remaining, f"Generated couplings not found in expected:\n{remaining}"


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

LOAD_EQUIPMENT = {"a_baseload", "a_power_to_gas_1", "b_baseload", "b_power_to_gas_1"}


class TestLoadFormulator:
    @pytest.fixture(scope="class")
    def result(self, formulator_output_dataset, formulator_parameters) -> FormulatorResult:
        equipments = formulator_output_dataset.load
        return LoadOrdersFormulator().formulate(equipments, _orders_time(formulator_parameters), formulator_parameters)

    def test_orders_match_expected(self, result, expected_orders):
        _assert_orders_match(result, expected_orders, LOAD_EQUIPMENT)

    def test_order_count(self, result, expected_orders):
        expected_count = sum(1 for o in expected_orders if o.equipment.name in LOAD_EQUIPMENT)
        assert len(result.orders) == expected_count

    def test_no_order_couplings(self, result):
        assert result.order_couplings == []


# ---------------------------------------------------------------------------
# Non-dispatchable
# ---------------------------------------------------------------------------

NON_DISPATCHABLE_EQUIPMENT = {"a_other_non_dispatchable", "b_other_non_dispatchable"}


class TestNonDispatchableFormulator:
    @pytest.fixture(scope="class")
    def result(self, formulator_output_dataset, formulator_parameters) -> FormulatorResult:
        equipments = formulator_output_dataset.other_non_dispatchable
        return NonDispatchableOrdersFormulator().formulate(
            equipments, _orders_time(formulator_parameters), formulator_parameters
        )

    def test_orders_match_expected(self, result, expected_orders):
        _assert_orders_match(result, expected_orders, NON_DISPATCHABLE_EQUIPMENT)

    def test_order_count(self, result, expected_orders):
        expected_count = sum(1 for o in expected_orders if o.equipment.name in NON_DISPATCHABLE_EQUIPMENT)
        assert len(result.orders) == expected_count

    def test_no_order_couplings(self, result):
        assert result.order_couplings == []


# ---------------------------------------------------------------------------
# Wind
# ---------------------------------------------------------------------------

WIND_EQUIPMENT = {"a_wind_1", "b_wind_1"}


class TestWindFormulator:
    @pytest.fixture(scope="class")
    def result(self, formulator_output_dataset, formulator_parameters) -> FormulatorResult:
        equipments = formulator_output_dataset.wind
        return WindOrdersFormulator().formulate(equipments, _orders_time(formulator_parameters), formulator_parameters)

    def test_orders_match_expected(self, result, expected_orders):
        _assert_orders_match(result, expected_orders, WIND_EQUIPMENT)

    def test_order_count(self, result, expected_orders):
        expected_count = sum(1 for o in expected_orders if o.equipment.name in WIND_EQUIPMENT)
        assert len(result.orders) == expected_count

    def test_no_order_couplings(self, result):
        assert result.order_couplings == []


# ---------------------------------------------------------------------------
# Solar
# ---------------------------------------------------------------------------

SOLAR_EQUIPMENT = {"a_photovoltaic_1", "b_photovoltaic_1"}


class TestSolarFormulator:
    @pytest.fixture(scope="class")
    def result(self, formulator_output_dataset, formulator_parameters) -> FormulatorResult:
        equipments = formulator_output_dataset.solar
        return SolarOrdersFormulator().formulate(equipments, _orders_time(formulator_parameters), formulator_parameters)

    def test_orders_match_expected(self, result, expected_orders):
        _assert_orders_match(result, expected_orders, SOLAR_EQUIPMENT)

    def test_order_count(self, result, expected_orders):
        expected_count = sum(1 for o in expected_orders if o.equipment.name in SOLAR_EQUIPMENT)
        assert len(result.orders) == expected_count

    def test_no_order_couplings(self, result):
        assert result.order_couplings == []


# ---------------------------------------------------------------------------
# Hydro
# ---------------------------------------------------------------------------

HYDRO_EQUIPMENT = {"a_hydraulic", "b_hydraulic"}


class TestHydroFormulator:
    @pytest.fixture(scope="class")
    def result(self, formulator_output_dataset, formulator_parameters) -> FormulatorResult:
        equipments = formulator_output_dataset.hydro
        return HydroOrdersFormulator().formulate(equipments, _orders_time(formulator_parameters), formulator_parameters)

    def test_orders_match_expected(self, result, expected_orders):
        _assert_orders_match(result, expected_orders, HYDRO_EQUIPMENT)

    def test_order_count(self, result, expected_orders):
        expected_count = sum(1 for o in expected_orders if o.equipment.name in HYDRO_EQUIPMENT)
        assert len(result.orders) == expected_count

    def test_no_order_couplings(self, result):
        assert result.order_couplings == []


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

STORAGE_EQUIPMENT = {"a_battery_1", "b_battery_1", "a_electric_vehicle_1", "b_electric_vehicle_1"}


class TestStorageFormulator:
    @pytest.fixture(scope="class")
    def result(self, formulator_output_dataset, formulator_parameters) -> FormulatorResult:
        equipments = formulator_output_dataset.storage
        return StorageOrdersFormulator().formulate(
            equipments, _orders_time(formulator_parameters), formulator_parameters
        )

    def test_orders_match_expected(self, result, expected_orders):
        _assert_orders_match(result, expected_orders, STORAGE_EQUIPMENT)

    def test_order_count(self, result, expected_orders):
        expected_count = sum(1 for o in expected_orders if o.equipment.name in STORAGE_EQUIPMENT)
        assert len(result.orders) == expected_count

    def test_ev_couplings_match_expected(self, result, expected_couplings):
        ev_equipment = {"a_electric_vehicle_1", "b_electric_vehicle_1"}
        relevant = [c for c in expected_couplings if any(o.equipment.name in ev_equipment for o in c.orders)]
        _assert_couplings_match(result.order_couplings, relevant)


# ---------------------------------------------------------------------------
# Thermal — BASE/INTERMEDIATE
# ---------------------------------------------------------------------------

THERMAL_BASE_INTERMEDIATE_EQUIPMENT = {
    "a_thermal_base_1",
    "a_thermal_intermediate_1",
    "b_thermal_base_1",
    "b_thermal_intermediate_1",
}


class TestThermalBaseIntermediateFormulator:
    @pytest.fixture(scope="class")
    def result(self, formulator_output_dataset, formulator_parameters) -> FormulatorResult:
        equipments = [
            t
            for t in formulator_output_dataset.thermal
            if t.strategy in (ThermalStrategy.BASE, ThermalStrategy.INTERMEDIATE)
        ]
        return ThermalOrdersFormulator().formulate(
            equipments, _orders_time(formulator_parameters), formulator_parameters
        )

    def test_orders_match_expected(self, result, expected_orders):
        _assert_orders_match(result, expected_orders, THERMAL_BASE_INTERMEDIATE_EQUIPMENT)

    def test_couplings_match_expected(self, result, expected_couplings):
        relevant = [
            c
            for c in expected_couplings
            if any(o.equipment.name in THERMAL_BASE_INTERMEDIATE_EQUIPMENT for o in c.orders)
        ]
        _assert_couplings_match(result.order_couplings, relevant)


# ---------------------------------------------------------------------------
# Thermal — PEAK
# ---------------------------------------------------------------------------

THERMAL_PEAK_EQUIPMENT = {"a_thermal_peak_1", "b_thermal_peak_1"}


class TestThermalPeakFormulator:
    @pytest.fixture(scope="class")
    def result(self, formulator_output_dataset, formulator_parameters) -> FormulatorResult:
        equipments = [t for t in formulator_output_dataset.thermal if t.strategy == ThermalStrategy.PEAK]
        return ThermalOrdersFormulator().formulate(
            equipments, _orders_time(formulator_parameters), formulator_parameters
        )

    def test_orders_match_expected(self, result, expected_orders):
        _assert_orders_match(result, expected_orders, THERMAL_PEAK_EQUIPMENT)

    def test_couplings_match_expected(self, result, expected_couplings):
        relevant = [c for c in expected_couplings if any(o.equipment.name in THERMAL_PEAK_EQUIPMENT for o in c.orders)]
        _assert_couplings_match(result.order_couplings, relevant)
