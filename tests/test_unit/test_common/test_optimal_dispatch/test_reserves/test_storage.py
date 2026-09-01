"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
import pytest

from atlas.common.optimal_dispatch.reserves.storage import StorageReserveHandler
from atlas.enums import SolverStatus
from atlas.solver.solver_interface import OptimisationModel


@pytest.fixture
def model():
    return OptimisationModel("SCIP", "test_storage_reserves")


@pytest.fixture
def time():
    return pendulum.datetime(2024, 1, 1)


@pytest.fixture
def handler():
    return StorageReserveHandler(name="bat_1", maximum_automated=10.0)


class TestStorageReserveHandlerVariables:
    def test_add_variables_creates_all_reserve_vars(self, handler, model, time):
        handler.setup(model)
        handler.add_variables(time, max_power=100.0, min_power=-50.0)

        assert f"reserves_up_bat_1_{time}" in model.variables
        assert f"reserves_down_bat_1_{time}" in model.variables
        assert f"unprovided_reserves_up_bat_1_{time}" in model.variables
        assert f"unprovided_reserves_down_bat_1_{time}" in model.variables
        assert f"automated_reserves_up_bat_1_{time}" in model.variables
        assert f"automated_reserves_down_bat_1_{time}" in model.variables

    def test_reserves_up_bounds(self, handler, model, time):
        handler.setup(model)
        handler.add_variables(time, max_power=100.0, min_power=-50.0)

        var = model.get_variable(f"reserves_up_bat_1_{time}")
        assert var.lb() == 0
        assert var.ub() == pytest.approx(100.0)

    def test_reserves_down_lower_bound_is_negative(self, handler, model, time):
        """reserves_down lower bound matches min_power (negative) to preserve original LP bounds."""
        handler.setup(model)
        handler.add_variables(time, max_power=100.0, min_power=-50.0)

        var = model.get_variable(f"reserves_down_bat_1_{time}")
        assert var.lb() == pytest.approx(-50.0)
        assert var.ub() == pytest.approx(100.0)

    def test_automated_reserves_down_is_bidirectional(self, handler, model, time):
        """automated_reserves_down for storage is bidirectional [-max_automated, max_automated]."""
        handler.setup(model)
        handler.add_variables(time, max_power=100.0, min_power=-50.0)

        var = model.get_variable(f"automated_reserves_down_bat_1_{time}")
        assert var.lb() == pytest.approx(-10.0)
        assert var.ub() == pytest.approx(10.0)

    def test_requires_setup_before_add_variables(self, handler, time):
        with pytest.raises(RuntimeError):
            handler.add_variables(time, max_power=100.0, min_power=-50.0)


class TestStorageReserveHandlerConstraints:
    def _setup_with_vars(self, handler, model, time, max_power=100.0, sell_var=None, buy_var=None):
        handler.setup(model)
        handler.add_variables(time, max_power=max_power, min_power=-max_power)
        _sell = sell_var or model.add_continuous_variable("sell", 0, max_power)
        _buy = buy_var or model.add_continuous_variable("buy", -max_power, 0)
        return _sell, _buy

    def test_fill_up_constraints_names(self, handler, model, time):
        sell, buy = self._setup_with_vars(handler, model, time)

        handler.add_fill_up_constraints(time, sell, buy, max_sell=90.0, min_buy=-55.0)

        assert f"generic_power_max_{time}_bat_1" in model.constraints
        assert f"generic_power_min_{time}_bat_1" in model.constraints

    def test_capacity_constraints_names(self, handler, model, time):
        sell, buy = self._setup_with_vars(handler, model, time)
        stored_energy = model.add_continuous_variable("stored_energy", 0, 500.0)

        handler.add_capacity_constraints(
            time,
            stored_energy,
            max_energy=500.0,
            min_soc=0.1,
            reserve_duration_h=1.0,
            automated_reserve_duration_h=0.5,
        )

        assert f"min_storage_level_{time}_bat_1" in model.constraints
        assert f"max_storage_level_{time}_bat_1" in model.constraints


class TestStorageReserveHandlerCapacitySolved:
    """
    Solve for the stored-energy floor/ceiling the capacity constraints impose, so the
    duration coefficients are checked rather than just the constraint names. Manual and
    automated durations are distinct values here — swapping them changes the result.
    """

    def _pin_reserves(self, handler, model, time, up: float, automated_up: float, down: float, automated_down: float):
        handler.setup(model)
        handler.add_variables(time, max_power=100.0, min_power=-100.0)
        for prefix, value in (
            ("reserves_up", up),
            ("automated_reserves_up", automated_up),
            ("reserves_down", down),
            ("automated_reserves_down", automated_down),
        ):
            model.add_constraint(model.get_variable(handler.var(prefix, time)) == value, f"pin_{prefix}")

    def test_min_storage_level_accounts_for_up_reserves(self, handler, model, time):
        self._pin_reserves(handler, model, time, up=4.0, automated_up=6.0, down=0.0, automated_down=0.0)
        stored_energy = model.add_continuous_variable("stored_energy", 0, 500.0)
        handler.add_capacity_constraints(
            time, stored_energy, max_energy=500.0, min_soc=0.1,
            reserve_duration_h=2.0, automated_reserve_duration_h=0.5,
        )

        model.set_direction("minimize")
        model.set_objective(stored_energy)
        assert model.solve().status == SolverStatus.OPTIMAL

        # floor = min_soc * max_energy + up * 2 h + automated_up * 0.5 h = 50 + 8 + 3
        assert stored_energy.solution_value() == pytest.approx(61.0)

    def test_max_storage_level_accounts_for_down_reserves(self, handler, model, time):
        self._pin_reserves(handler, model, time, up=0.0, automated_up=0.0, down=4.0, automated_down=6.0)
        stored_energy = model.add_continuous_variable("stored_energy", 0, 500.0)
        handler.add_capacity_constraints(
            time, stored_energy, max_energy=500.0, min_soc=0.1,
            reserve_duration_h=2.0, automated_reserve_duration_h=0.5,
        )

        model.set_direction("maximize")
        model.set_objective(stored_energy)
        assert model.solve().status == SolverStatus.OPTIMAL

        # ceiling = max_energy - (down * 2 h + automated_down * 0.5 h) = 500 - 11
        assert stored_energy.solution_value() == pytest.approx(489.0)
