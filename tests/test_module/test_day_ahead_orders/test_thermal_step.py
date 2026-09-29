"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Tests for the thermal day-ahead bidding step built on the common optimal dispatch.
"""

import pytest

from atlas.enums import ThermalDispatchState
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.steps.thermal.intermediate import ThermalIntermediateLoadOrders
from atlas.modules.day_ahead_orders.steps.thermal.optimisation import (
    ThermalDAOStep,
    ThermalOptimisationResult,
    build_dispatch_state_sequence,
    solve_thermal_unit,
)
from atlas.modules.day_ahead_orders.steps.thermal.step import optimize_single_thermal_unit
from atlas.solver.solver_interface import OptimisationModel
from atlas.timing import generate_datetimes
from tests.test_module.test_day_ahead_orders.conftest import STEPS_PARAMS_DICT


@pytest.fixture(scope="class")
def thermal_parameters() -> DayAheadOrdersParameters:
    """Step parameters pinned to SCIP — the default solver is Xpress, unavailable on CI."""
    return DayAheadOrdersParameters.model_validate(
        {**STEPS_PARAMS_DICT, "solver": {"solver_name": "SCIP"}, "price_forecasts_types": ["Medium"]}
    )


@pytest.fixture(scope="class")
def thermals(steps_input_dataset):
    return {thermal.name: thermal for thermal in steps_input_dataset.thermal}


def _build_model(thermal, parameters):
    """Formulate the step on a fresh model and return (model, step)."""
    prices = Timeseries.from_index(
        parameters.temporal.start_date,
        parameters.temporal.timestep,
        parameters.temporal.end_date + thermal.additional_hours,
        50.0,
    )
    model = OptimisationModel(parameters.solver.solver_name, f"test_{thermal.name}")
    model.set_direction("maximize")

    step = ThermalDAOStep(thermal, prices)
    step.add_variables(model, parameters)
    step.add_constraints(model, parameters)
    step.add_objective(model, parameters)
    return model, step


def _states(values: list[float], parameters) -> Timeseries:
    return Timeseries.from_values(
        start_date=parameters.temporal.start_date,
        frequency=parameters.temporal.timestep,
        values=values,
    )


class TestThermalDAOStep:
    def test_horizon_is_extended_by_the_unit_lookahead(self, thermals, thermal_parameters):
        """The model runs past the delivery day, by the unit's own additional_hours."""
        thermal = thermals["a_thermal_intermediate_1"]
        _, step = _build_model(thermal, thermal_parameters)

        expected = generate_datetimes(
            thermal_parameters.temporal.start_date,
            thermal_parameters.temporal.end_date + thermal.additional_hours - thermal_parameters.temporal.timestep,
            thermal_parameters.temporal.timestep,
        )
        assert step.time_frame == expected
        assert step.time_frame[-1] > thermal_parameters.temporal.end_date

    def test_day_ahead_specific_rows_are_added(self, thermals, thermal_parameters):
        """Contracted differences and reserve fill-up are the day-ahead part of the model."""
        thermal = thermals["a_thermal_intermediate_1"]
        model, step = _build_model(thermal, thermal_parameters)
        time = step.time_frame[0]

        for prefix in (
            "contracted_difference_up",
            "contracted_difference_down",
            "automated_contracted_difference_up",
            "automated_contracted_difference_down",
        ):
            assert f"{prefix}_{thermal.name}_{time}" in model.variables
            assert f"def_{prefix}_{thermal.name}_{time}" in model.constraints

        assert f"up_fillup_1_{time}_{thermal.name}" in model.constraints
        assert f"down_fillup_1_{time}_{thermal.name}" in model.constraints

    def test_physical_rows_come_from_the_shared_dispatch(self, thermals, thermal_parameters):
        """Power bounds, state exclusion and gradients are owned by ThermalDispatch."""
        thermal = thermals["a_thermal_intermediate_1"]
        model, step = _build_model(thermal, thermal_parameters)
        time = step.time_frame[0]

        assert f"lower_bound_{thermal.name}_{time}" in model.constraints
        assert f"upper_bound_{thermal.name}_{time}" in model.constraints
        assert f"mutual_exclusion_{time}_{thermal.name}" in model.constraints
        assert f"upward_gradient_{thermal.name}_{time}" in model.constraints

    def test_solved_states_follow_the_unit_phases(self, thermals, thermal_parameters):
        """A unit with ramps but no stable phase reports start/stop and no on_flat."""
        thermal = thermals["a_thermal_intermediate_1"]
        result = solve_thermal_unit(thermal, thermal_parameters, "Medium")

        assert result.start is not None
        assert result.stop is not None
        assert result.on_flat is None, "a 30-minute stable duration is below the hourly timestep"
        assert len(result.off.values) == len(
            generate_datetimes(
                thermal_parameters.temporal.start_date,
                thermal_parameters.temporal.end_date + thermal.additional_hours - thermal_parameters.temporal.timestep,
                thermal_parameters.temporal.timestep,
            )
        )
        assert set(result.off.values) <= {0.0, 1.0}


