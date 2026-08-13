"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from datetime import datetime

import pendulum
import pytest

from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.common.optimal_dispatch.dispatch.thermal import ThermalDispatch
from atlas.common.optimal_dispatch.input_objects.thermal import ThermalDispatchInput
from atlas.io_utils.parameters import DateParameters
from atlas.math.timeseries import Timeseries
from atlas.objects.market.market_area import MarketArea
from atlas.objects.market_operator.portfolio import Portfolio
from atlas.objects.network.node import Node
from atlas.objects.network_operator.control_block import ControlBlock
from atlas.solver.solver_interface import OptimisationModel


@pytest.fixture
def start_date():
    return pendulum.datetime(2024, 1, 1)


@pytest.fixture
def timestep():
    return pendulum.duration(hours=1)


@pytest.fixture
def control_block():
    return ControlBlock(name="cb")


@pytest.fixture
def market_area(control_block):
    return MarketArea(name="ma", control_block=control_block)


@pytest.fixture
def node(control_block, market_area):
    return Node(name="node", control_block=control_block, market_area=market_area)


@pytest.fixture
def portfolio(control_block, market_area):
    return Portfolio(name="portfolio", control_block=control_block, market_area=market_area)


@pytest.fixture
def power_ts(start_date, timestep):
    return Timeseries.from_index(
        start_date=start_date.subtract(days=1),
        frequency=timestep,
        end_date=start_date.add(days=2),
        default_value=200.0,
    )


@pytest.fixture
def min_power_ts(start_date, timestep):
    return Timeseries.from_index(
        start_date=start_date.subtract(days=1),
        frequency=timestep,
        end_date=start_date.add(days=2),
        default_value=50.0,
    )


def _make_equipment(node, portfolio, power_ts, min_power_ts, **kwargs):
    """Build a ThermalDispatchInput with sensible defaults, overridable via kwargs."""
    defaults = {
        "minimum_time_on": pendulum.duration(hours=0),
        "minimum_time_off": pendulum.duration(hours=0),
        "minimum_stable_power_duration": pendulum.duration(hours=0),
    }
    defaults.update(kwargs)
    return ThermalDispatchInput(
        name="th_unit",
        node=node,
        portfolio=portfolio,
        maximum_power=power_ts,
        minimum_power=min_power_ts,
        **defaults,
    )


@pytest.fixture
def comb1_equipment(node, portfolio, power_ts, min_power_ts):
    """Combination 1: no start, no stop, no flat."""
    return _make_equipment(node, portfolio, power_ts, min_power_ts)


@pytest.fixture
def parameters(start_date, timestep):
    return AbstractModuleParameters(
        temporal=DateParameters(
            start_date=start_date,
            end_date=start_date.add(hours=4),
            execution_date=start_date.subtract(days=1),
            timestep=timestep,
        )
    )


@pytest.fixture
def model():
    return OptimisationModel("SCIP", "test_thermal_dispatch")


@pytest.fixture
def time_window(start_date, timestep):
    return [start_date.add(hours=h) for h in range(4)]


class TestThermalDispatchCombinations:
    """The combination property encodes which state variables exist."""

    def _combination(self, node, portfolio, power_ts, min_power_ts, parameters, model, **kwargs):
        eq = _make_equipment(node, portfolio, power_ts, min_power_ts, **kwargs)
        d = ThermalDispatch(eq)
        d.setup(model, parameters)
        return d.combination

    def test_combination_1_no_flags(self, node, portfolio, power_ts, min_power_ts, parameters, model):
        assert self._combination(node, portfolio, power_ts, min_power_ts, parameters, model) == 1

    def test_combination_2_stop_only(self, node, portfolio, power_ts, min_power_ts, parameters, model):
        assert (
            self._combination(
                node, portfolio, power_ts, min_power_ts, parameters, model,
                shutdown_duration=pendulum.duration(hours=2),
            )
            == 2
        )

    def test_combination_3_flat_only(self, node, portfolio, power_ts, min_power_ts, parameters, model):
        assert (
            self._combination(
                node, portfolio, power_ts, min_power_ts, parameters, model,
                minimum_stable_power_duration=pendulum.duration(hours=3),
            )
            == 3
        )

    def test_combination_4_start_only(self, node, portfolio, power_ts, min_power_ts, parameters, model):
        assert (
            self._combination(
                node, portfolio, power_ts, min_power_ts, parameters, model,
                startup_duration=pendulum.duration(hours=2),
            )
            == 4
        )

    def test_combination_5_stop_and_flat(self, node, portfolio, power_ts, min_power_ts, parameters, model):
        assert (
            self._combination(
                node, portfolio, power_ts, min_power_ts, parameters, model,
                shutdown_duration=pendulum.duration(hours=2),
                minimum_stable_power_duration=pendulum.duration(hours=3),
            )
            == 5
        )

    def test_combination_6_start_and_flat(self, node, portfolio, power_ts, min_power_ts, parameters, model):
        assert (
            self._combination(
                node, portfolio, power_ts, min_power_ts, parameters, model,
                startup_duration=pendulum.duration(hours=2),
                minimum_stable_power_duration=pendulum.duration(hours=3),
            )
            == 6
        )

    def test_combination_7_stop_and_start(self, node, portfolio, power_ts, min_power_ts, parameters, model):
        assert (
            self._combination(
                node, portfolio, power_ts, min_power_ts, parameters, model,
                shutdown_duration=pendulum.duration(hours=2),
                startup_duration=pendulum.duration(hours=2),
            )
            == 7
        )

    def test_combination_8_all_flags(self, node, portfolio, power_ts, min_power_ts, parameters, model):
        assert (
            self._combination(
                node, portfolio, power_ts, min_power_ts, parameters, model,
                shutdown_duration=pendulum.duration(hours=2),
                startup_duration=pendulum.duration(hours=2),
                minimum_stable_power_duration=pendulum.duration(hours=3),
            )
            == 8
        )


