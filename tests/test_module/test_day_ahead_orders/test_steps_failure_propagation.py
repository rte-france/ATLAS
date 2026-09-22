"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

A unit that fails must not be dropped from the step result: the step has no way to tell the
caller that its orders are incomplete, so the failure is propagated instead.
"""

from unittest.mock import Mock, patch

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


def test_storage_step_propagates_unit_failure():
    step = _step(StorageStep, "storage", "a_battery")

    with patch(
        "atlas.modules.day_ahead_orders.steps.storage.storage_step.optimize_single_storage",
        side_effect=RuntimeError("solver crashed"),
    ):
        with pytest.raises(RuntimeError, match="solver crashed"):
            step._formulate_sequential(local_timewindow=[])


def test_thermal_step_propagates_unit_failure():
    step = _step(ThermalBiddingStep, "thermal", "a_thermal")

    with patch(
        "atlas.modules.day_ahead_orders.steps.thermal.thermal_bidding_step.optimize_single_thermal_unit",
        side_effect=RuntimeError("solver crashed"),
    ):
        with pytest.raises(RuntimeError, match="solver crashed"):
            step._formulate_sequential()


def test_thermal_worker_rejects_unknown_strategy():
    thermal = Mock()
    thermal.name = "a_thermal"
    thermal.strategy = None

    with pytest.raises(ValueError, match="Unknown thermal strategy"):
        optimize_single_thermal_unit(thermal, orders_time=[], parameters=Mock())