class TestThermalWorker:
    @pytest.mark.parametrize("name", ["a_thermal_base_1", "a_thermal_peak_1"])
    def test_base_and_peak_units_are_not_optimised(self, thermals, thermal_parameters, name):
        """Only intermediate units go through the LP — the others are pure heuristics."""
        assert optimize_single_thermal_unit(thermals[name], thermal_parameters) is None

    def test_intermediate_units_are_solved_once_per_scenario(self, thermals, thermal_parameters):
        solved = optimize_single_thermal_unit(thermals["a_thermal_intermediate_1"], thermal_parameters)

        assert solved is not None
        assert set(solved) == set(thermal_parameters.price_forecasts_types)


class TestStateSequences:
    def test_order_states_read_the_phases_off_the_result(self, thermal_parameters):
        """OFF is 0, online is 1, startup 2 and shutdown 3; absent phases are skipped."""
        formulator = ThermalIntermediateLoadOrders([], thermal_parameters)
        result = ThermalOptimisationResult(
            on_up=_states([0, 0, 1, 0], thermal_parameters),
            on_down=_states([0, 0, 0, 0], thermal_parameters),
            off=_states([1, 0, 0, 0], thermal_parameters),
            start=_states([0, 1, 0, 0], thermal_parameters),
            stop=_states([0, 0, 0, 1], thermal_parameters),
        )

        assert formulator.determine_intermediate_load_states_sequence(result).values == [0.0, 2.0, 1.0, 3.0]

    def test_order_states_ignore_a_missing_stable_phase(self, thermal_parameters):
        formulator = ThermalIntermediateLoadOrders([], thermal_parameters)
        result = ThermalOptimisationResult(
            on_up=_states([1, 0], thermal_parameters),
            on_down=_states([0, 1], thermal_parameters),
            off=_states([0, 0], thermal_parameters),
        )

        assert formulator.determine_intermediate_load_states_sequence(result).values == [1.0, 1.0]

    def test_dispatch_states_keep_the_regimes_distinct(self, thermal_parameters):
        """The sequence stored on the unit tells ramping up from ramping down."""
        result = ThermalOptimisationResult(
            on_up=_states([1, 0, 0, 0, 0, 0], thermal_parameters),
            on_down=_states([0, 1, 0, 0, 0, 0], thermal_parameters),
            off=_states([0, 0, 1, 0, 0, 0], thermal_parameters),
            start=_states([0, 0, 0, 1, 0, 0], thermal_parameters),
            stop=_states([0, 0, 0, 0, 1, 0], thermal_parameters),
            on_flat=_states([0, 0, 0, 0, 0, 1], thermal_parameters),
        )

        sequence = build_dispatch_state_sequence(result, thermal_parameters)

        assert sequence.values == [
            ThermalDispatchState.ON_UP,
            ThermalDispatchState.ON_DOWN,
            ThermalDispatchState.OFF,
            ThermalDispatchState.START,
            ThermalDispatchState.STOP,
            ThermalDispatchState.ON_FLAT,
        ]

    def test_dispatch_states_fall_back_to_unknown(self, thermal_parameters):
        """A timestep where the solver activated no state is reported, not dropped."""
        result = ThermalOptimisationResult(
            on_up=_states([0, 1], thermal_parameters),
            on_down=_states([0, 0], thermal_parameters),
            off=_states([0, 0], thermal_parameters),
        )

        assert build_dispatch_state_sequence(result, thermal_parameters).values == [
            ThermalDispatchState.UNKNOWN,
            ThermalDispatchState.ON_UP,
        ]
