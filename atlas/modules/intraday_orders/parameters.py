"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from datetime import datetime
from functools import cached_property

from pendulum import duration, DateTime
from pydantic import Field, field_validator
from pydantic_extra_types.pendulum_dt import Duration

from atlas.abstract_class.abstract_parameters import AbstractParameters
from atlas.validators import convert_to_duration


class IntradayOrdersParameters(AbstractParameters):
    """Pydantic model for module parameters with documentation and defaults."""

    start_date: DateTime = Field(
        lambda: datetime.now(), description="Beginning of the timeframe studied by the module."
    )
    end_date: DateTime = Field(
        lambda: datetime.now(),
        description="End of the timeframe studied by the module. More precisely, the end of the last time step of this timeframe.",
    )
    execution_date: DateTime = Field(lambda: datetime.now(), description="Date from which the module is executed.")
    debug_mode: bool = Field(
        False,
        description="Boolean indicating whether the debug mode is activated or not for the optimization programs. If activated, returns the LP files of the optimization programs.",
    )
    electric_vehicles_complement_ordering: bool = Field(
        True, description="If True, COMPLEMENT coupling will be generated for Electric Vehicle orders."
    )
    proportional_reserves_penalty: bool = Field(
        True,
        description="A boolean indicating whether the amount of reserves offered is flexible, resulting in a proportional penalty priced to the market.",
    )
    verbose: bool = Field(True, description="If True, additional logs are generated.")
    allowed_round_off_error: float = Field(
        0.001,
        description="Threshold, in MW, below which the value of accepted power is considered equal to 0. Typical values: 0.001, 0.0001 or 0.00001.",
    )
    consumption_price: float = Field(3000.0, description="Price of all consumption orders, in euros/MWh.")
    epsilon: float = Field(
        0.001, description="A slack parameter to avoid infeasibility due to numerical approximations."
    )
    hydraulic_minimal_fragment_size: float = Field(
        150.0,
        description="Minimal amount of power for an offer to be formulated. If for one particular time-step, the quantity Qmax of an offer is less than this threshold, the associated fragment is removed. Then the Qmax values of the other fragments are renormalized.",
    )
    large_imbalance_penalty: float = Field(
        0.2,
        description="Parameters used to compute the Imbalance Settlement Price forecasts, that will define the price of Wind, PV and NDP buy orders.",
    )
    manual_unprocured_reserves_penalty: float = Field(
        10000.0,
        description="A penalty expressed in euros/MW per hour corresponding to the price of not providing the manual reserves procurement.",
    )
    thermal_additional_hours: int = Field(
        12,
        description="Number of extra hours after end_date for the optimization programs applied to Thermal instances.",
    )
    timestep: Duration = Field(lambda: duration(hours=1), description="Time step of the simulated market.")

    @cached_property
    def penultimate_date(self) -> DateTime:
        return self.end_date - self.timestep

    @field_validator(
        "timestep",
        "solver_timeout",
        mode="before",
    )
    @classmethod
    def parse_duration(cls, v):
        """Convert various duration formats to Duration objects."""
        return convert_to_duration(v)
