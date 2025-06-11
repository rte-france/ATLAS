"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import Field
from pydantic_extra_types.pendulum_dt import DateTime
from atlas.abstract_class.abstract_parameters import AbstractParameters


class DayAheadOrdersParameters(AbstractParameters):
    start_date: DateTime = Field(
        "2028-09-02 00:00:00",
        description="Beginning of the timeframe studied by the module. "
        "NB: In action plan context, value is automatically set according to task settings, and should not "
        "be reconfigured in the parameters of the study case.",
    )
    execution_date: DateTime = Field(
        "2028-09-01 12:00:00",
        description="Date from which the module is executed. "
        "NB: In action plan context, value is automatically set according to task settings, and should not "
        "be reconfigured in the parameters of the study case.",
    )
    end_date: DateTime = Field(
        "2028-09-03 00:00:00",
        description="End of the timeframe studied by the module. More precisely, the end of the last time step of this timeframe. "
        "NB: In action plan context, value is automatically set according to task settings, and should not "
        "be reconfigured in the parameters of the study case.",
    )
    output_folder: str = Field(
        "DAO",
        description="Optional parameter to choose an output folder in the SAMBA folder where the LPs will be exported. "
        "If None, a folder will be created named 'DAO/{ExecutionDate}'.",
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
    electric_vehicle_energy_coeff: float = Field(
        1.5,
        description="Coefficient multiplied to the delta of DisplacementEnergy to compensate for over the entire EV "
        "optimization time frame, used to generate enough Buy offers.",
    )
    electric_vehicle_smoothing_factor: float = Field(
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
    pumped_hydraulic_storage_smoothing_factor: float = Field(
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
    battery_number_of_fragments: int = Field(
        3,
        description="Number of orders that can be formulated at one time-step for the optimization problem related to "
        "the Storage instances with the type Battery.",
    )
    electric_vehicle_additional_hours: int = Field(
        144,
        description="Number of extra hours after EndDate for the optimization programs applied to Storage instances "
        "with the type ElectricVehicle.",
    )
    electric_vehicle_number_of_fragments: int = Field(
        3,
        description="Number of orders that can be formulated at one time-step for the optimization problem related to "
        "the Storage instances with the type ElectricVehicle.",
    )
    pumped_hydraulic_storage_additional_hours: int = Field(
        144,
        description="Number of extra hours after EndDate for the optimization programs applied to Storage instances "
        "with the type PumpedHydraulicStorage.",
    )
    pumped_hydraulic_storage_number_of_fragments: int = Field(
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
