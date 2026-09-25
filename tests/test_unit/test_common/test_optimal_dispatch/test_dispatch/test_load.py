"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
import pytest

from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.common.optimal_dispatch.dispatch.load import LoadDispatch
from atlas.common.optimal_dispatch.input_objects.load import LoadDispatchInput
from atlas.io_utils.parameters import DateParameters
from atlas.math.timeseries import Timeseries
from atlas.solver.solver_interface import OptimisationModel


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
    """Forecast = -50 MW (consumption, signed negative)."""
    return Timeseries.from_index(start_date, timestep, start_date.add(hours=3), -50.0)


@pytest.fixture
def equipment(node, portfolio, forecast_ts):
    from atlas.enums import LoadType
    from atlas.math.forecasting_matrix import ForecastingMatrix

    fm = ForecastingMatrix()
    eq = LoadDispatchInput(
        name="load_1",
        node=node,
        portfolio=portfolio,
        load_type=LoadType.BASE_LOAD,
        maximum_power_forecast=fm,
        additional_hours=pendulum.duration(hours=0),
    )
    eq._cached_forecast = forecast_ts
    return eq


@pytest.fixture
def model():
    return OptimisationModel("SCIP", "test_load_dispatch")


class TestLoadDispatchVariables:
    def test_setup_creates_power_level_var(self, equipment, model, parameters):
        d = LoadDispatch(equipment)
        d.setup(model, parameters)
        assert d.power_level_var is not None

    def test_add_variables_creates_expected_name(self, equipment, model, parameters, time_window):
        d = LoadDispatch(equipment)
        d.setup(model, parameters)
        t = time_window[0]
        d.add_variables(t)
        assert f"{equipment.name}_power_level_{t}" in model.variables

    def test_power_level_bounds_negative_floor(self, equipment, model, parameters, time_window):
        d = LoadDispatch(equipment)
        d.setup(model, parameters)
        t = time_window[0]
        d.add_variables(t)
        var = model.get_variable(f"{equipment.name}_power_level_{t}")
        assert var.lb() == pytest.approx(-50.0)
        assert var.ub() == 0

    def test_power_level_bounds_zero_without_forecast(self, node, portfolio, model, parameters, time_window):
        from atlas.enums import LoadType
        from atlas.math.forecasting_matrix import ForecastingMatrix

        eq = LoadDispatchInput(
            name="load_2",
            node=node,
            portfolio=portfolio,
            load_type=LoadType.BASE_LOAD,
            maximum_power_forecast=ForecastingMatrix(),
            additional_hours=pendulum.duration(hours=0),
        )
        d = LoadDispatch(eq)
        d.setup(model, parameters)
        t = time_window[0]
        d.add_variables(t)
        var = model.get_variable(f"{eq.name}_power_level_{t}")
        assert var.lb() == 0
        assert var.ub() == 0


class TestLoadDispatchHelpers:
    def test_max_power_returns_signed_forecast(self, equipment, model, parameters, time_window):
        d = LoadDispatch(equipment)
        d.setup(model, parameters)
        assert d.max_power(time_window[0]) == pytest.approx(-50.0)

    def test_max_power_returns_zero_when_time_missing(self, equipment, model, parameters):
        d = LoadDispatch(equipment)
        d.setup(model, parameters)
        outside = pendulum.datetime(2099, 1, 1)
        assert d.max_power(outside) == 0.0

    def test_max_power_fallback_to_forecasting_matrix(self, node, portfolio, model, parameters, start_date, timestep):
        from atlas.enums import LoadType
        from atlas.math.forecasting_matrix import ForecastingMatrix

        ts = Timeseries.from_index(start_date, timestep, start_date.add(hours=3), -30.0)
        fm = ForecastingMatrix()
        fm.add(ts, parameters.temporal.execution_date)
        eq = LoadDispatchInput(
            name="load_fb",
            node=node,
            portfolio=portfolio,
            load_type=LoadType.BASE_LOAD,
            maximum_power_forecast=fm,
            additional_hours=pendulum.duration(hours=0),
        )
        d = LoadDispatch(eq)
        d.setup(model, parameters)
        assert d.max_power(start_date) == pytest.approx(-30.0)


class TestLoadDispatchConstraints:
    def test_add_constraints_emits_min_and_max_bounds(self, equipment, model, parameters, time_window):
        d = LoadDispatch(equipment)
        d.setup(model, parameters)
        t = time_window[0]
        d.add_variables(t)
        d.add_constraints(model, t)
        n = equipment.name
        assert f"power_max_{t}_{n}" in model.constraints
        assert f"power_min_{t}_{n}" in model.constraints
