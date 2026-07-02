"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from functools import cached_property

from pendulum import DateTime, duration
from pydantic import Field, field_validator
from pydantic_extra_types.pendulum_dt import Duration

from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.enums import MarketType, StorageType
from atlas.io_utils.parameters import MultiProcessingParameters, SolverParameters
from atlas.objects.equipment.equipment import Equipment
from atlas.timing import generate_datetimes
from atlas.validators import ExclusionList, ThermalStrategyList, convert_to_duration


class PortfolioOptimisationParameters(AbstractModuleParameters):
    """Pydantic model for module parameters with documentation and defaults."""

    solver: SolverParameters = SolverParameters()  # type: ignore[call-arg]
    multiprocessing: MultiProcessingParameters = MultiProcessingParameters()

    is_portfolio_bidding: bool = Field(
        True, description="True if optimization is on portfolios, False for individual units."
    )
    use_forecast: bool = Field(
        False,
        description="Whether to take a price forecast. If true, optimization happens before a market.",
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
    battery_automated_reserve_duration: Duration = Field(
        default_factory=lambda: duration(minutes=60),
        description="Automated reserve duration for battery equipment.",  # type: ignore[assignment]
    )
    battery_nb_fragments: int = Field(
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
    electric_vehicle_nb_fragments: int = Field(3, description="Number of power fragments for electric vehicle.")
    electric_vehicle_reserve_duration: Duration = Field(
        default_factory=lambda: duration(minutes=1),
        description="Manual reserve duration for electric vehicle equipment.",  # type: ignore[assignment]
    )
    hydraulic_minimal_fragment_size: float = Field(
        100, description="Minimal amount of power for an offer to be formulated for hydraulic."
    )
    pumped_hydraulic_automated_reserve_duration: Duration = Field(
        default_factory=lambda: duration(minutes=60),
        description="Automated reserve duration for pumped hydraulic equipment.",  # type: ignore[assignment]
    )
    pumped_hydraulic_nb_fragments: int = Field(3, description="Number of power fragments for pumped hydraulic.")
    pumped_hydraulic_reserve_duration: Duration = Field(
        default_factory=lambda: duration(minutes=60),
        description="Manual reserve duration for pumped hydraulic equipment.",  # type: ignore[assignment]
    )
    excluded_market_areas: ExclusionList = Field(
        default_factory=list,
        description='list of market areas excluded from classic optimization. None and ["all"] are possible values.',
    )
    excluded_technologies: ExclusionList = Field(
        default_factory=list,
        description='list of equipment types excluded from classic optimization. None and ["all"] are possible values.',
    )
    excluded_thermal_strategies: ThermalStrategyList = Field(
        default_factory=list,
        description='list of thermal strategies for which manual activation is always used. "Peak", "Intermediate", "Base", ["all"], None.',
    )
    market: MarketType = Field(
        MarketType.dayahead,
        description='Market during which the Portfolio Optimization is run. Possible values: "DayAhead", "Intraday", "RRActivation", "MFRRActivation".',
    )

    @field_validator(
        "battery_automated_reserve_duration",
        "battery_reserve_duration",
        "electric_vehicle_automated_reserve_duration",
        "electric_vehicle_reserve_duration",
        "pumped_hydraulic_automated_reserve_duration",
        "pumped_hydraulic_reserve_duration",
        mode="before",
    )
    @classmethod
    def parse_duration(cls, v):
        """Convert various duration formats to Duration objects."""
        return convert_to_duration(v)

    @cached_property
    def portfolio_time_window(self) -> list[DateTime]:
        """Datetime index for the main optimization period (portfolio balance window)."""
        return generate_datetimes(
            self.temporal.start_date, self.temporal.end_date, self.temporal.timestep, closed="left"
        )

    @cached_property
    def _equipment_time_window_cache(self) -> dict[int, list[DateTime]]:
        return {}

    def equipment_time_window(self, equipment: Equipment) -> list[DateTime]:
        """Per-equipment dispatch window: portfolio_time_window extended by the equipment's `additional_hours` lookahead."""
        cache = self._equipment_time_window_cache
        key = id(equipment)
        if key not in cache:
            end = self.temporal.end_date - self.temporal.timestep + equipment.additional_hours
            cache[key] = generate_datetimes(self.temporal.start_date, end, self.temporal.timestep)
        return cache[key]

    @property
    def init_battery_time(self) -> DateTime:
        """Datetime for the initial battery state (start_date - timestep)."""
        return self.temporal.start_date - self.temporal.timestep

    @property
    def storage_mapping(self):
        storage_mapping: dict[StorageType, dict[str, int | float]] = {
            StorageType.BATTERY: {
                "nb_fragment": self.battery_nb_fragments,
                "smoothing_factor": self.battery_smoothing_factor,
            },
            StorageType.PUMPED_HYDRAULIC_STORAGE: {
                "nb_fragment": self.pumped_hydraulic_nb_fragments,
                "smoothing_factor": self.pumped_hydraulic_smoothing_factor,
            },
            StorageType.ELECTRIC_VEHICLE: {
                "nb_fragment": self.electric_vehicle_nb_fragments,
                "smoothing_factor": self.electric_vehicle_smoothing_factor,
            },
        }
        return storage_mapping
