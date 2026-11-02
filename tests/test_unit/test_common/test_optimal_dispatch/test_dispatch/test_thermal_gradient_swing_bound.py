"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
import pytest

from atlas.math.timeseries import Timeseries
from atlas.solver.models import SolverStatus

GRADIENT_VARIABLES = ("up_grad", "down_grad", "aux_up_grad", "aux_down_grad", "dd_grad")


def _series(start_date, timestep, value, **overrides_by_hour):
    series = Timeseries.from_index(
        start_date=start_date.subtract(days=1),
        frequency=timestep,
        end_date=start_date.add(days=2),
        default_value=value,
    )
    for hour, hour_value in overrides_by_hour.items():
        series.set_value(start_date.add(hours=int(hour.removeprefix("h"))), hour_value)
    return series


@pytest.fixture
def spiked_power(start_date, timestep):
    """200 everywhere but a 900 spike a day after the start of the window, far outside of it."""
    series = _series(start_date, timestep, 200.0)
    series.set_value(start_date.add(days=1), 900.0)
    return series


@pytest.mark.parametrize("variable", GRADIENT_VARIABLES)
def test_the_gradient_auxiliaries_are_bounded_by_the_widest_power_swing_of_the_series(
    build_thermal_dispatch, model, spiked_power, variable
):
    """Both ramps and a stable phase, so that the five auxiliaries exist."""
    equipment, _, window = build_thermal_dispatch(
        maximum_power=spiked_power,
        startup_duration=pendulum.duration(hours=2),
        shutdown_duration=pendulum.duration(hours=2),
        minimum_stable_power_duration=pendulum.duration(hours=3),
    )

    bounded = model.get_variable(f"{variable}_{equipment.name}_{window[0]}")

    assert bounded.lb() == -900.0
    assert bounded.ub() == 900.0


def test_the_linearisation_rows_use_the_same_swing(build_thermal_dispatch, model, spiked_power):
    equipment, _, window = build_thermal_dispatch(
        maximum_power=spiked_power,
        minimum_stable_power_duration=pendulum.duration(hours=3),
    )
    row = model.get_constraint(f"tilde_U_evol_1_{window[1]}_{equipment.name}")
    on_up_before = model.get_variable(f"on_up_{equipment.name}_{window[0]}")

    assert abs(row.GetCoefficient(on_up_before)) == 900.0


def test_a_step_down_larger_than_the_new_maximum_power_stays_feasible(
    build_thermal_dispatch, model, start_date, timestep, power_history
):
    """
    The maximum power falls from 200 to 100 while the unit steps down by 150.

    The step is within its gradient (3 per minute, 180 per step) and above its minimum power. The rows used
    the maximum power of the current step, 100, and so forbade a step they allow in both directions.
    """
    equipment, dispatch, window = build_thermal_dispatch(
        maximum_power=_series(start_date, timestep, 200.0, **{f"h{hour}": 100.0 for hour in range(2, 24)}),
        maximum_gradient=3.0,
        minimum_stable_power_duration=pendulum.duration(hours=2),
        power=power_history([200.0] * 10),
    )
    for hour, value in {0: 200.0, 1: 200.0, 2: 50.0}.items():
        model.add_constraint(dispatch.power_level[window[hour]] == value, f"force_{hour}")
    model.set_direction("minimize")
    model.set_objective(dispatch.power_level[window[0]])

    assert model.solve().status == SolverStatus.OPTIMAL
