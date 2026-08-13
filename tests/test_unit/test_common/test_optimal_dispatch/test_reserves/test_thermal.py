"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
import pytest

from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.common.optimal_dispatch.dispatch.thermal import ThermalDispatch
from atlas.common.optimal_dispatch.input_objects.thermal import ThermalDispatchInput
from atlas.common.optimal_dispatch.reserves.thermal import ThermalReserveHandler
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
def time(start_date):
    return start_date


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
    return OptimisationModel("SCIP", "test_thermal_reserves")


def _make_equipment(node, portfolio, power_ts, min_power_ts, **kwargs):
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


def _setup_dispatch(equipment, model, parameters, time_window):
    """Helper: create, setup and populate dispatch variables for each time in the window."""
    d = ThermalDispatch(equipment)
    d.setup(model, parameters)
    for t in time_window:
        d.add_variables(t)
    return d


@pytest.fixture
def comb1_equipment(node, portfolio, power_ts, min_power_ts):
    return _make_equipment(node, portfolio, power_ts, min_power_ts)


@pytest.fixture
def comb1_dispatch(comb1_equipment, model, parameters, time):
    return _setup_dispatch(comb1_equipment, model, parameters, [time])


@pytest.fixture
def handler(comb1_dispatch):
    h = ThermalReserveHandler(name="th_unit", dispatch=comb1_dispatch, maximum_automated=15.0)
    return h


class TestThermalReserveHandlerVariables:
    def test_add_variables_creates_all_seven_vars(self, handler, model, time):
        handler.setup(model)
        handler.add_variables(time, max_power=200.0, min_power=50.0)

        assert f"reserves_up_th_unit_{time}" in model.variables
        assert f"reserves_down_th_unit_{time}" in model.variables
        assert f"unprovided_reserves_up_th_unit_{time}" in model.variables
        assert f"unprovided_reserves_down_th_unit_{time}" in model.variables
        assert f"relaxed_reserves_th_unit_{time}" in model.variables
        assert f"automated_reserves_up_th_unit_{time}" in model.variables
        assert f"automated_reserves_down_th_unit_{time}" in model.variables

    def test_reserves_up_bounds(self, handler, model, time):
        handler.setup(model)
        handler.add_variables(time, max_power=200.0, min_power=50.0)

        var = model.get_variable(f"reserves_up_th_unit_{time}")
        assert var.lb() == 0
        assert var.ub() == pytest.approx(200.0)

    def test_reserves_down_bounds(self, handler, model, time):
        handler.setup(model)
        handler.add_variables(time, max_power=200.0, min_power=50.0)

        var = model.get_variable(f"reserves_down_th_unit_{time}")
        assert var.lb() == 0
        assert var.ub() == pytest.approx(200.0)

    def test_relaxed_reserves_upper_bound_is_min_power(self, handler, model, time):
        handler.setup(model)
        handler.add_variables(time, max_power=200.0, min_power=50.0)

        var = model.get_variable(f"relaxed_reserves_th_unit_{time}")
        assert var.lb() == 0
        assert var.ub() == pytest.approx(50.0)

    def test_automated_reserves_bounds(self, handler, model, time):
        handler.setup(model)
        handler.add_variables(time, max_power=200.0, min_power=50.0)

        for prefix in ("automated_reserves_up", "automated_reserves_down"):
            var = model.get_variable(f"{prefix}_th_unit_{time}")
            assert var.lb() == 0
            assert var.ub() == pytest.approx(15.0)

    def test_requires_setup_before_add_variables(self, handler, time):
        with pytest.raises(RuntimeError):
            handler.add_variables(time, max_power=200.0, min_power=50.0)


class TestThermalReserveHandlerFillUpConstraints:
    def _setup_all(self, handler, model, time, max_power=200.0, min_power=50.0):
        handler.setup(model)
        handler.add_variables(time, max_power=max_power, min_power=min_power)
        power_var = model.add_continuous_variable("power_level", 0, max_power)
        return power_var

    def test_fill_up_constraint_names(self, handler, model, time):
        power_var = self._setup_all(handler, model, time)

        handler.add_fill_up_constraints(time, power_var, max_power=200.0, min_power=50.0, epsilon=0.01)

        assert f"up_fillup_1_{time}_th_unit" in model.constraints
        assert f"up_fillup_2_{time}_th_unit" in model.constraints
        assert f"down_fillup_1_{time}_th_unit" in model.constraints
        assert f"down_fillup_2_{time}_th_unit" in model.constraints

    def test_four_constraints_added(self, handler, model, time):
        power_var = self._setup_all(handler, model, time)
        before = len(model.constraints)

        handler.add_fill_up_constraints(time, power_var, max_power=200.0, min_power=50.0, epsilon=0.01)

        assert len(model.constraints) - before == 4


