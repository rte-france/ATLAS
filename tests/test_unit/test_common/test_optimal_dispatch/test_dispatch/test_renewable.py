"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from dataclasses import dataclass

import pendulum
import pytest

from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.common.optimal_dispatch.dispatch.renewable import RenewableDispatch
from atlas.io_utils.parameters import DateParameters
from atlas.math.timeseries import Timeseries
from atlas.solver.solver_interface import OptimisationModel


@dataclass
class _RenewableStub:
    """Minimal structural fixture satisfying ``RenewableDispatchInput``."""

    name: str
    maximum_curtailment_ratio: Timeseries
    _cached_forecast: Timeseries | None


@pytest.fixture
def start_date():
    return pendulum.datetime(2024, 1, 1)


@pytest.fixture
def timestep():
    return pendulum.duration(hours=1)


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
def time_window(start_date):
    return [start_date.add(hours=h) for h in range(4)]


@pytest.fixture
def forecast_ts(start_date, timestep):
    """Forecast = 100 MW over the whole window."""
    return Timeseries.from_index(start_date, timestep, start_date.add(hours=3), 100.0)


@pytest.fixture
def curtailment_ts(start_date, timestep):
    """Curtailment ratio = 0.2 → min_power = 80 MW."""
    return Timeseries.from_index(start_date, timestep, start_date.add(hours=3), 0.2)


@pytest.fixture
def equipment(forecast_ts, curtailment_ts):
    return _RenewableStub(name="wind_1", maximum_curtailment_ratio=curtailment_ts, _cached_forecast=forecast_ts)


@pytest.fixture
def model():
    return OptimisationModel("SCIP", "test_renewable_dispatch")


class TestRenewableDispatchVariables:
    def test_setup_creates_power_level_var(self, equipment, model, parameters):
        d = RenewableDispatch(equipment)
        d.setup(model, parameters)
        assert d.power_level_var is not None

    def test_add_variables_creates_expected_name(self, equipment, model, parameters, time_window):
        d = RenewableDispatch(equipment)
        d.setup(model, parameters)
        t = time_window[0]
        d.add_variables(t)
        assert f"{equipment.name}_power_level_{t}" in model.variables

    def test_power_level_bounds_match_forecast(self, equipment, model, parameters, time_window):
        d = RenewableDispatch(equipment)
        d.setup(model, parameters)
        t = time_window[0]
        d.add_variables(t)
        var = model.get_variable(f"{equipment.name}_power_level_{t}")
        assert var.lb() == 0
        assert var.ub() == pytest.approx(100.0)

    def test_power_level_bounds_zero_when_no_forecast(self, curtailment_ts, model, parameters, time_window):
        eq = _RenewableStub(name="solar_1", maximum_curtailment_ratio=curtailment_ts, _cached_forecast=None)
        d = RenewableDispatch(eq)
        d.setup(model, parameters)
        t = time_window[0]
        d.add_variables(t)
        var = model.get_variable(f"{eq.name}_power_level_{t}")
        assert var.lb() == 0
        assert var.ub() == 0


class TestRenewableDispatchHelpers:
    def test_max_power_uses_cached_forecast(self, equipment, model, parameters, time_window):
        d = RenewableDispatch(equipment)
        d.setup(model, parameters)
        assert d.max_power(time_window[0]) == pytest.approx(100.0)

    def test_max_power_returns_zero_without_forecast(self, curtailment_ts, model, parameters, time_window):
        eq = _RenewableStub(name="solar_1", maximum_curtailment_ratio=curtailment_ts, _cached_forecast=None)
        d = RenewableDispatch(eq)
        d.setup(model, parameters)
        assert d.max_power(time_window[0]) == 0.0

    def test_min_power_curtailment_applied(self, equipment, model, parameters, time_window):
        d = RenewableDispatch(equipment)
        d.setup(model, parameters)
        # min_power = (1 - 0.2) * 100 = 80
        assert d.min_power(time_window[0]) == pytest.approx(80.0)


class TestRenewableDispatchConstraints:
    def test_add_constraints_emits_max_and_min_bounds(self, equipment, model, parameters, time_window):
        d = RenewableDispatch(equipment)
        d.setup(model, parameters)
        t = time_window[0]
        d.add_variables(t)
        d.add_constraints(model, t)
        n = equipment.name
        assert f"power_max_{t}_{n}" in model.constraints
        assert f"power_min_{t}_{n}" in model.constraints
