"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Unit tests for compute_efficiency_adjusted_prices (storage formulator).
"""

import pendulum
import pytest

from atlas.enums import StorageType
from atlas.modules.intraday_orders.input_objects.storage import StorageIDO
from atlas.modules.intraday_orders.orders_formulation.storage import compute_efficiency_adjusted_prices
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.objects.market_operator.portfolio import Portfolio
from atlas.timing import generate_datetimes

from .conftest import EXEC_DATE, const_ts, make_control_block, make_fm, make_market_area, make_node

START = pendulum.datetime(2028, 1, 1, 0, 0, 0)
END = pendulum.datetime(2028, 1, 1, 3, 0, 0)
STEP = pendulum.duration(hours=1)

T0 = START
T1 = START.add(hours=1)


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


def _run(da: dict, plan: dict, prices: dict, discharge_eff: float = 0.9, charge_eff: float = 0.9):
    params = _params()

    da_ts = _ts(0.0)
    for t, v in da.items():
        da_ts.set_value(t, v)
    plan_ts = _ts(0.0)
    for t, v in plan.items():
        plan_ts.set_value(t, v)
    price_ts = _ts(0.0)
    for t, v in prices.items():
        price_ts.set_value(t, v)

    market_area = make_market_area(id_price_forecast=make_fm(price_ts))
    portfolio = Portfolio(name="ptf", control_block=make_control_block(), market_area=market_area)

    storage = StorageIDO(
        name="battery",
        storage_type=StorageType.BATTERY,
        node=make_node(),
        portfolio=portfolio,
        da_cleared_quantity=da_ts,
        id_po_for_orders=make_fm(plan_ts),
        minimum_power=_ts(0.0),
        maximum_power=_ts(100.0),
        discharge_efficiency=discharge_eff,
        charge_efficiency=charge_eff,
        variable_cost=_ts(0.0),
    )
    timestamps = generate_datetimes(START, params.penultimate_date, STEP)
    return compute_efficiency_adjusted_prices(storage, timestamps, params)


class TestComputeEfficiencyAdjustedPrices:
    def test_only_sell_periods(self):
        # new_plan > DA everywhere → only sell timestamps → buy_price = 0
        sell_price, buy_price = _run(
            da={T0: 0.0, T1: 0.0},
            plan={T0: 50.0, T1: 50.0},
            prices={T0: 80.0, T1: 80.0},
        )
        assert sell_price == 80.0
        assert buy_price == 0.0

    def test_only_buy_periods(self):
        # DA > new_plan everywhere → only buy timestamps → sell_price = 0
        sell_price, buy_price = _run(
            da={T0: 50.0, T1: 50.0},
            plan={T0: 0.0, T1: 0.0},
            prices={T0: 40.0, T1: 40.0},
        )
        assert sell_price == 0.0
        assert buy_price == 40.0

    def test_negative_min_sell_price_forces_zero_sell(self):
        sell_price, buy_price = _run(
            da={T0: 0.0, T1: 50.0},
            plan={T0: 50.0, T1: 0.0},
            prices={T0: -10.0, T1: 40.0},
        )
        assert sell_price == 0.0
        assert buy_price == 40.0

    def test_both_prices_zero_returns_zero(self):
        # Safeguard against division by zero in the efficiency formula
        sell_price, buy_price = _run(
            da={T0: 0.0, T1: 50.0},
            plan={T0: 50.0, T1: 0.0},
            prices={T0: 0.0, T1: 0.0},
        )
        assert sell_price == 0.0
        assert buy_price == 0.0

    def test_efficiency_adjustment_reaches_breakeven(self):
        # The formula moves sell_price DOWN and buy_price UP symmetrically so that
        # sell × η_discharge × η_charge = buy exactly (break-even point).
        sell_price, buy_price = _run(
            da={T0: 0.0, T1: 50.0},
            plan={T0: 50.0, T1: 0.0},
            prices={T0: 100.0, T1: 50.0},
            discharge_eff=0.9,
            charge_eff=0.9,
        )
        # Both prices are shifted from their raw values
        assert sell_price < 100.0  # sell price moved toward break-even (down)
        assert buy_price > 50.0  # buy price moved toward break-even (up)
        # Break-even invariant: sell × η_d × η_c == buy
        assert sell_price * 0.9 * 0.9 == pytest.approx(buy_price, rel=1e-6)

    def test_no_id_price_forecast_returns_inf_sell_zero_buy(self):
        params = _params()
        market_area = make_market_area(id_price_forecast=None)
        portfolio = Portfolio(name="ptf", control_block=make_control_block(), market_area=market_area)
        storage = StorageIDO(
            name="battery",
            storage_type=StorageType.BATTERY,
            node=make_node(),
            portfolio=portfolio,
            da_cleared_quantity=_ts(0.0),
            id_po_for_orders=make_fm(_ts(0.0)),
            minimum_power=_ts(0.0),
            maximum_power=_ts(100.0),
            discharge_efficiency=0.9,
            charge_efficiency=0.9,
            variable_cost=_ts(0.0),
        )
        timestamps = generate_datetimes(START, params.penultimate_date, STEP)
        sell_price, buy_price = compute_efficiency_adjusted_prices(storage, timestamps, params)
        assert sell_price == float("inf")
        assert buy_price == 0.0
