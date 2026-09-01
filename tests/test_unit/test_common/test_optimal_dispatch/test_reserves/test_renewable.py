"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
import pytest

from atlas.common.optimal_dispatch.reserves.renewable import RenewableReserveHandler
from atlas.solver.solver_interface import OptimisationModel


@pytest.fixture
def model():
    return OptimisationModel("SCIP", "test_renewable_reserves")


@pytest.fixture
def time():
    return pendulum.datetime(2024, 1, 1)


@pytest.fixture
def handler():
    return RenewableReserveHandler(name="wind_1", maximum_automated=10.0)


class TestRenewableReserveHandlerVariables:
    def test_add_variables_creates_all_reserve_vars(self, handler, model, time):
        handler.setup(model)
        handler.add_variables(time, max_power=100.0, min_power=80.0)

        assert f"reserves_up_wind_1_{time}" in model.variables
        assert f"reserves_down_wind_1_{time}" in model.variables
        assert f"unprovided_reserves_up_wind_1_{time}" in model.variables
        assert f"unprovided_reserves_down_wind_1_{time}" in model.variables
        assert f"automated_reserves_up_wind_1_{time}" in model.variables
        assert f"automated_reserves_down_wind_1_{time}" in model.variables

    def test_no_relaxed_reserves_variable(self, handler, model, time):
        """Renewables have no relaxed_reserves variable (unlike thermals)."""
        handler.setup(model)
        handler.add_variables(time, max_power=100.0, min_power=80.0)
        assert f"relaxed_reserves_wind_1_{time}" not in model.variables

    def test_reserves_up_bounds(self, handler, model, time):
        handler.setup(model)
        handler.add_variables(time, max_power=100.0, min_power=80.0)

        var = model.get_variable(f"reserves_up_wind_1_{time}")
        assert var.lb() == 0
        assert var.ub() == pytest.approx(100.0)

    def test_reserves_down_lower_bound_is_min_power(self, handler, model, time):
        """For renewables, ``reserves_down`` lower bound matches ``min_power`` (curtailed floor)."""
        handler.setup(model)
        handler.add_variables(time, max_power=100.0, min_power=80.0)

        var = model.get_variable(f"reserves_down_wind_1_{time}")
        assert var.lb() == pytest.approx(80.0)
        assert var.ub() == pytest.approx(100.0)

    def test_automated_reserves_bounds(self, handler, model, time):
        handler.setup(model)
        handler.add_variables(time, max_power=100.0, min_power=80.0)

        up_var = model.get_variable(f"automated_reserves_up_wind_1_{time}")
        dn_var = model.get_variable(f"automated_reserves_down_wind_1_{time}")
        # Renewables are unidirectional (unlike storage), bounds [0, max_automated].
        assert up_var.lb() == 0
        assert up_var.ub() == pytest.approx(10.0)
        assert dn_var.lb() == 0
        assert dn_var.ub() == pytest.approx(10.0)

    def test_requires_setup_before_add_variables(self, handler, time):
        with pytest.raises(RuntimeError):
            handler.add_variables(time, max_power=100.0, min_power=80.0)


class TestRenewableReserveHandlerConstraints:
    def test_capacity_constraints_names(self, handler, model, time):
        handler.setup(model)
        handler.add_variables(time, max_power=100.0, min_power=80.0)

        handler.add_capacity_constraints(time, max_power=100.0)

        assert f"reserves_up_max_{time}_wind_1" in model.constraints
        assert f"reserves_down_max_{time}_wind_1" in model.constraints

    def test_automated_capacity_constraints_names(self, handler, model, time):
        handler.setup(model)
        handler.add_variables(time, max_power=100.0, min_power=80.0)

        handler.add_automated_capacity_constraints(time)

        assert f"automated_reserves_up_max_{time}_wind_1" in model.constraints
        assert f"automated_reserves_down_max_{time}_wind_1" in model.constraints
