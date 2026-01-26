"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from functools import cached_property
from pathlib import Path

from pendulum import DateTime, duration
from pendulum.duration import Duration
from pydantic import Field, field_validator

from atlas.abstract_class.abstract_parameters import AbstractParameters
from atlas.validators import hours_validator, minutes_validator


class DayAheadOrdersParameters(AbstractParameters):
    output_folder: Path = Field(
        Path("DAO_lp_exports"),
        description="Optional parameter to choose an output folder in the folder where the LPs will be exported.",
    )
    verbose: bool = Field(
        True,
        description="A boolean indicating whether or not the program shall return detailed logs.",
    )
    debug: bool = Field(
        True,
        description="A boolean indicating if the script will run in debug mode.",
    )
    proportional_reserves_penalty: bool = Field(
        True,
        description="A boolean indicating whether the amount of reserves offered is flexible, resulting in a "
        "proportional penalty priced to the market",
    )
    use_presolve: bool = Field(
        True,
        description="Boolean indicating if a presolve step is desired or not before solving the optimization program.",
    )
    automated_unprocured_reserves_penalty: float = Field(
        10000,
        description="A penalty expressed in euros/MW per hour corresponding to the price of not providing the "
        "automated reserves procurement",
    )
    battery_smoothing_factor: float = Field(
        0.1,
        description="Coefficient used to determine the extra cost of each power fragment in the optimization problem "
        "related to the Storage instances with the type Battery.",
    )
    ev_energy_coef: float = Field(
        1.5,
        description="Coefficient multiplied to the delta of DisplacementEnergy to compensate for over the entire EV "
        "optimization time frame, used to generate enough Buy offers.",
    )
    ev_smoothing_factor: float = Field(
        0.1,
        description="Coefficient used to determine the extra cost of each power fragment in the optimization problem "
        "related to the Storage instances with the type ElectricVehicle.",
    )
    epsilon: float = Field(
        0.001, description="A slack parameter to avoid infeasibilities due to numerical approximations."
    )
    hydraulic_minimal_fragment_size: float = Field(
        100,
        description="Minimal amount of power for an offer to be formulated. If for one particular time-step, the "
        "quantity Qmax of an offer is less than this threshold, the associated fragment is removed. Then "
        "the Qmax values of the other fragments are renormalized.",
    )
    load_price: float = Field(
        3000,
        description="Price of all load orders (in euros/MWh). 3000 is a standard value, corresponding to the upper "
        "price cap of the DayAhead market.",
    )
    manual_unprocured_reserves_penalty: float = Field(
        100,
        description="A penalty expressed in euros/MW per hour corresponding to the price of not providing the manual "
        "reserves procurement.",
    )
    phs_smoothing_factor: float = Field(
        0.2,
        description="Coefficient used to determine the extra cost of each power fragment in the optimization problem "
        "related to the Storage instances with the type PumpedHydraulicStorage.",
    )
    solver_duality_gap: float = Field(0.0001, description="DualityGap used for the optimization.")
    thermic_additional_hours: Duration = Field(
        default_factory=lambda: duration(hours=12),
        description="Number of extra hours after EndDate for the optimization programs applied to Thermic instances.",
    )
    battery_additional_hours: Duration = Field(
        default_factory=lambda: duration(hours=48),
        description="Number of extra hours after EndDate for the optimization programs applied to Storage instances "
        "with the type Battery.",
    )
    battery_nb_fragments: int = Field(
        3,
        description="Number of orders that can be formulated at one time-step for the optimization problem related to "
        "the Storage instances with the type Battery.",
    )
    ev_additional_hours: Duration = Field(
        default_factory=lambda: duration(hours=144),
        description="Number of extra hours after EndDate for the optimization programs applied to Storage instances "
        "with the type ElectricVehicle.",
    )
    ev_nb_fragments: int = Field(
        3,
        description="Number of orders that can be formulated at one time-step for the optimization problem related to "
        "the Storage instances with the type ElectricVehicle.",
    )
    phs_additional_hours: Duration = Field(
        default_factory=lambda: duration(hours=144),
        description="Number of extra hours after EndDate for the optimization programs applied to Storage instances "
        "with the type PumpedHydraulicStorage.",
    )
    phs_nb_fragments: int = Field(
        3,
        description="Number of orders that can be formulated at one time-step for the optimization problem related to "
        "the Storage instances with the type PumpedHydraulicStorage.",
    )
    solver_time_out: Duration = Field(
        default_factory=lambda: duration(minutes=4), description="Timeout (in seconds) of the optimization."
    )
    time_step: Duration = Field(
        default_factory=lambda: duration(minutes=60),
        description="Discretization step of the simulated time interval, expressed as a string giving an integer "
        "number of minutes",
    )
    price_forecasts_types: list[str] = Field(
        ["Medium", "High", "Low"],
        description="List of available PriceForecasts in the input data, separated by ';'. The default value should "
        "always include 'Medium'.",
    )

    @cached_property
    def penultimate_date(self) -> DateTime:
        return self.end_date - self.time_step

    @cached_property
    def end_optimization_date(self) -> DateTime:
        return self.end_date + self.thermic_additional_hours

    @field_validator(
        "phs_additional_hours",
        "ev_additional_hours",
        "battery_additional_hours",
        "thermic_additional_hours",
        mode="before",
    )
    @classmethod
    def convert_hours_to_duration(cls, v):
        """Convert various duration formats to Duration objects (hours default)."""
        return hours_validator(v)

    @field_validator(
        "time_step",
        "solver_time_out",
        mode="before",
    )
    @classmethod
    def convert_minutes_to_duration(cls, v):
        """Convert various duration formats to Duration objects (minutes default)."""
        return minutes_validator(v)
