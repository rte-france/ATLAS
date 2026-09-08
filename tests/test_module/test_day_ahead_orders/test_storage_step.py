"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Tests for the storage day-ahead bidding step built on the common optimal dispatch.
"""

import pytest

from atlas.enums import OrderType, StorageType
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.steps.storage.optimisation import StorageDAOStep, optimize_single_storage
from atlas.modules.day_ahead_orders.steps.storage.orders import build_storage_bids
from atlas.solver.solver_interface import OptimisationModel
from atlas.timing import generate_datetimes

NB_FRAGMENTS = 3
SMOOTHING_FACTOR = 0.1


@pytest.fixture(scope="class")
def local_timewindow(steps_parameters):
    return generate_datetimes(
        steps_parameters.temporal.start_date,
        steps_parameters.penultimate_date,
        steps_parameters.temporal.timestep,
    )


@pytest.fixture(scope="class")
def storages(steps_input_dataset):
    return {storage.name: storage for storage in steps_input_dataset.storage}


def _build_model(storage, parameters):
    """Formulate the step on a fresh model and return (model, step, time_window)."""
    time_window = generate_datetimes(
        parameters.temporal.start_date,
        parameters.temporal.end_date + storage.additional_hours - parameters.temporal.timestep,
        parameters.temporal.timestep,
    )
    model = OptimisationModel(parameters.solver.solver_name, f"test_{storage.name}")
    model.set_direction("maximize")

    step = StorageDAOStep(storage, time_window, NB_FRAGMENTS, SMOOTHING_FACTOR)
    step.add_variables(model, parameters)
    step.add_constraints(model, parameters)
    step.add_objective(model, parameters, dict.fromkeys(time_window, 50.0))
    return model, step, time_window


class TestStorageDAOStep:
    def test_buy_power_is_negative_and_sell_positive(self, storages, steps_parameters):
        """The step follows the dispatch sign convention: charging is negative power."""
        storage = storages["a_battery_1"]
        model, step, time_window = _build_model(storage, steps_parameters)
        time = time_window[0]

        buy = step.dispatch.power_level_buy_var.get_value(time)
        sell = step.dispatch.power_level_sell_var.get_value(time)

        assert buy.lb() == storage.minimum_power.get_value(time) < 0
        assert buy.ub() == 0
        assert sell.lb() == 0
        assert sell.ub() == storage.maximum_power.get_value(time) > 0

    def test_fragment_bounds_split_the_power_range(self, storages, steps_parameters):
        """Fragments are bounded on the variables, not through constraints."""
        storage = storages["a_battery_1"]
        model, step, time_window = _build_model(storage, steps_parameters)
        time = time_window[0]

        for n in range(NB_FRAGMENTS):
            sell_n = step.dispatch.get_fragment_sell_var(time, n)
            buy_n = step.dispatch.get_fragment_buy_var(time, n)
            assert sell_n.ub() == pytest.approx(storage.maximum_power.get_value(time) / NB_FRAGMENTS)
            assert buy_n.lb() == pytest.approx(storage.minimum_power.get_value(time) / NB_FRAGMENTS)

    def test_battery_is_cycle_balanced(self, storages, steps_parameters):
        """A battery must return to its initial state of charge, and has no driving to pay back."""
        storage = storages["a_battery_1"]
        model, _, _ = _build_model(storage, steps_parameters)

        assert f"cycle_balance_{storage.name}" in model.constraints
        assert f"DisplacementEnergy_compensation_for_{storage.name}" not in model.constraints

    def test_electric_vehicle_compensates_displacement_instead(self, storages, steps_parameters):
        """An EV only has to pay back its driving energy, it is free to end the horizon anywhere."""
        storage = storages["a_electric_vehicle_1"]
        assert storage.storage_type == StorageType.ELECTRIC_VEHICLE
        model, _, _ = _build_model(storage, steps_parameters)

        assert f"DisplacementEnergy_compensation_for_{storage.name}" in model.constraints
        assert f"cycle_balance_{storage.name}" not in model.constraints

    def test_every_timestep_is_constrained(self, storages, steps_parameters):
        """Level evolution, sell/buy separation and fragment sums are added for each timestep."""
        storage = storages["a_battery_1"]
        model, _, time_window = _build_model(storage, steps_parameters)

        for prefix in ("storage_level_evol", "relative_power_max", "relative_power_min"):
            assert sum(name.startswith(prefix) for name in model.constraints) == len(time_window)
        for prefix in ("sell_fragment_sum", "buy_fragment_sum"):
            assert sum(name.startswith(prefix) for name in model.constraints) == len(time_window)


class TestStorageBids:
    def test_solved_battery_bids_a_price_curve(self, storages, steps_parameters, local_timewindow):
        """A solved battery formulates buy and sell orders at a single pair of prices."""
        storage = storages["a_battery_1"]
        result = optimize_single_storage(storage, steps_parameters, local_timewindow)
        assert result is not None

        bids = build_storage_bids(storage, result, steps_parameters, local_timewindow)

        assert all(volume >= 0 for volume in result.buy_volumes.values())
        assert all(volume >= 0 for volume in result.sell_volumes.values())
        assert len(bids.orders) == len(result.buy_volumes) + len(result.sell_volumes)
        assert len(bids.order_couplings) == 1
        assert bids.order_couplings[0].orders == bids.orders

        for order_type in (OrderType.Buy, OrderType.Sell):
            prices = {order.price for order in bids.orders if order.order_type == order_type}
            assert len(prices) == 1, f"{order_type} orders should share a single price, got {prices}"

    def test_zero_capacity_unit_is_skipped(self, storages, steps_parameters, local_timewindow):
        """A unit with no energy capacity over the window is not optimised at all."""
        storage = storages["a_battery_1"].model_copy(deep=True)
        storage.maximum_energy = Timeseries.from_values(
            steps_parameters.temporal.start_date,
            steps_parameters.temporal.timestep,
            [0.0] * len(local_timewindow),
        )

        assert optimize_single_storage(storage, steps_parameters, local_timewindow) is None
