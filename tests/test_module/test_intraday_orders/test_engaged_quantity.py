"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Unit tests for engaged_quantity (utils).

engaged_quantity is the foundation of every formulator: it computes the cumulative
cleared engagement (DA + all prior ID sessions) that all order volumes are computed
relative to.
"""

import pendulum
import pytest

from atlas.enums import ThermalStrategy
from atlas.modules.intraday_orders.input_objects.thermal import ThermalIDO
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.modules.intraday_orders.utils import engaged_quantity

from .conftest import EXEC_DATE, const_ts, make_fm, make_node, make_portfolio

START = pendulum.datetime(2028, 1, 1, 0, 0, 0)
END = pendulum.datetime(2028, 1, 1, 3, 0, 0)
STEP = pendulum.duration(hours=1)

T0 = START
T1 = START.add(hours=1)
T2 = START.add(hours=2)  # penultimate


def _params() -> IntradayOrdersParameters:
    return IntradayOrdersParameters.model_validate(
        {
            "temporal": {
                "start_date": str(START),
                "execution_date": str(EXEC_DATE),
                "end_date": str(END),
                "timestep": "PT1H",
            }
        }
    )


def _ts(value: float):
    return const_ts(value, START, STEP, END)


def _make_thermal(**overrides) -> ThermalIDO:
    defaults = dict(
        name="unit",
        strategy=ThermalStrategy.BASE,
        node=make_node(),
        portfolio=make_portfolio(),
        da_cleared_quantity=_ts(50.0),
        id_po_for_orders=make_fm(_ts(50.0)),
        minimum_power=_ts(30.0),
        maximum_power=_ts(100.0),
        startup_cost=_ts(0.0),
        variable_cost=_ts(10.0),
    )
    defaults.update(overrides)
    return ThermalIDO(**defaults)


class TestEngagedQuantity:
    def test_only_da_when_no_id_clearing(self):
        # total_id_cleared_quantity is None → engagement = DA only
        params = _params()
        thermal = _make_thermal(da_cleared_quantity=_ts(60.0), total_id_cleared_quantity=None)
        result = engaged_quantity(thermal, params)
        assert result.get_value(T0) == pytest.approx(60.0)
        assert result.get_value(T1) == pytest.approx(60.0)

    def test_da_plus_id_when_id_clearing_exists(self):
        # total_id_cleared_quantity is set → engagement = DA + ID
        params = _params()
        thermal = _make_thermal(da_cleared_quantity=_ts(60.0), total_id_cleared_quantity=_ts(10.0))
        result = engaged_quantity(thermal, params)
        assert result.get_value(T0) == pytest.approx(70.0)
        assert result.get_value(T1) == pytest.approx(70.0)

    def test_zero_filled_when_da_outside_order_window(self):
        # DA timeseries with no overlap with [START, penultimate] → zeros
        params = _params()
        far_past = const_ts(999.0, START.subtract(days=10), STEP, START.subtract(days=9))
        thermal = _make_thermal(da_cleared_quantity=far_past)
        result = engaged_quantity(thermal, params)
        assert result.get_value(T0) == pytest.approx(0.0)
        assert result.get_value(T1) == pytest.approx(0.0)
