import pytest
from pydantic import ValidationError

from atlas.enum import Product
from atlas.modules.market_clearing.market_clearing_parameters import MarketClearingParameters, ExchangeConstraintsType, \
    SolverEnum


def test_default_parameters():
    params = MarketClearingParameters()
    assert params.time_step == 60
    assert params.solver_name == SolverEnum.XPRESS
    assert params.allowed_round_off_error == 0.001
    assert params.exchange_constraints_type == ExchangeConstraintsType.ATC
    assert params.market == Product.DayAhead
    assert params.control_block_names == "All"
    assert params.market_area_names == "All"
    assert params.initial_max_price == 1e8
    assert params.initial_min_price == -1e8
    assert not params.prevent_adverse_flows
    assert not params.activate_constrained_tso_quantity
    assert params.initial_max_price == 1e8
    assert params.initial_min_price == -1e8


def test_custom_parameters():
    params = MarketClearingParameters(
        time_step=15,
        solver_name=SolverEnum.XPRESS,
        control_block_names=["CB1", "CB2"],
        market_area_names="MA",
        price_modifier_lambda_1=0.05,
        exchange_constraints_type=ExchangeConstraintsType.FB,
        market=Product.Intraday,
        use_presolve=False,
        paradoxically_rejected_penalty_N=2000,
    )
    assert params.time_step == 15
    assert params.price_modifier_lambda_1 == 0.05
    assert params.control_block_names == ["CB1", "CB2"]
    assert params.market_area_names == "MA"
    assert params.exchange_constraints_type == ExchangeConstraintsType.FB
    assert params.market == Product.Intraday
    assert not params.use_presolve
    assert params.paradoxically_rejected_penalty_N == 2000


def test_invalid_time_step_raises():
    with pytest.raises(ValidationError):
        MarketClearingParameters(time_step=0)


def test_invalid_enum_for_exchange_constraints_type_raises():
    with pytest.raises(ValidationError):
        MarketClearingParameters(exchange_constraints_type="INVALID")


def test_list_or_str_control_blocks():
    params = MarketClearingParameters(control_block_names="All")
    assert isinstance(params.control_block_names, str)

    params = MarketClearingParameters(control_block_names=["CB1", "CB2"])
    assert isinstance(params.control_block_names, list)
    assert "CB1" in params.control_block_names
