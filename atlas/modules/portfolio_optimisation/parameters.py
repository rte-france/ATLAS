from __future__ import annotations

from enum import Enum

from pydantic import Field

from atlas.abstract_class.abstract_parameters import AbstractParameters


class MarketEnum(str, Enum):
    dayahead = "DayAhead"
    intraday = "Intraday"
    rr_activation = "RRActivation"
    mfrr_activation = "MFRRActivation"


class SolverEnum(str, Enum):
    xpress = "XPRESS"
    pne = "PNE"
    glop = "GLOP"
    scip = "SCIP"
    cpsat = "CP-SAT"


class PortfolioOptimisationParameters(AbstractParameters):
    """Pydantic model for module parameters with documentation and defaults."""

    start_date: str = Field(
        "2028/07/01 01:00:00",
        description="Beginning of the timeframe studied by the module. In action plan context, value is set by task settings.",
    )
    execution_date: str = Field(
        "2028/06/30 13:00:00",
        description="Date from which the module is executed. In action plan context, value is set by task settings.",
    )
    end_date: str = Field(
        "2028/07/01 03:00:00",
        description="End of the timeframe studied by the module (end of the last time step). In action plan context, value is set by task settings.",
    )
    debug: bool = Field(False, description="Boolean indicating if the PO is in debug mode.")
    is_portfolio_bidding: bool = Field(
        True, description="True if optimization is on portfolios, False for individual units."
    )
    use_forecast: bool = Field(
        False,
        description="Whether to take a price forecast. If true, optimization happens before a market.",
    )
    use_presolve: bool = Field(False, description="Boolean indicating if the solver should use a presolve mode.")
    verbose: bool = Field(
        True,
        description="If True, information of the module execution will be displayed in the terminal.",
    )
    with_rounding: bool = Field(
        True, description="If true, optimization outputs are rounded at the end to avoid artefacts."
    )
    allowed_round_off_error: float = Field(
        0.01, description="Error (in MW) below which the activated power is considered equal to 0."
    )
    automated_unprocured_reserves_penalty: float = Field(
        30000, description="Penalty (euro/MW per hour) for not providing automated reserves."
    )
    battery_smoothing_factor: float = Field(
        0.2, description="Smoothing factor for battery power offer/demand curve (0-1)."
    )
    electric_vehicle_smoothing_factor: float = Field(
        0.2, description="Smoothing factor for EV power offer/demand curve (0-1)."
    )
    imbalance_penalty_offset: float = Field(
        10,
        description="Offset (euros/MWh) applied when forecasting the imbalance settlement price.",
    )
    isp_forecast_lower_bound: float = Field(
        10,
        description="Lower bound (euro/MWh) of the absolute value of the Imbalance Settlement Price forecast.",
    )
    large_imbalance_penalty: float = Field(
        0.2,
        description="Coefficient for estimating imbalance settlement price for large imbalances.",
    )
    maximum_imbalance: float = Field(100000, description="Maximum imbalance allowed within a portfolio, in MW.")
    manual_unprocured_reserves_penalty: float = Field(
        30000, description="Penalty (euro/MW per hour) for not providing manual reserves."
    )
    pumped_hydraulic_smoothing_factor: float = Field(
        0.2, description="Smoothing factor for pumped hydraulic power offer/demand curve (0-1)."
    )
    small_imbalance_penalty: float = Field(
        0.1,
        description="Coefficient for estimating imbalance settlement price for small imbalances.",
    )
    small_imbalance_size: float = Field(
        0.15,
        description="Quantity (%) of imbalance qualified as small, relative to max portfolio energy.",
    )
    solver_duality_gap: float = Field(0.0001, description="Duality gap used for the optimization.")
    additional_hours: int = Field(
        12,
        description="Default optimization period in hours for PV, Wind, and Load. Overwritten by specific equipment.",
    )
    battery_additional_hours: int = Field(
        48, description="Optimization period in hours for Storage Equipments of type Battery."
    )
    battery_automated_reserve_duration: int = Field(60, description="Automated reserve duration for battery equipment.")
    battery_number_of_fragments: int = Field(
        3, description="Number of power fragments for battery; last fragments are more expensive."
    )
    battery_reserve_duration: int = Field(60, description="Manual reserve duration for battery equipment.")
    electric_vehicle_additional_hours: int = Field(
        144,
        description="Optimization period in hours for Storage Equipments of type ElectricVehicle.",
    )
    electric_vehicle_automated_reserve_duration: int = Field(
        1, description="Automated reserve duration for electric vehicle equipment."
    )
    electric_vehicle_number_of_fragments: int = Field(3, description="Number of power fragments for electric vehicle.")
    electric_vehicle_reserve_duration: int = Field(
        0, description="Manual reserve duration for electric vehicle equipment."
    )
    hydraulic_additional_hours: int = Field(12, description="Optimization period in hours for hydraulic group.")
    hydraulic_minimal_fragment_size: int = Field(
        100, description="Minimal amount of power for an offer to be formulated for hydraulic."
    )
    pumped_hydraulic_automated_reserve_duration: int = Field(
        60, description="Automated reserve duration for pumped hydraulic equipment."
    )
    pumped_hydraulic_number_of_fragments: int = Field(3, description="Number of power fragments for pumped hydraulic.")
    pumped_hydraulic_reserve_duration: int = Field(
        60, description="Manual reserve duration for pumped hydraulic equipment."
    )
    pumped_hydraulic_storage_additional_hours: int = Field(
        144,
        description="Optimization period in hours for Storage Equipments of type PumpedHydraulicStorage.",
    )
    solver_timeout: int = Field(240, description="Timeout (in seconds) of the optimization.")
    thermal_additional_hours: int = Field(12, description="Optimization period in hours for thermal group.")
    time_step: int = Field(60, description="Time step (in minutes) of the simulated market.")
    excluded_market_areas: str | None = Field(
        None,
        description='List of market areas (separated by ";") excluded from classic optimization. None and "All" are possible values.',
    )
    excluded_technologies: str | None = Field(
        None,
        description='List of equipment types (separated by ";") excluded from classic optimization. None and "All" are possible values.',
    )
    excluded_thermal_strategies: str | None = Field(
        None,
        description='List of thermal strategies (separated by ";") for which manual activation is always used. "Peak", "Intermediate", "Base", "All", None.',
    )
    market: MarketEnum = Field(
        MarketEnum.dayahead,
        description='Market during which the Portfolio Optimization is run. Possible values: "DayAhead", "Intraday", "RRActivation", "MFRRActivation".',
    )
    output_folder: str = Field(
        "PO",
        description='Optional output folder in the SAMBA folder for LP exports. If None, a folder "PO_{Market}_{ExecutionDate}" is created.',
    )
    solver: SolverEnum = Field(
        SolverEnum.xpress,
        description='Solver to use. Default: "XPRESS". Other options: "PNE", "GLOP", "SCIP", "CP-SAT".',
    )
