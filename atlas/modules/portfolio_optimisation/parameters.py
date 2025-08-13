"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pendulum import DateTime, duration
from pendulum.duration import Duration
from pydantic import Field, field_validator

from atlas.abstract_class.abstract_parameters import AbstractParameters
from atlas.enum import MarketType, SolverEnum, StorageType, ThermalStrategy
from atlas.timing import generate_datetimes
from atlas.validators import hours_validator, minutes_validator


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
    battery_automated_reserve_duration: Duration = Field(
        default_factory=lambda: duration(minutes=60), description="Automated reserve duration for battery equipment."
    )
    battery_number_of_fragments: int = Field(
        3, description="Number of power fragments for battery; last fragments are more expensive."
    )
    battery_reserve_duration: Duration = Field(
        default_factory=lambda: duration(minutes=60), description="Manual reserve duration for battery equipment."
    )
    electric_vehicle_automated_reserve_duration: Duration = Field(
        default_factory=lambda: duration(minutes=1),
        description="Automated reserve duration for electric vehicle equipment.",
    )
    electric_vehicle_number_of_fragments: int = Field(3, description="Number of power fragments for electric vehicle.")
    electric_vehicle_reserve_duration: Duration = Field(
        lambda: duration(minutes=1), description="Manual reserve duration for electric vehicle equipment."
    )
    hydraulic_minimal_fragment_size: int = Field(
        100, description="Minimal amount of power for an offer to be formulated for hydraulic."
    )
    pumped_hydraulic_automated_reserve_duration: Duration = Field(
        default_factory=lambda: duration(minutes=60),
        description="Automated reserve duration for pumped hydraulic equipment.",
    )
    pumped_hydraulic_number_of_fragments: int = Field(3, description="Number of power fragments for pumped hydraulic.")
    pumped_hydraulic_reserve_duration: Duration = Field(
        default_factory=lambda: duration(minutes=60),
        description="Manual reserve duration for pumped hydraulic equipment.",
    )

    solver_timeout: Duration = Field(
        default_factory=lambda: duration(seconds=60), description="Timeout (in seconds) of the optimization."
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
        description="Default optimization period in hours for PV, Wind, and Load. Overwritten by specific equipment.",
    )
    battery_additional_hours: Duration = Field(
        default_factory=lambda: duration(hours=48),
        description="Optimization period in hours for Storage Equipments of type Battery.",
    )
    electric_vehicle_additional_hours: Duration = Field(
        default_factory=lambda: duration(hours=0),
        description="Optimization period in hours for Storage Equipments of type ElectricVehicle.",
    )
    hydraulic_additional_hours: Duration = Field(
        default_factory=lambda: duration(hours=12),
        description="Optimization period in hours for hydraulic group.",
    )
    pumped_hydraulic_storage_additional_hours: Duration = Field(
        default_factory=lambda: duration(hours=144),
        description="Optimization period in hours for Storage Equipments of type PumpedHydraulicStorage.",
    )
    thermal_additional_hours: Duration = Field(
        default_factory=lambda: duration(hours=12),
        description="Optimization period in hours for thermal group.",
    )
    timestep: Duration = Field(
        default_factory=lambda: duration(hours=1),
        description="Time step (in hours) of the simulated market.",
    )

    @field_validator(
        "additional_hours",
        "battery_additional_hours",
        "electric_vehicle_additional_hours",
        "hydraulic_additional_hours",
        "pumped_hydraulic_storage_additional_hours",
        "thermal_additional_hours",
        "timestep",
        mode="before",
    )
    @classmethod
    def convert_hours_to_duration(cls, v):
        """Convert various duration formats to Duration objects (hours default)."""
        return hours_validator(v)

    @field_validator(
        "pumped_hydraulic_automated_reserve_duration",
        "battery_automated_reserve_duration",
        "electric_vehicle_automated_reserve_duration",
        "electric_vehicle_reserve_duration",
        "battery_reserve_duration",
        "pumped_hydraulic_reserve_duration",
        mode="before",
    )
    @classmethod
    def convert_minutes_to_duration(cls, v):
        """Convert various duration formats to Duration objects (minutes default)."""
        return minutes_validator(v)

    @property
    def target_times(self) -> list[DateTime]:
        """Datetime index for the main optimization period."""
        return generate_datetimes(self.start_date, self.end_date, self.timestep)

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
    def adjusted_end_date(self) -> DateTime:
        """End date adjusted by subtracting one time step."""
        return self.end_date - self.timestep

    @property
    def renewables_load_op_times(self) -> list[DateTime]:
        """Datetime index for the main optimization period (with additional hours)."""
        end = self.adjusted_end_date + self.additional_hours
        return generate_datetimes(self.start_date, end, self.timestep)

    @property
    def thermal_optimization_period(self) -> int:
        return len(self.target_times) + int(self.thermal_additional_hours / self.timestep)

    @property
    def thermal_op_times(self) -> list[DateTime]:
        end = self.adjusted_end_date + self.thermal_additional_hours
        return generate_datetimes(self.start_date, end, self.timestep)

    @property
    def hydraulic_op_times(self) -> list[DateTime]:
        end = self.adjusted_end_date + self.hydraulic_additional_hours
        return generate_datetimes(self.start_date, end, self.timestep)

    @property
    def battery_op_times(self) -> list[DateTime]:
        end = self.adjusted_end_date + self.battery_additional_hours
        return generate_datetimes(self.start_date, end, self.timestep)

    @property
    def phs_op_times(self) -> list[DateTime]:
        end = self.adjusted_end_date + self.pumped_hydraulic_storage_additional_hours
        return generate_datetimes(self.start_date, end, self.timestep)

    @property
    def ev_op_times(self) -> list[DateTime]:
        end = self.adjusted_end_date + self.electric_vehicle_additional_hours
        return generate_datetimes(self.start_date, end, self.timestep)

    @property
    def init_battery_time(self) -> DateTime:
        """Datetime for the initial battery state (start_date - timestep)."""
        return self.start_date - self.timestep

    @property
    def storage_mapping(self):
        storage_mapping: dict[StorageType, dict[str, list[DateTime] | int | float]] = {
            StorageType.BATTERY: {
                "optimisation_times": self.battery_op_times,
                "nb_fragment": self.battery_number_of_fragments,
                "smoothing_factor": self.battery_smoothing_factor,
            },
            StorageType.PUMPED_HYDRAULIC_STORAGE: {
                "optimisation_times": self.phs_op_times,
                "nb_fragment": self.pumped_hydraulic_number_of_fragments,
                "smoothing_factor": self.pumped_hydraulic_smoothing_factor,
            },
            StorageType.ELECTRIC_VEHICLE: {
                "optimisation_times": self.ev_op_times,
                "nb_fragment": self.electric_vehicle_number_of_fragments,
                "smoothing_factor": self.electric_vehicle_smoothing_factor,
            },
        }
        return storage_mapping
