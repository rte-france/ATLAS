"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Fixtures shared by the ThermalDispatch tests that live in their own files.

``test_thermal.py`` keeps its own copies, which take precedence in that module.
"""

import pendulum
import pytest

from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.common.optimal_dispatch.dispatch.thermal import ThermalDispatch
from atlas.common.optimal_dispatch.input_objects.thermal import ThermalDispatchInput
from atlas.io_utils.parameters import DateParameters
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.solver.solver_interface import OptimisationModel


@pytest.fixture
def start_date():
    return pendulum.datetime(2024, 1, 1)


@pytest.fixture
def timestep():
    return pendulum.duration(hours=1)


def _constant_series(start_date, timestep, value):
    return Timeseries.from_index(
        start_date=start_date.subtract(days=1),
        frequency=timestep,
        end_date=start_date.add(days=2),
        default_value=value,
    )


@pytest.fixture
def power_ts(start_date, timestep):
    return _constant_series(start_date, timestep, 200.0)


@pytest.fixture
def min_power_ts(start_date, timestep):
    return _constant_series(start_date, timestep, 50.0)


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
def power_history(start_date, timestep, parameters):
    """Return a function building the ``power`` history of a unit from its last values, oldest first."""

    def make(values):
        series = Timeseries.from_index(
            start_date=start_date - timestep * len(values),
            frequency=timestep,
            end_date=start_date - timestep,
            default_value=values[0],
        )
        for index, value in enumerate(values):
            series.set_value(start_date - timestep * (len(values) - index), value)
        history = ForecastingMatrix()
        history.add(series, parameters.temporal.execution_date)
        return history

    return make


@pytest.fixture
def build_thermal_dispatch(node, portfolio, power_ts, min_power_ts, parameters, model):
    """
    Return a function that builds a ThermalDispatch over the 4 hours window of ``parameters``.

    The unit has a 3 hours minimum time on and a 2 hours minimum time off unless told otherwise. The variables
    and every constraint row, gradient rows included, are added to ``model``.

    Pass ``maximum_power`` for a custom series, and any other ThermalDispatchInput field as keyword
    (``power`` being the history of the unit, see ``power_history``).
    It returns ``(equipment, dispatch, window)``.
    """

    def build(*, maximum_power=None, **equipment_fields):
        fields = {
            "minimum_time_on": pendulum.duration(hours=3),
            "minimum_time_off": pendulum.duration(hours=2),
            "minimum_stable_power_duration": pendulum.duration(hours=0),
            **equipment_fields,
        }
        equipment = ThermalDispatchInput(
            name="th_unit",
            node=node,
            portfolio=portfolio,
            maximum_power=maximum_power if maximum_power is not None else power_ts,
            minimum_power=min_power_ts,
            **fields,
        )
        dispatch = ThermalDispatch(equipment)
        dispatch.setup(model, parameters)
        window = [parameters.temporal.start_date.add(hours=hour) for hour in range(4)]
        dispatch.add_variables(window)
        for time in window:
            dispatch.add_constraints(model, time, parameters)
            dispatch.add_dd_and_gradient_constraints(model, time, time - parameters.temporal.timestep)
        return equipment, dispatch, window

    return build
