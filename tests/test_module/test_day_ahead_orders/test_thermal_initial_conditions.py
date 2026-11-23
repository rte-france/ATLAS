"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Regression tests on the initial conditions of the thermal DayAheadOrders optimisation, when they are
rebuilt from a power trajectory computed by an upstream module (typically PortfolioOptimisation).
"""

from pathlib import Path

import pytest

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.module import DayAheadOrdersModule

DAY_AHEAD_INPUT_DIR = Path("tests/dataset/day_ahead/day_ahead_input")
UNIT_NAME = "a_thermal_intermediate_1"  # qmin = 200 MW, startup_duration = 2h, minimum_time_on = 2h

# Power trajectory of the previous day (2028-09-27), ending with a 2h startup ramp (100 MW, then qmin = 200 MW).
CLEAN_TRAJECTORY = [0.0] * 21 + [0.0, 100.0, 200.0]
# Same trajectory, as returned by a solver: residual noise around 0 and right below qmin.
NOISY_TRAJECTORY = [0.0] * 21 + [4.218847493575597e-14, 99.99999999999999, 199.99999999999997]

NEXT_DAY_PARAMETERS = {
    "temporal": {
        "start_date": "2028-09-28 00:00:00",
        "end_date": "2028-09-29 00:00:00",
        "execution_date": "2028-09-27 12:00:00",
        "timestep": "PT1H",
    },
    "solver": {"solver_name": "SCIP", "timeout": "PT30S"},
    "price_forecasts_types": ["Medium", "High", "Low"],
}


def _dataset_with_previous_power(values: list[float]) -> AtlasDataset:
    dataset = AtlasDataset.from_directory(DAY_AHEAD_INPUT_DIR).include_equipments([UNIT_NAME]).model_copy(deep=True)
    previous_power = Timeseries.from_values(
        start_date="2028-09-27 00:00:00", frequency="1h", values=values, timezone="UTC"
    )
    power = ForecastingMatrix()
    power.add(previous_power, "2028-09-26 12:00:00")
    dataset.thermal.get(UNIT_NAME).power = power
    return dataset


@pytest.mark.parametrize("trajectory", [CLEAN_TRAJECTORY, NOISY_TRAJECTORY], ids=["clean", "solver_noise"])
def test_next_day_orders_with_previous_startup_ramp(trajectory: list[float]) -> None:
    """A startup ramp ending the previous day must give a feasible problem, even with solver noise on the power."""
    assert len(trajectory) == 24
    dataset = _dataset_with_previous_power(trajectory)

    result = DayAheadOrdersModule().run(dataset, NEXT_DAY_PARAMETERS)

    assert result.change_sets, f"No order formulated for {UNIT_NAME}"
