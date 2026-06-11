"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import Field, field_validator

from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.enums import Enum, Product
from atlas.io_utils.parameters import SolverParameters


class ExchangeConstraintsType(str, Enum):
    """
    Represents different types of exchange constraints.

    :cvar ATC: Available Transmission Capacity
    :cvar FB: Flow-Based
    """

    ATC = "ATC"
    FB = "FB"


class MarketClearingParameters(AbstractModuleParameters):
    """Parameters of for Market Clearing module

    :param price_modifier_lambda_1: Price modifier that allows to alter prices for a better optimization :
    default value is 0
    :type price_modifier_lambda_1: float
    :param flow_penalty_lambda_2: Coefficient penalizing the exchanges through borders in the clearing cost function :
    default value is 0
    :type flow_penalty_lambda_2: float
    :param flow_penalty_lambda_3: Coefficient penalizing the non-maximal exchanges through borders in the clearing cost
    function : default value is 0
    :type flow_penalty_lambda_3: float
    :param flow_penalty_lambda_4: Coefficient penalizing the non-minimal exchanges through borders in the clearing cost
    function : default value is 0
    :type flow_penalty_lambda_4: float
    :param activate_constrained_tso_quantity: Used in Balancing only. Boolean to indicate whether the Clearing should
    implement constraint 3.5 on TSO sold/bought quantities (can be accepted only if enough power has been offered as in
    the other way by other players than TSO on the Control Block) : default value is False"
    :type activate_constrained_tso_quantity: bool
    :param prevent_adverse_flows: Boolean to indicate whether the pricing should prevent adverse flows.
    It may be possible to leave out these constraints in some FB cases : default value is False
    :type prevent_adverse_flows: bool
    :param allowed_round_off_error: Threshold, in MW, below which the value of accepted power is considered equal to 0.
    Typical values: 0.001, 0.0001 or 0.00001 : default value is 0.001
    :type allowed_round_off_error: float
    :param fb_branch_load_slack_penalty: Penalty coefficient favoring the minimization of slacks on flow-based branch
    load constraints during the pricing phase : default value is 200
    :type fb_branch_load_slack_penalty: float
    :param market_price_penalty_alpha: Penalty coefficient favoring the minimization of individual market prices during
    the pricing phase : default value is 10
    :type market_price_penalty_alpha: float
    :param market_price_penalty_beta: Penalty coefficient favoring the minimization of individual market prices in
    absolute values during the pricing phase : default value is 20
    :type market_price_penalty_beta: float
    :param paradoxically_accepted_penalty_M: Very big penalty coefficient used to minimize first the paradoxical values
    during the fixing of market prices : default value is 10000
    :type paradoxically_accepted_penalty_M: float
    :param paradoxically_rejected_penalty_N: Very big penalty coefficient used to minimize paradoxically rejected bids
    during the fixing of market prices : default value is 1000
    :type paradoxically_rejected_penalty_N: float
    :param execution_datetime_tolerance: Time (in minutes) associated with the execution date tolerance band.
    Required to simulated overlapping markets (Intraday, or Balancing). Needs to be greater than the difference between
    execution dates of consecutive order formulation module and Clearing, but less than between the order formulation
    of the previous market and the current Clearing : must be superior to 0, default value is 5
    :type execution_datetime_tolerance: int
    :param control_block_names: Custom selection of control blocks to be included in the computation or string 'All' to
    select all control block. the default value is 'All'
    :type control_block_names: str | list[str]
    :param exchange_constraints_type: Type of constraints to apply on exchanges between market areas: ATC or
    FB (Flow-based): Default value is 'ATC'
    :type exchange_constraints_type: ExchangeConstraintsType
    :param exchange_constraints_type: Name of the market to be considered. Only orders matching the entered market name
    will be considered : Default value is 'DayAhead'
    :type exchange_constraints_type: Product
    :param market_area_names: Custom selection of market areas to be included in the computation or string 'All' to
    select all market area. the default value is 'All'
    :type market_area_names: str | list[str]
    """

    solver: SolverParameters = SolverParameters()  # type: ignore[call-arg, arg-type]

    price_modifier_lambda_1: float = Field(
        0, description="Price modifier that allows to alter prices for a better optimization : default value is 0"
    )
    flow_penalty_lambda_2: float = Field(
        0,
        description="Coefficient penalizing the exchanges through borders in the clearing cost function : "
        "default value is 0",
    )
    flow_penalty_lambda_3: float = Field(
        0,
        description="Coefficient penalizing the non-maximal exchanges through borders in the clearing cost function : "
        "default value is 0",
    )
    flow_penalty_lambda_4: float = Field(
        0,
        description="Coefficient penalizing the non-minimal exchanges through borders in the clearing cost function : "
        "default value is 0",
    )
    activate_constrained_tso_quantity: bool = Field(
        False,
        description="Used in Balancing only. Boolean to indicate whether the Clearing should implement constraint 3.5 "
        "on TSO sold/bought quantities (can be accepted only if enough power has been offered as in the "
        "other way by other players than TSO on the Control Block) : default value is False",
    )
    prevent_adverse_flows: bool = Field(
        False,
        description="Boolean to indicate whether the pricing should prevent adverse flows. It may be possible to leave "
        "out these constraints in some FB cases : default value is False",
    )
    allowed_round_off_error: float = Field(
        0.001,
        description="Threshold, in MW, below which the value of accepted power is considered equal to 0. "
        "Typical values: 0.001, 0.0001 or 0.00001 : default value is 0.001",
    )
    fb_branch_load_slack_penalty: float = Field(
        1,
        description="Penalty coefficient favoring the minimization of slacks on flow-based branch load constraints "
        "during the pricing phase : default value is 200",
    )
    market_price_penalty_alpha: float = Field(
        10,
        description="Penalty coefficient favoring the minimization of individual market prices during "
        "the pricing phase : default value is 10",
    )
    market_price_penalty_beta: float = Field(
        20,
        description="Penalty coefficient favoring the minimization of individual market prices in absolute values "
        "during the pricing phase : default value is 20",
    )
    paradoxically_accepted_penalty_M: float = Field(
        10000,
        description="Very big penalty coefficient used to minimize first the paradoxical values during the fixing of "
        "market prices : default value is 10000",
    )
    paradoxically_rejected_penalty_N: float = Field(
        1000,
        description="Very big penalty coefficient used to minimize paradoxically rejected bids during the fixing of "
        "market prices : default value is 1000",
    )
    execution_datetime_tolerance: int = Field(
        5,
        ge=1,
        description="Time (in minutes) associated with the execution date tolerance band. Required to simulated "
        "overlapping markets (Intraday, or Balancing). Needs to be greater than the difference between "
        "execution dates of consecutive order formulation module and Clearing, but less than between "
        "the order formulation of the previous market and the current Clearing : must be superior to 0, "
        "default value is 5",
    )
    control_block_names: str | list[str] = Field(
        "All",
        description="Custom selection of control blocks to be included in the computation or string 'All' to select "
        "all control block. the default value is 'All'",
    )
    exchange_constraints_type: ExchangeConstraintsType = Field(
        ExchangeConstraintsType.ATC,
        description="Type of constraints to apply on exchanges between market areas (not case sensitive) : ATC or "
        "FB (Flow-based) : Default value is 'ATC",
    )
    market: Product = Field(
        Product.DayAhead,
        description="Name of the market to be considered. Only orders matching the entered market name will be "
        "considered (not case sensitive) : Default value is 'DayAhead'",
    )
    market_area_names: str | list[str] = Field(
        "All",
        description="Custom selection of market areas to be included in the computation or string 'All' to select all "
        "market area. the default value is 'All'",
    )
    initial_max_price: int = Field(
        int(1e8),
        description=" Max price : default value is 100 000 000",
    )
    initial_min_price: int = Field(
        -int(1e8),
        description="Min price : default value is - 100 000 000",
    )

    @field_validator("market_area_names", "control_block_names", mode="before")
    @classmethod
    def parse_included_objects(cls, v):
        # case default
        if isinstance(v, str) and v.lower() == "all":
            return v.lower()

        # already a list
        if isinstance(v, list):
            return v

        # string like "[es, fr]"
        if isinstance(v, str):
            v = v.strip()

            if not (v.startswith("[") and v.endswith("]")):
                raise ValueError("market_area_names must be 'All' or a list like [es, fr]")

            content = v[1:-1].strip()
            if not content:
                return []

            return [item.strip() for item in content.split(",")]

        raise ValueError("Invalid value for market_area_names")