class TestThermalDispatchVariables:
    def test_setup_creates_model_vars(self, comb1_equipment, model, parameters):
        d = ThermalDispatch(comb1_equipment)
        d.setup(model, parameters)

        assert d.power_level_var is not None
        assert d.off_var is not None
        assert d.on_up_var is not None
        assert d.on_down_var is not None
        assert d.turned_on is not None
        assert d.turned_off is not None

    def test_add_variables_creates_correct_names(self, comb1_equipment, model, parameters, time_window):
        d = ThermalDispatch(comb1_equipment)
        d.setup(model, parameters)
        n = comb1_equipment.name
        t = time_window[0]
        d.add_variables(t)

        assert f"{n}_power_level_{t}" in model.variables
        assert f"off_{n}_{t}" in model.variables
        assert f"on_up_{n}_{t}" in model.variables
        assert f"on_down_{n}_{t}" in model.variables
        assert f"t_on_{n}_{t}" in model.variables
        assert f"t_off_{n}_{t}" in model.variables

    def test_power_level_bounds(self, comb1_equipment, model, parameters, time_window):
        d = ThermalDispatch(comb1_equipment)
        d.setup(model, parameters)
        t = time_window[0]
        d.add_variables(t)

        var = model.get_variable(f"{comb1_equipment.name}_power_level_{t}")
        assert var.lb() == 0
        assert var.ub() == pytest.approx(200.0)

    def test_off_var_is_boolean(self, comb1_equipment, model, parameters, time_window):
        d = ThermalDispatch(comb1_equipment)
        d.setup(model, parameters)
        t = time_window[0]
        d.add_variables(t)

        var = model.get_variable(f"off_{comb1_equipment.name}_{t}")
        assert var.lb() == 0
        assert var.ub() == 1

    def test_start_stop_vars_absent_for_combination_1(self, comb1_equipment, model, parameters, time_window):
        d = ThermalDispatch(comb1_equipment)
        d.setup(model, parameters)
        t = time_window[0]
        d.add_variables(t)

        n = comb1_equipment.name
        assert f"on_start_{n}_{t}" not in model.variables
        assert f"stop_{n}_{t}" not in model.variables
        assert f"on_flat_{n}_{t}" not in model.variables

    def test_stop_var_present_for_combination_2(self, node, portfolio, power_ts, min_power_ts, model, parameters, time_window):
        eq = _make_equipment(
            node, portfolio, power_ts, min_power_ts,
            shutdown_duration=pendulum.duration(hours=2),
        )
        d = ThermalDispatch(eq)
        d.setup(model, parameters)
        t = time_window[0]
        d.add_variables(t)

        assert f"stop_{eq.name}_{t}" in model.variables

    def test_start_var_present_for_combination_4(self, node, portfolio, power_ts, min_power_ts, model, parameters, time_window):
        eq = _make_equipment(
            node, portfolio, power_ts, min_power_ts,
            startup_duration=pendulum.duration(hours=2),
        )
        d = ThermalDispatch(eq)
        d.setup(model, parameters)
        t = time_window[0]
        d.add_variables(t)

        assert f"on_start_{eq.name}_{t}" in model.variables

    def test_flat_var_present_for_combination_3(self, node, portfolio, power_ts, min_power_ts, model, parameters, time_window):
        eq = _make_equipment(
            node, portfolio, power_ts, min_power_ts,
            minimum_stable_power_duration=pendulum.duration(hours=3),
        )
        d = ThermalDispatch(eq)
        d.setup(model, parameters)
        t = time_window[0]
        d.add_variables(t)

        assert f"on_flat_{eq.name}_{t}" in model.variables


