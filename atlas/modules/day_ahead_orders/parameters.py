"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from functools import cached_property
from pathlib import Path

from pendulum import DateTime, Duration
from pydantic import Field, field_validator

from atlas.abstract_class.abstract_parameters import AbstractParameters
from atlas.validators import convert_to_duration


class DayAheadOrdersParameters(AbstractParameters):
    export_lp_path: Path = Field(
        Path("DAO_lp_exports"),
        description="Optional parameter to choose an output folder in the folder where the LPs will be exported.",
    )
    export_lp: bool = Field(False, description="Boolean indicating if the LP model should be exported to a file.")
    proportional_reserves_penalty: bool = Field(
        True,
        description="A boolean indicating whether the amount of reserves offered is flexible, resulting in a "
        "proportional penalty priced to the market",
    )
    use_presolve: bool = Field(
        True,
        description="Boolean indicating if a presolve step is desired or not before solving the optimization program.",
    )
    use_multiprocessing: bool = Field(
        False,
        description="If True, use multiprocessing for parallel storage and thermal optimization. If False, use sequential for loop.",
    )
    max_workers: int | None = Field(
        None,
        description="Maximum number of parallel processes for equipment optimization. None defaults to CPU count. Only used if use_multiprocessing is True.",
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
    solver_duality_gap: float = Field(0.0001, description="duality gap used for the optimization.")
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
    solver_timeout: Duration = Field(
        default_factory=lambda: Duration(minutes=4), description="Timeout of the optimization."
    )
    timestep: Duration = Field(
        default_factory=lambda: Duration(minutes=60), description="Discretization step of the simulated time interval"
    )
    price_forecasts_types: list[str] = Field(
        ["Medium", "High", "Low"],
        description="List of available PriceForecasts in the input data, separated by ';'. The default value should "
        "always include 'Medium'.",
    )

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
