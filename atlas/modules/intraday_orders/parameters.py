"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from functools import cached_property

from pendulum import DateTime
from pydantic import Field

from atlas.abstract_class.parameters import AbstractModuleParameters


class IntradayOrdersParameters(AbstractModuleParameters):
    """Pydantic model for module parameters with documentation and defaults."""

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

    @cached_property
    def penultimate_date(self) -> DateTime:
        return self.temporal.end_date - self.temporal.timestep