class TestThermalDispatchConstraints:
    def _setup(self, equipment, model, parameters, time_window):
        d = ThermalDispatch(equipment)
        d.setup(model, parameters)
        for t in time_window:
            d.add_variables(t)
        return d

    def test_mutual_exclusion_constraint_added(self, comb1_equipment, model, parameters, time_window):
        d = self._setup(comb1_equipment, model, parameters, time_window)
        t = time_window[0]
        d.add_constraints(model, t, parameters)

        assert f"mutual_exclusion_{t}_{comb1_equipment.name}" in model.constraints

    def test_turned_on_constraints_added(self, comb1_equipment, model, parameters, time_window):
        d = self._setup(comb1_equipment, model, parameters, time_window)
        t = time_window[1]
        d.add_constraints(model, t, parameters)

        n = comb1_equipment.name
        assert f"t_on_evol_1_{t}_{n}" in model.constraints
        assert f"t_on_evol_2_{t}_{n}" in model.constraints
        assert f"t_on_evol_3_{t}_{n}" in model.constraints

    def test_turned_off_constraints_added(self, comb1_equipment, model, parameters, time_window):
        d = self._setup(comb1_equipment, model, parameters, time_window)
        t = time_window[1]
        d.add_constraints(model, t, parameters)

        n = comb1_equipment.name
        assert f"t_off_evol_1_{t}_{n}" in model.constraints
        assert f"t_off_evol_2_{t}_{n}" in model.constraints
        assert f"t_off_evol_3_{t}_{n}" in model.constraints

    def test_power_bounds_constraints_added(self, comb1_equipment, model, parameters, time_window):
        d = self._setup(comb1_equipment, model, parameters, time_window)
        t = time_window[0]
        d.add_constraints(model, t, parameters)

        n = comb1_equipment.name
        assert f"lower_bound_{n}_{t}" in model.constraints
        assert f"upper_bound_{n}_{t}" in model.constraints

    def test_gradient_constraint_added(self, comb1_equipment, model, parameters, time_window):
        d = self._setup(comb1_equipment, model, parameters, time_window)
        t = time_window[1]
        prev = time_window[0]
        d.add_dd_and_gradient_constraints(model, t, prev)

        n = comb1_equipment.name
        assert f"unconstrained_upward_gradient_{n}_{prev}" in model.constraints
        assert f"unconstrained_downward_gradient_{n}_{prev}" in model.constraints


class TestThermalDispatchDailyEnergyConstraint:
    def _make_daily_params(self, start_date, timestep):
        return AbstractModuleParameters(
            temporal=DateParameters(
                start_date=start_date,
                end_date=start_date.add(days=2),
                execution_date=start_date.subtract(days=1),
                timestep=timestep,
            )
        )

    def _make_daily_energy_ts(self, start_date, timestep):
        return Timeseries.from_index(
            start_date=start_date.subtract(days=1),
            frequency=timestep,
            end_date=start_date.add(days=3),
            default_value=1000.0,
        )

    def test_constraint_added_when_active(self, node, portfolio, power_ts, min_power_ts, model, start_date, timestep):
        daily_energy_ts = self._make_daily_energy_ts(start_date, timestep)
        eq = _make_equipment(
            node, portfolio, power_ts, min_power_ts,
            has_daily_energy_constraint=True,
            maximum_daily_energy=daily_energy_ts,
        )
        params = self._make_daily_params(start_date, timestep)
        d = ThermalDispatch(eq)
        d.setup(model, params)
        time_window = [start_date.add(hours=h) for h in range(48)]
        for t in time_window:
            d.add_variables(t)

        d.add_daily_energy_constraint(model, time_window, timestep)

        day0 = datetime(start_date.year, start_date.month, start_date.day)
        assert f"energy_limit_of_{eq.name}_at_{day0}" in model.constraints

    def test_constraint_skipped_when_inactive(self, node, portfolio, power_ts, min_power_ts, model, start_date, timestep):
        eq = _make_equipment(node, portfolio, power_ts, min_power_ts, has_daily_energy_constraint=False)
        params = self._make_daily_params(start_date, timestep)
        d = ThermalDispatch(eq)
        d.setup(model, params)
        time_window = [start_date.add(hours=h) for h in range(24)]
        for t in time_window:
            d.add_variables(t)

        d.add_daily_energy_constraint(model, time_window, timestep)

        assert not any("energy_limit_of" in c for c in model.constraints)

    def test_one_constraint_per_day(self, node, portfolio, power_ts, min_power_ts, model, start_date, timestep):
        daily_energy_ts = self._make_daily_energy_ts(start_date, timestep)
        eq = _make_equipment(
            node, portfolio, power_ts, min_power_ts,
            has_daily_energy_constraint=True,
            maximum_daily_energy=daily_energy_ts,
        )
        params = self._make_daily_params(start_date, timestep)
        d = ThermalDispatch(eq)
        d.setup(model, params)
        time_window = [start_date.add(hours=h) for h in range(48)]
        for t in time_window:
            d.add_variables(t)

        d.add_daily_energy_constraint(model, time_window, timestep)

        energy_constraints = [c for c in model.constraints if "energy_limit_of" in c]
        assert len(energy_constraints) == 2
