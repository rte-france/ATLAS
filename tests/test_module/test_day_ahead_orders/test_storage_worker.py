"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from types import SimpleNamespace

import pendulum
import pytest

from atlas.io_utils.parameters import DateParameters
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.steps.storage.storage_worker import _initiate_stock

START = pendulum.datetime(2028, 9, 27)


@pytest.fixture
def parameters():
    temporal = DateParameters(
        start_date=START,
        end_date=START.add(days=1),
        execution_date=START.subtract(hours=12),
        timestep=pendulum.duration(hours=1),
    )
    return SimpleNamespace(temporal=temporal)


def _hourly(values: list[float]) -> Timeseries:
    return Timeseries.from_values(START.subtract(hours=2), frequency="1h", values=values)


def test_initial_stock_is_read_at_the_previous_timestep(parameters):
    # index: start - 2h, start - 1h, start
    storage = SimpleNamespace(
        storage_initial_level=_hourly([0.1, 0.5, 0.9]),
        maximum_energy=_hourly([10.0, 100.0, 1000.0]),
        stored_energy=None,
    )

    assert _initiate_stock(storage, parameters) == pytest.approx(0.5 * 100.0)
