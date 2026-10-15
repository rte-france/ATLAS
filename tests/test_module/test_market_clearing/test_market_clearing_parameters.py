"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pytest
from pendulum import DateTime, Duration
from pydantic import ValidationError

from atlas.enums import Product, SolverEnum
from atlas.io_utils.parameters import DateParameters, SolverParameters
from atlas.modules.market_clearing.parameters import (
    ExchangeConstraintsType,
    MarketClearingParameters,
)


def make_date(**kwargs):
    return DateParameters(
        start_date=DateTime.now(),
        end_date=DateTime.now(),
        execution_date=DateTime.now(),
        **kwargs,
    )


def test_default_parameters():
    params = MarketClearingParameters(temporal=make_date())
    assert params.temporal.timestep == Duration(hours=1)
    assert params.solver.solver_name == SolverEnum.XPRESS
    assert params.allowed_round_off_error == 0.001
    assert params.exchange_constraints_type == ExchangeConstraintsType.ATC
    assert params.market == Product.DayAhead
    assert params.market_area_names == "all"
    assert params.initial_max_price == 1e8
    assert params.initial_min_price == -1e8
    assert not params.prevent_adverse_flows
    assert not params.activate_constrained_tso_quantity
    assert params.initial_max_price == 1e8
    assert params.initial_min_price == -1e8


def test_custom_parameters():
    params = MarketClearingParameters(
        temporal=make_date(timestep=Duration(minutes=15)),
        solver=SolverParameters(solver_name=SolverEnum.XPRESS, use_presolve=False),
        market_area_names="[MA]",
        price_modifier_lambda_1=0.05,
        exchange_constraints_type=ExchangeConstraintsType.FB,
        market=Product.Intraday,
        paradoxically_rejected_penalty=2000,
    )
    assert params.temporal.timestep == Duration(minutes=15)
    assert params.price_modifier_lambda_1 == 0.05
    assert params.market_area_names == ["MA"]
    assert params.exchange_constraints_type == ExchangeConstraintsType.FB
    assert params.market == Product.Intraday
    assert not params.solver.use_presolve
    assert params.paradoxically_rejected_penalty == 2000


def test_invalid_enum_for_exchange_constraints_type_raises():
    with pytest.raises(ValidationError):
        MarketClearingParameters(exchange_constraints_type="INVALID")


def test_list_or_str_market_areas():
    params = MarketClearingParameters(temporal=make_date(), market_area_names="All")
    assert isinstance(params.market_area_names, str)

    params = MarketClearingParameters(temporal=make_date(), market_area_names=["MA1", "MA2"])
    assert isinstance(params.market_area_names, list)
    assert "MA1" in params.market_area_names
