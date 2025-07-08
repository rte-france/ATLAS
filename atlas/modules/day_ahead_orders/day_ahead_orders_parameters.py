"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import Field

from atlas.abstract_class.abstract_parameters import AbstractParameters


class DayAheadOrdersParameters(AbstractParameters):
    output_folder: str = Field(
        "DAO",
        description="Optional parameter to choose an output folder in the SAMBA folder where the LPs will be exported. "
        "If None, a folder will be created named 'DAO/{ExecutionDate}'.",
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
    thermic_additional_hours: float = Field(
        12,
        description="Number of extra hours after EndDate for the optimization programs applied to Thermic instances.",
    )
    battery_additional_hours: int = Field(
        48,
        description="Number of extra hours after EndDate for the optimization programs applied to Storage instances "
        "with the type Battery.",
    )
    battery_nb_fragments: int = Field(
        3,
        description="Number of orders that can be formulated at one time-step for the optimization problem related to "
        "the Storage instances with the type Battery.",
    )
    ev_additional_hours: int = Field(
        144,
        description="Number of extra hours after EndDate for the optimization programs applied to Storage instances "
        "with the type ElectricVehicle.",
    )
    ev_nb_fragments: int = Field(
        3,
        description="Number of orders that can be formulated at one time-step for the optimization problem related to "
        "the Storage instances with the type ElectricVehicle.",
    )
    phs_additional_hours: int = Field(
        144,
        description="Number of extra hours after EndDate for the optimization programs applied to Storage instances "
        "with the type PumpedHydraulicStorage.",
    )
    phs_nb_fragments: int = Field(
        3,
        description="Number of orders that can be formulated at one time-step for the optimization problem related to "
        "the Storage instances with the type PumpedHydraulicStorage.",
    )
    solver_time_out: int = Field(240, description="Timeout (in seconds) of the optimization.")
    time_step: int = Field(
        60,
        description="Discretization step of the simulated time interval, expressed as a string giving an integer "
        "number of minutes",
    )
    price_forecasts_types: str = Field(
        ["Medium", "High", "Low"],
        description="List of available PriceForecasts in the input data, separated by ';'. The default value should "
        "always include 'Medium'.",
    )
    solver: str = Field(
        "XPRESS",
        description="Name of the solver to use in the optimization problems. Note that only 'XPRESS' is maintained "
        "and tested, other solvers may result in unexpected behaviour. Other possible values : "
        "'GLPK', 'PNE', 'GLOP' (for linear problems only), 'SCIP', 'CP-SAT'.",
    )
