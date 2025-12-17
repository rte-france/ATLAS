"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pendulum import DateTime, duration
from pydantic import Field
from pydantic_extra_types.pendulum_dt import Duration

from atlas.abstract_class.abstract_parameters import AbstractParameters
from atlas.enum import MarketType, SolverEnum, StorageType, ThermalStrategy
from atlas.timing import generate_datetimes


class PortfolioOptimisationParameters(AbstractParameters):
    """Pydantic model for module parameters with documentation and defaults."""

    debug: bool = Field(False, description="Boolean indicating if the PO is in debug mode.")
    is_portfolio_bidding: bool = Field(
        True, description="True if optimization is on portfolios, False for individual units."
    )
    use_forecast: bool = Field(
        False,
        description="Whether to take a price forecast. If true, optimization happens before a market.",
    )
    use_presolve: bool = Field(False, description="Boolean indicating if the solver should use a presolve mode.")
    use_multiprocessing: bool = Field(
        True,
        description="If True, use multiprocessing for parallel portfolio optimization. If False, use sequential for loop.",
    )
    max_workers: int | None = Field(
        None,
        description="Maximum number of parallel processes for portfolio optimization. None defaults to CPU count. Only used if use_multiprocessing is True.",
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
    battery_automated_reserve_duration: Duration = Field(
        default_factory=lambda: duration(minutes=60),
        description="Automated reserve duration for battery equipment.",  # type: ignore[assignment]
    )
    battery_number_of_fragments: int = Field(
        3, description="Number of power fragments for battery; last fragments are more expensive."
    )
    battery_reserve_duration: Duration = Field(
        default_factory=lambda: duration(minutes=60),
        description="Manual reserve duration for battery equipment.",  # type: ignore[assignment]
    )
    electric_vehicle_automated_reserve_duration: Duration = Field(
        default_factory=lambda: duration(minutes=1),
        description="Automated reserve duration for electric vehicle equipment.",  # type: ignore[assignment]
    )
    electric_vehicle_number_of_fragments: int = Field(3, description="Number of power fragments for electric vehicle.")
    electric_vehicle_reserve_duration: Duration = Field(
        default_factory=lambda: duration(minutes=1),
        description="Manual reserve duration for electric vehicle equipment.",  # type: ignore[assignment]
    )
    hydraulic_minimal_fragment_size: int = Field(
        100, description="Minimal amount of power for an offer to be formulated for hydraulic."
    )
    pumped_hydraulic_automated_reserve_duration: Duration = Field(
        default_factory=lambda: duration(minutes=60),
        description="Automated reserve duration for pumped hydraulic equipment.",  # type: ignore[assignment]
    )
    pumped_hydraulic_number_of_fragments: int = Field(3, description="Number of power fragments for pumped hydraulic.")
    pumped_hydraulic_reserve_duration: Duration = Field(
        default_factory=lambda: duration(minutes=60),
        description="Manual reserve duration for pumped hydraulic equipment.",  # type: ignore[assignment]
    )
    solver_timeout: Duration = Field(
        default_factory=lambda: duration(seconds=60),
        description="Timeout (in seconds) of the optimization.",  # type: ignore[assignment]
    )
    excluded_market_areas_: str | None = Field(
        None,
        description='list of market areas (separated by ";") excluded from classic optimization. None and "all" are possible values.',
        alias="excluded_market_areas",
    )
    excluded_technologies_: str | None = Field(
        None,
        description='list of equipment types (separated by ";") excluded from classic optimization. None and "all" are possible values.',
        alias="excluded_technologies",
    )
    excluded_thermal_strategies_: str | None = Field(
        None,
        description='list of thermal strategies (separated by ";") for which manual activation is always used. "Peak", "Intermediate", "Base", "all", None.',
        alias="excluded_thermal_strategy",
    )
    market: MarketType = Field(
        MarketType.dayahead,
        description='Market during which the Portfolio Optimization is run. Possible values: "DayAhead", "Intraday", "RRActivation", "MFRRActivation".',
    )
    solver: SolverEnum = Field(
        SolverEnum.XPRESS,
        description='Solver to use. Default: "XPRESS". Other options: "PNE", "GLOP", "SCIP", "CP-SAT".',
    )

    additional_hours: Duration = Field(
        default_factory=lambda: duration(hours=12),
        description="Default optimization period in hours for PV, Wind, and Load. Overwritten by specific equipment.",  # type: ignore[assignment]
    )
    battery_additional_hours: Duration = Field(
        default_factory=lambda: duration(hours=48),
        description="Optimization period in hours for Storage Equipments of type Battery.",  # type: ignore[assignment]
    )
    electric_vehicle_additional_hours: Duration = Field(
        default_factory=lambda: duration(hours=24),
        description="Optimization period in hours for Storage Equipments of type ElectricVehicle.",  # type: ignore[assignment]
    )
    hydraulic_additional_hours: Duration = Field(
        default_factory=lambda: duration(hours=12),
        description="Optimization period in hours for hydraulic group.",  # type: ignore[assignment]
    )
    pumped_hydraulic_storage_additional_hours: Duration = Field(
        default_factory=lambda: duration(hours=144),
        description="Optimization period in hours for Storage Equipments of type PumpedHydraulicStorage.",  # type: ignore[assignment]
    )
    thermal_additional_hours: Duration = Field(
        default_factory=lambda: duration(hours=12),
        description="Optimization period in hours for thermal group.",  # type: ignore[assignment]
    )
    timestep: Duration = Field(
        default_factory=lambda: duration(hours=1),
        description="Time step of the simulated market.",  # type: ignore[assignment]
    )

    @property
    def excluded_market_areas(self) -> list[str]:
        """list of market areas excluded from optimization."""
        val = self.excluded_market_areas_
        if val is None or val.lower() == "none":
            return []
        if val.lower() == "all":
            return ["all"]
        return [area.strip() for area in val.split(";")]

    @property
    def excluded_technologies(self) -> list[str]:
        """list of technologies excluded from optimization."""
        val = self.excluded_technologies_
        if val is None or val.lower() == "none":
            return []
        if val.lower() == "all":
            return ["all"]
        return [tech.strip() for tech in val.split(";")]

    @property
    def excluded_thermal_strategies(self) -> list[str]:
        """list of thermal strategies excluded from optimization."""
        val = self.excluded_thermal_strategies_
        if val is None or val.lower() == "none":
            return []
        if val.lower() == "all":
            return [ThermalStrategy.BASE, ThermalStrategy.INTERMEDIATE, ThermalStrategy.PEAK]
        return [ThermalStrategy(strat.strip()) for strat in val.split(";")]

    @property
    def target_times(self) -> list[DateTime]:
        """Datetime index for the main optimization period."""
        return generate_datetimes(self.start_date, self.end_date, self.timestep, closed="left")

    @property
    def init_battery_time(self) -> DateTime:
        """Datetime for the initial battery state (start_date - timestep)."""
        return self.start_date - self.timestep

    @property
    def storage_mapping(self):
        storage_mapping: dict[StorageType, dict[str, int | float]] = {
            StorageType.BATTERY: {
                "nb_fragment": self.battery_number_of_fragments,
                "smoothing_factor": self.battery_smoothing_factor,
            },
            StorageType.PUMPED_HYDRAULIC_STORAGE: {
                "nb_fragment": self.pumped_hydraulic_number_of_fragments,
                "smoothing_factor": self.pumped_hydraulic_smoothing_factor,
            },
            StorageType.ELECTRIC_VEHICLE: {
                "nb_fragment": self.electric_vehicle_number_of_fragments,
                "smoothing_factor": self.electric_vehicle_smoothing_factor,
            },
        }
        return storage_mapping
