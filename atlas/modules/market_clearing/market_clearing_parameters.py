"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import Field

from atlas.abstract_class.abstract_parameters import AbstractParameters


class MarketClearingParameters(AbstractParameters):
    """Parameters of for Market Clearing module"""

    time_step: int = Field(
        default=60,
        ge=1,
        description="Timestep of the studied market, in minutes : must be superior to 0, default value is 60",
    )
    price_modifier_lambda_1: float = Field(
        0, description="Price modifier that allows to alter prices for a better optimization : default value is 0"
    )
    flow_penalty_lambda_2: float = Field(
        0,
        description="Coefficient penalizing the exchanges through borders in the clearing cost function : default value "
        "is 0",
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
    use_presolve: bool = Field(
        True,
        description="Boolean indicating if a presolve step is desired or not before solving the clearing phase : "
        "default value is False",
    )
    allowed_round_off_error: float = Field(
        0.001,
        description="Threshold, in MW, below which the value of accepted power is considered equal to 0. "
        "Typical values: 0.001, 0.0001 or 0.00001 : default value is 0.001",
    )
    fb_branch_load_slack_penalty: float = Field(
        200,
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

    # TODO
    # ControlBlockNames
    # ExchangeConstraintsType
    # Market
    # MarketAreaNames
