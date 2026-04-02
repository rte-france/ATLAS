"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from functools import cached_property

from pendulum import DateTime
from pydantic import Field

from atlas.abstract_class.abstract_parameters import AbstractParameters
from atlas.io_utils.parameters import (
    MultiProcessingParameters,
    SolverParameters,
)


class DayAheadOrdersParameters(AbstractParameters):
    solver: SolverParameters = SolverParameters()  # type: ignore[call-arg]

    multiprocessing: MultiProcessingParameters = MultiProcessingParameters()

    proportional_reserves_penalty: bool = Field(
        True,
        description="A boolean indicating whether the amount of reserves offered is flexible, resulting in a "
        "proportional penalty priced to the market",
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
        description="Minimal amount of power for an offer to be formulated. If for one particular timestep, the "
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
    battery_nb_fragments: int = Field(
        3,
        description="Number of orders that can be formulated at one timestep for the optimization problem related to "
        "the Storage instances with the type Battery.",
    )
    ev_nb_fragments: int = Field(
        3,
        description="Number of orders that can be formulated at one timestep for the optimization problem related to "
        "the Storage instances with the type ElectricVehicle.",
    )
    phs_nb_fragments: int = Field(
        3,
        description="Number of orders that can be formulated at one timestep for the optimization problem related to "
        "the Storage instances with the type PumpedHydraulicStorage.",
    )
    price_forecasts_types: list[str] = Field(
        ["Medium", "High", "Low"],
        description="List of available PriceForecasts in the input data, separated by ';'. The default value should "
        "always include 'Medium'.",
    )

    @cached_property
    def penultimate_date(self) -> DateTime:
        return self.temporal.end_date - self.temporal.timestep
