"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

A unit that fails must not be dropped from the step result: the step has no way to tell the
caller that its orders are incomplete, so the failure is propagated instead.
"""

from concurrent.futures import Future
from unittest.mock import MagicMock, Mock, patch

import pytest

from atlas.modules.day_ahead_orders.steps.storage.storage_step import StorageStep
from atlas.modules.day_ahead_orders.steps.thermal.thermal_bidding_step import ThermalBiddingStep
from atlas.modules.day_ahead_orders.steps.thermal.thermal_worker import optimize_single_thermal_unit


def _step(step_class, dataset_attribute: str, unit_name: str):
    dataset = Mock()
    unit = Mock()
    unit.name = unit_name
    setattr(dataset, dataset_attribute, [unit])
    return step_class(dataset, orders_time=[], parameters=Mock())


def _crashed_executor(executor_class: MagicMock) -> None:
    """Make every unit submitted to a patched ProcessPoolExecutor come back crashed."""

    def submit(*args, **kwargs) -> Future:
        future: Future = Future()
        future.set_exception(RuntimeError("solver crashed"))
        return future

    executor_class.return_value.__enter__.return_value.submit.side_effect = submit


def test_storage_step_propagates_unit_failure():
    step = _step(StorageStep, "storage", "a_battery")

    with patch(
        "atlas.modules.day_ahead_orders.steps.storage.storage_step.optimize_single_storage",
        side_effect=RuntimeError("solver crashed"),
    ):
        with pytest.raises(RuntimeError, match="a_battery") as error:
            step._formulate_sequential(local_timewindow=[])

    assert str(error.value.__cause__) == "solver crashed"


def test_storage_step_parallel_names_the_failing_unit():
    step = _step(StorageStep, "storage", "a_battery")

    with patch("atlas.modules.day_ahead_orders.steps.storage.storage_step.ProcessPoolExecutor") as executor_class:
        _crashed_executor(executor_class)

        with pytest.raises(RuntimeError, match="a_battery") as error:
            step._formulate_parallel(local_timewindow=[])

    assert str(error.value.__cause__) == "solver crashed"


def test_thermal_step_propagates_unit_failure():
    step = _step(ThermalBiddingStep, "thermal", "a_thermal")

    with patch(
        "atlas.modules.day_ahead_orders.steps.thermal.thermal_bidding_step.optimize_single_thermal_unit",
        side_effect=RuntimeError("solver crashed"),
    ):
        with pytest.raises(RuntimeError, match="a_thermal") as error:
            step._formulate_sequential()

    assert str(error.value.__cause__) == "solver crashed"


def test_thermal_step_parallel_names_the_failing_unit():
    step = _step(ThermalBiddingStep, "thermal", "a_thermal")

    with patch(
        "atlas.modules.day_ahead_orders.steps.thermal.thermal_bidding_step.ProcessPoolExecutor"
    ) as executor_class:
        _crashed_executor(executor_class)

        with pytest.raises(RuntimeError, match="a_thermal") as error:
            step._formulate_parallel()

    assert str(error.value.__cause__) == "solver crashed"


def test_thermal_worker_rejects_unknown_strategy():
    thermal = Mock()
    thermal.name = "a_thermal"
    thermal.strategy = None

    with pytest.raises(ValueError, match="Unknown thermal strategy"):
        optimize_single_thermal_unit(thermal, orders_time=[], parameters=Mock())