class TestThermalReserveHandlerRelaxedReserveConstraint:
    def test_relaxed_reserve_constraint_name(self, handler, model, time):
        handler.setup(model)
        handler.add_variables(time, max_power=200.0, min_power=50.0)

        handler.add_relaxed_reserve_constraint(time, min_power=50.0)

        assert f"relaxed_reserves_{time}_th_unit" in model.constraints

    def test_one_constraint_added(self, handler, model, time):
        handler.setup(model)
        handler.add_variables(time, max_power=200.0, min_power=50.0)
        before = len(model.constraints)

        handler.add_relaxed_reserve_constraint(time, min_power=50.0)

        assert len(model.constraints) - before == 1


class TestThermalReserveHandlerCapacityConstraints:
    def _full_setup(self, handler, model, time):
        handler.setup(model)
        handler.add_variables(time, max_power=200.0, min_power=50.0)

    def test_capacity_constraint_names_combination_1(self, handler, model, time):
        """Combination 1: unavailable = off only → 4 capacity constraints."""
        self._full_setup(handler, model, time)

        handler.add_capacity_constraints(time, max_power=200.0)

        n = "th_unit"
        assert f"automated_reserves_up_max_{time}_{n}" in model.constraints
        assert f"automated_reserves_down_max_{time}_{n}" in model.constraints
        assert f"reserves_up_max_{time}_{n}" in model.constraints
        assert f"reserves_down_max_{time}_{n}" in model.constraints

    def test_four_constraints_for_combination_1(self, handler, model, time):
        self._full_setup(handler, model, time)
        before = len(model.constraints)

        handler.add_capacity_constraints(time, max_power=200.0)

        assert len(model.constraints) - before == 4

    def test_capacity_constraints_with_stop(
        self, node, portfolio, power_ts, min_power_ts, model, parameters, time
    ):
        """Combination 2: unavailable = off + stop_var."""
        eq = _make_equipment(
            node, portfolio, power_ts, min_power_ts,
            shutdown_duration=pendulum.duration(hours=2),
        )
        d = _setup_dispatch(eq, model, parameters, [time])
        h = ThermalReserveHandler(name=eq.name, dispatch=d, maximum_automated=15.0)
        h.setup(model)
        h.add_variables(time, max_power=200.0, min_power=50.0)

        h.add_capacity_constraints(time, max_power=200.0)

        assert f"automated_reserves_up_max_{time}_{eq.name}" in model.constraints
        assert f"automated_reserves_down_max_{time}_{eq.name}" in model.constraints

    def test_capacity_constraints_with_start(
        self, node, portfolio, power_ts, min_power_ts, model, parameters, time
    ):
        """Combination 4: unavailable = off + on_start_var."""
        eq = _make_equipment(
            node, portfolio, power_ts, min_power_ts,
            startup_duration=pendulum.duration(hours=2),
        )
        d = _setup_dispatch(eq, model, parameters, [time])
        h = ThermalReserveHandler(name=eq.name, dispatch=d, maximum_automated=15.0)
        h.setup(model)
        h.add_variables(time, max_power=200.0, min_power=50.0)

        h.add_capacity_constraints(time, max_power=200.0)

        assert f"automated_reserves_up_max_{time}_{eq.name}" in model.constraints
        assert f"automated_reserves_down_max_{time}_{eq.name}" in model.constraints

    def test_capacity_constraints_with_flat(
        self, node, portfolio, power_ts, min_power_ts, model, parameters, time
    ):
        """Combination 3: has_flat → res_unavailable adds on_up + on_down ramp states."""
        eq = _make_equipment(
            node, portfolio, power_ts, min_power_ts,
            minimum_stable_power_duration=pendulum.duration(hours=3),
        )
        d = _setup_dispatch(eq, model, parameters, [time])
        h = ThermalReserveHandler(name=eq.name, dispatch=d, maximum_automated=15.0)
        h.setup(model)
        h.add_variables(time, max_power=200.0, min_power=50.0)

        h.add_capacity_constraints(time, max_power=200.0)

        n = eq.name
        assert f"reserves_up_max_{time}_{n}" in model.constraints
        assert f"reserves_down_max_{time}_{n}" in model.constraints
