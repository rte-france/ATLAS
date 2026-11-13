"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pathlib import Path

from pydantic import Field

from atlas.abstract_class.parameters import AbstractModuleParameters


class TSOOrdersParameters(AbstractModuleParameters):
    start_date: str = Field(
        "2028/09/02 00:00:00",
        description="Task start date parameter.",
    )

    end_date: str = Field(
        "2028/09/02 01:00:00",
        description="Task end date parameter.",
    )

    execution_date: str = Field(
        "2028/09/01 23:30:00",
        description="Task execution date parameter.",
    )

    market_price_cap: int = Field(
        15000,
        description="Price cap of the market (€/MW).",
    )

    time_step: int = Field(
        15,
        description="Time step of the process (minutes).",
    )

    market: str = Field(
        "RRActivation",
        description="Type of market (MFRRActivation or RRActivation).",
    )

    debug: bool = Field(
        False,
        description="Generate debug information.",
    )

    verbose: bool = Field(
        True,
        description="Print detailed information during execution.",
    )

    pricing_slices_size: float = Field(
        200.0,
        description="Size (MW) of pricing slices used during pricing computation.",
    )

    use_presolve: bool = Field(
        True,
        description="Whether a presolve step is applied before clearing optimization.",
    )

    solver: str = Field(
        "XPRESS",
        description="Optimization solver.",
    )

    voll: int = Field(
        26000,
        description="Value of Lost Load (€/MWh).",
    )

    tso_forecast_error_quantiles: Path | None = Field(
        None,
        description="CSV containing forecast error quantiles for volume uncertainty pricing.",
    )

    mfrr_alternative_prices_spread: Path | None = Field(
        None,
        description="CSV containing price spreads for the mFRR alternative pricing strategy.",
    )

    day_ahead_execution_hour: int = Field(
        12,
        description="Hour at which the Day-Ahead Market is run.",
    )

    default_pricing_type: str = Field(
        "AtAllCosts",
        description='Default pricing type ("AtAllCosts", "FrBM", or "mFRR").',
    )

    frbm_available_quantity_percentage: float = Field(
        1.0,
        description="Percentage of BSP available power assumed available on the Balancing Mechanism.",
    )

    frbm_pricing_available_units: str = Field(
        "All",
        description='Units assumed always available for Balancing Mechanism simulations. Use ";" as separator or "All".',
    )

    frbm_pricing_available_technologies: str = Field(
        "All",
        description='Technologies assumed available for Balancing Mechanism simulations. Use ";" as separator or "All".',
    )

    frbm_redispatch_penalty: int = Field(
        5000,
        description="Penalty (€/MWh) applied to avoid economic redispatch.",
    )

    use_res_forecasts: bool = Field(
        True,
        description="Use latest RES forecasts instead of latest measured output.",
    )

    apply_tso_volume_limit: bool = Field(
        True,
        description="Limit TSO demand by total BSP offer volume.",
    )

    lp_output_folder: str = Field(
        "TSO_orders",
        description="Output folder for LP files in debug mode.",
    )

    solver_timeout: int = Field(
        240,
        description="Optimization timeout (seconds).",
    )

    solver_duality_gap: float = Field(
        0.001,
        description="Duality gap used for FrBM optimizations.",
    )

    allowed_round_off_error: float = Field(
        0.01,
        description="Activated power below this threshold (MW) is considered zero.",
    )

    frbm_ev_allowed: bool = Field(
        False,
        description="Whether Electric Vehicles are allowed in the Balancing Mechanism.",
    )

    frbm_spillage_penalty: int = Field(
        100,
        description="Penalty applied to unwanted generation spillage.",
    )

    included_control_blocks: str = Field(
        "All",
        description='List of control blocks separated by ";" ("All" or "None" allowed).',
    )
