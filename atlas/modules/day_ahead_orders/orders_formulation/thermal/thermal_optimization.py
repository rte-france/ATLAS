"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import math
import os
from datetime import datetime
from typing import Literal

import pendulum
from pendulum._pendulum import Duration

import atlas.config as cfg
from atlas import OptimisationModel, generate_datetimes
from atlas.enum import SolverEnum
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.thermal import Thermal
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters


class ThermalOptimization(OptimisationModel):
    """
    This class modelize the optimization program associated to the thermic units. It only
    performs the optimization for one unit, passed as an argument.
    Optimization is done over the extended optimization period, ie between start_date - epsilon
    and end_optimization_date + epsilon where epsilon is an additional time corresponding to
    the maximum between the minimum duration time and the startup duration.
    Optimization is done with respect to a given price sequence given.
    """

    def __init__(
        self,
        parameters: DayAheadOrdersParameters,
        thermal_unit: Thermal,
        prices,
        price_type,
    ):
        """
        :param parameters: a DayAheadOrdersParameters instance
        :param thermal_unit: a Thermal instance
        :param prices: a price timeseries based on which optimization will be conducted.
        :param price_type: the price_type
        """
        super().__init__(
            solver_name=parameters.solver.upper(),
            name=f"Optimization program for thermal unit {thermal_unit.name}",
        )
        self.parameters = parameters
        if self.solver_name != SolverEnum.XPRESS:
            # If another solver is being used, consider setting the NoOverlap parameter to False as it previously raised errors otherwise with GLPK
            raise ValueError(
                "Please use XPRESS, as other solvers either are deprecated or provide non-optimal solutions"
            )
        # Quick sanity check on the class of the equipment supplied as input.
        if not type(thermal_unit).__name__ == "Thermal":
            cfg.logger.error(f"*** WARNING ***\n Equipement {thermal_unit.name} is not of type thermic.")
            raise ValueError("Wrong equipment type for the thermic optimization program.")
        self.thermal_unit = thermal_unit
        self.prices = prices
        self.price_type = price_type
        self.T_on = None
        self.T_off = None
        self.T_stable = None
        self.time_frame = list[pendulum.DateTime]
        self.T_start = None
        self.T_stop = None
        self.previous_time_frame = []
        self.extended_start_date = None
        self.q_lower = None
        self.q_upper = None
        self.maximum_automated = None
        self.reserves_up_procured = None
        self.reserves_down_procured = None
        self.feasible_automated_reserves_up_procured = None
        self.feasible_automated_reserves_down_procured = None
        self.automated_unsupplied_reserves = 0
        self.delta_q = None
        self.delta_q_unconstrained = None
        self.q = {}
        self.reserves_up = {}
        self.reserves_down = {}
        self.unprovided_reserves_up = {}
        self.unprovided_reserves_down = {}
        self.relaxed_reserves = {}
        self.automated_reserves_up = {}
        self.automated_reserves_down = {}
        self.contracted_difference_up = {}
        self.contracted_difference_down = {}
        self.automated_contracted_difference_up = {}
        self.automated_contracted_difference_down = {}
        self.OFF = {}
        self.ON_DOWN = {}
        self.ON_UP = {}
        self.start_time_steps = None
        self.stop_time_steps = None
        self.START = {}
        self.STOP = {}
        self.start_date_minus_one = None
        self.ON_FLAT = {}
        self.turned_on = {}  # Corresponding to the variable defined in sec. 6.1.1
        self.turned_off = {}  # Corresponding to the variable defined in sec. 6.1.2
        self.time_frame_union_minus_one = None
        self.Q_max = None
        self.Q_min = None
        self.stable = {}  # This auxiliary variable indicates when the unit enters the FLAT state
        self.entered_up = {}  # This variable replaces ON_UP in the definition of the gradient and will bound the gradient for only one time step
        self.entered_down = {}  # Same as single_on_up but for on down
        self.U = {}  # This variable will be implemented in the gradient and bound the upward gradient
        self.tilde_U = {}
        self.D = {}  # This variable will be implemented in the gradient and bound the downward gradient
        self.tilde_D = {}
        self.last_power = None
        self.last_date = None

        # Power gradients
        # Definition of the gradients_time_frame : starts at start_date - time_step and goes until T-1
        # Gradients are defined on a "shifted" time frame.
        self.gradients_time_frame = generate_datetimes(
            self.parameters.start_date - self.parameters.time_step,
            self.parameters.end_optimization_date - 2 * self.parameters.time_step,
            self.parameters.time_step,
        )

        self._initial_setup()
        self.define_initial_parameters()
        self.create_objective_function("maximize")
        self.create_constraints_and_init_conitions()

    def _initial_setup(self):
        """STEP 0 : Retrieve the parameters of the program and set up the time frame"""

        # Sanity check on the start_date and the end_date. A warning message is sent to the user if the start_date is later
        # than the end_date.
        if self.parameters.start_date > self.parameters.end_optimization_date:
            cfg.logger.error(
                "*** WARNING ***\n The end_optimization_date is earlier than or identical to the start_date. \n"
                "The time frame cannot be defined. Please check the values of start_date, EndDate and AdditionalHours"
            )
            raise ValueError("Improper dates")

        # Get the parameters of the unit
        fcr_up_procured = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, 0
        )
        fcr_down_procured = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, 0
        )
        afrr_up_procured = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, 0
        )
        afrr_down_procured = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, 0
        )
        mfrr_up_procured = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, 0
        )
        mfrr_down_procured = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, 0
        )
        rr_up_procured = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, 0
        )
        rr_down_procured = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, 0
        )
        if self.thermal_unit.fcr_up_procured:
            fcr_up_procured = self.thermal_unit.fcr_up_procured.get_forecast(
                self.parameters.execution_date, self.parameters.start_date, self.parameters.end_optimization_date
            )
        if self.thermal_unit.fcr_down_procured:
            fcr_down_procured = self.thermal_unit.fcr_down_procured.get_forecast(
                self.parameters.execution_date, self.parameters.start_date, self.parameters.end_optimization_date
            )
        if self.thermal_unit.afrr_up_procured:
            afrr_up_procured = self.thermal_unit.afrr_up_procured.get_forecast(
                self.parameters.execution_date, self.parameters.start_date, self.parameters.end_optimization_date
            )
        if self.thermal_unit.afrr_down_procured:
            afrr_down_procured = self.thermal_unit.afrr_down_procured.get_forecast(
                self.parameters.execution_date, self.parameters.start_date, self.parameters.end_optimization_date
            )
        if self.thermal_unit.mfrr_up_procured:
            mfrr_up_procured = self.thermal_unit.mfrr_up_procured.get_forecast(
                self.parameters.execution_date, self.parameters.start_date, self.parameters.end_optimization_date
            )
        if self.thermal_unit.mfrr_down_procured:
            mfrr_down_procured = self.thermal_unit.mfrr_down_procured.get_forecast(
                self.parameters.execution_date, self.parameters.start_date, self.parameters.end_optimization_date
            )
        if self.thermal_unit.rr_up_procured:
            rr_up_procured = self.thermal_unit.rr_up_procured.get_forecast(
                self.parameters.execution_date, self.parameters.start_date, self.parameters.end_optimization_date
            )
        if self.thermal_unit.rr_down_procured:
            rr_down_procured = self.thermal_unit.rr_down_procured.get_forecast(
                self.parameters.execution_date, self.parameters.start_date, self.parameters.end_optimization_date
            )

        # Check that the minimum_stable_power_duration is smaller than the minimumTimeOn
        # if not thermal_unit.minimum_stable_power_duration <= thermal_unit.minimum_time_on:
        #    # Warn the user
        #    warning_message =  """
        #        *** WARNING *** \n
        #        the minimum_stable_power_duration of equipment {} is greater than its minimum_time_on.\n
        #        minimum_stable_power_duration has been modified and is now considered equal to minimum_time_on.
        #        """.format(thermal_unit.name)
        #    if p.verbose:
        #        API.IO.Trace.Log(warning_message)

        #    # Change the value of minimum_stable_power_duration
        #    # Take the maximum between 1 and minimumTimeOn because self.T_on > 0
        #    minimum_stable_power_duration = max(1, thermal_unit.minimum_time_on) # Enforces equations (1) of the documentation
        # else:
        #    minimum_stable_power_duration = thermal_unit.minimum_stable_power_duration
        minimum_stable_power_duration = self.thermal_unit.minimum_stable_power_duration

        # Conversion of the equipment-specific parameters in terms of time step.
        # All T_.'s are integers (by definition).
        if self.thermal_unit.minimum_time_on.total_hours() > 0:
            self.T_on = (
                int(
                    max(
                        1,
                        math.ceil(
                            self.thermal_unit.minimum_time_on.total_minutes()
                            / self.parameters.time_step.total_minutes()
                        ),
                    )
                )
                + 1
            )
        else:
            self.T_on = 0

        if self.thermal_unit.minimum_time_off.total_hours() > 0:
            self.T_off = (
                int(
                    max(
                        1,
                        math.ceil(
                            self.thermal_unit.minimum_time_off.total_minutes()
                            / self.parameters.time_step.total_minutes()
                        ),
                    )
                )
                + 1
            )
        else:
            self.T_off = 0
        self.T_start = int(
            math.floor(self.thermal_unit.startup_duration.total_minutes() / self.parameters.time_step.total_minutes())
        )
        self.T_stop = int(
            math.floor(self.thermal_unit.shutdown_duration.total_minutes() / self.parameters.time_step.total_minutes())
        )

        if minimum_stable_power_duration.total_minutes() >= self.parameters.time_step.total_minutes():
            self.T_stable = (
                int(
                    math.ceil(minimum_stable_power_duration.total_minutes() / self.parameters.time_step.total_minutes())
                )
                + 1
            )
        else:
            self.T_stable = 0

        # Rescale self.T_stable so that it is either equal to 0 or >= 2:
        self.T_stable = self.T_stable if self.T_stable >= 2 else 0

        # Set-up the time frames
        # Definition of the time_frame time frame : the time frame on which
        # the optimization program will be solved.
        # Remark: we define the time series until end_date - time_step because
        # we want all time steps to lie in the [start_date, end_optimization_date] range.
        end_date = self.parameters.end_optimization_date - self.parameters.time_step
        self.time_frame = generate_datetimes(self.parameters.start_date, end_date, self.parameters.time_step)

        # Define T_traceback, the number of timesteps we need to go before start_date to define the initial conditions.
        # We add +1 in order to avoid out-of-bounds errors when defining the ON_FLAT state.
        T_traceback = int(max(self.T_on + self.T_start, self.T_off + self.T_stop)) + 1

        # Define manually the previous_time_frame, which contains all time steps from start_date to (start_date - T_traceback * time_step)
        for k in range(1, T_traceback + 1):
            self.previous_time_frame.append(self.parameters.start_date - k * self.parameters.time_step)

            # Define the extendedTimeFrame, ranging from the last element of the previous_time_frame to end_optimization_date.
        # We also start from 1 in order to exclude start_date from the previous_time_frame.
        self.extended_start_date = self.previous_time_frame[-1]  # Last date in the previous_time_frame

        # Retrieve the values of the Power attribute over previous_time_frame
        if self.thermal_unit.power:
            self.last_power = self.thermal_unit.power.get_forecast(
                self.parameters.execution_date,
                self.extended_start_date,
                self.parameters.start_date - self.parameters.time_step,
            )  # Extract the time series corresponding to the previous period
        else:
            self.last_power = Timeseries.from_index(
                self.extended_start_date,
                self.parameters.time_step,
                self.parameters.start_date - self.parameters.time_step,
                0,
            )

        self.last_date = self.last_power.last_date()  # get the last date with a recorded value

        # Set-up the power bounds : copy maximum- and minimum_power
        # because q_lower and q_upper may be modified afterwards.
        self.q_lower = Timeseries.from_timeseries(self.thermal_unit.minimum_power)
        self.q_upper = Timeseries.from_timeseries(self.thermal_unit.maximum_power)

        # Set-up the reserve requirements
        # Compute the maximum_automated
        self.maximum_automated = self.thermal_unit.maximum_afrr + self.thermal_unit.maximum_fcr

        # Add the manual reserves (referred to as "reserves" in the following)
        # Reserves
        self.reserves_up_procured = mfrr_up_procured + rr_up_procured
        self.reserves_down_procured = mfrr_down_procured + rr_down_procured
        # Compute the feasibleAutomatedReserves. This is to accomodate for the fact that the maximumAFRR and maximumFCR capacities
        # may be different.If the unit has a procurement greater than its capacity, the remaning part will be unsupplied and counted
        # in a penalty added in the objective function.

        # Create the time series of feasible automated reserves procurements
        self.feasible_automated_reserves_up_procured = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, end_date, default_value=0
        )
        self.feasible_automated_reserves_down_procured = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, end_date, default_value=0
        )

        # Populate the time series and retrieve the infeasible automated reserve procurements.
        for t in self.time_frame:
            # retrieve the feasible part in the feasible time series
            self.feasible_automated_reserves_up_procured[t] = min(
                afrr_up_procured.get_value(t), self.thermal_unit.maximum_afrr
            ) + min(fcr_up_procured.get_value(t), self.thermal_unit.maximum_fcr)
            self.feasible_automated_reserves_down_procured[t] = min(
                afrr_down_procured.get_value(t), self.thermal_unit.maximum_afrr
            ) + min(fcr_down_procured.get_value(t), self.thermal_unit.maximum_fcr)

            # retrieve and save the infeasible part
            self.automated_unsupplied_reserves += (
                max(afrr_up_procured.get_value(t) - self.thermal_unit.maximum_afrr, 0)
                + max(fcr_up_procured.get_value(t) - self.thermal_unit.maximum_fcr, 0)
                + max(afrr_down_procured.get_value(t) - self.thermal_unit.maximum_afrr, 0)
                + max(fcr_down_procured.get_value(t) - self.thermal_unit.maximum_fcr, 0)
            )

        if self.parameters.verbose:
            cfg.logger.info(f"automated unsupplied reserves : {self.automated_unsupplied_reserves}")

        # Set-up the power gradients
        self.delta_q = self.thermal_unit.maximum_gradient * self.parameters.time_step
        self.delta_q_unconstrained = self.thermal_unit.maximum_power.max()

    def define_initial_parameters(self):
        """STEP 1 : Definition of the state, auxiliary and control variables over the time_frame."""

        # 1.1. Control variables :
        #    - the power output of the unit
        #    - the reserves of the unit and the mirror variables
        #    - contracted difference which corresponds to max(procured - provided, 0).
        # Define the main optimization variable. Bounds : O and self.q_upper
        for t in self.time_frame:
            self.q[t] = self.add_continuous_variable(
                f"power_equip_{self.thermal_unit.name}_at_{t}",
                0,
                self.q_upper.get_value(t),
            )

        # Define the reserves variables
        # reserves_up and reserves_down are defined no matter the value of self.T_stable. Only the type of reserves it encompasses changes.
        for t in self.time_frame:
            self.reserves_up[t] = self.add_continuous_variable(
                f"reservesUp_equip_{self.thermal_unit.name}_at_{t}",
                0,
                self.q_upper.get_value(t),
            )

            self.reserves_down[t] = self.add_continuous_variable(
                f"reservesDown_equip_{self.thermal_unit.name}_at_{t}",
                0,
                self.q_upper.get_value(t),
            )

            self.unprovided_reserves_up[t] = self.add_continuous_variable(
                f"unprovidedReservesUp_equip_{self.thermal_unit.name}_at_{t}",
                0,
                self.q_upper.get_value(t),
            )

            self.unprovided_reserves_down[t] = self.add_continuous_variable(
                f"unprovidedReservesDown_equip_{self.thermal_unit.name}_at_{t}",
                0,
                self.q_upper.get_value(t),
            )

            self.relaxed_reserves[t] = self.add_continuous_variable(
                f"relaxedReserves_equip_{self.thermal_unit.name}_at_{t}",
                0,
                self.q_lower.get_value(t),
            )

        # create the automatedReserves control variables.
        for t in self.time_frame:
            self.automated_reserves_up[t] = self.add_continuous_variable(
                f"automatedReservesUp_equip_{self.thermal_unit.name}_at_{t}",
                0,
                self.maximum_automated,
            )

            self.automated_reserves_down[t] = self.add_continuous_variable(
                f"automatedReservesDown_equip_{self.thermal_unit.name}_at_{t}",
                0,
                self.maximum_automated,
            )

        # Create the contractedDifference variables. These variables are implemented as control variables will be included in the
        # objective function and constrained by constraint (40).
        for t in self.time_frame:
            self.contracted_difference_up[t] = self.add_continuous_variable(
                f"contractedDifferenceUp_equip_{self.thermal_unit.name}_at_{t}",
                0,
                self.q_upper.get_value(t),
            )
            self.contracted_difference_down[t] = self.add_continuous_variable(
                f"contractedDifferenceDown_equip_{self.thermal_unit.name}_at_{t}",
                0,
                self.q_upper.get_value(t),
            )

        # Automated contracted difference variables. These variables will be constrained by equation (39).
        for t in self.time_frame:
            self.automated_contracted_difference_up[t] = self.add_continuous_variable(
                f"automatedContractedDifferenceUp_equip_{self.thermal_unit.name}_at_{t}",
                0,
                self.q_upper.get_value(t),
            )
            self.automated_contracted_difference_down[t] = self.add_continuous_variable(
                f"automatedContractedDifferenceDown_equip_{self.thermal_unit.name}_at_{t}",
                0,
                self.q_upper.get_value(t),
            )

        # 1.2. State variables (always in upper case)

        # 1.2.1. Initialization of the state variables that are always defined :
        # OFF, ON_UP, ON_FLAT and ON_DOWN

        # Create the state variables for each time step over the extended time frame.
        for t in self.time_frame:
            self.OFF[t] = self.add_boolean_variable(f"OFF_equip_{self.thermal_unit.name}_at_{t}")
            self.ON_UP[t] = self.add_boolean_variable(f"ON_UP_equip_{self.thermal_unit.name}_at_{t}")
            self.ON_DOWN[t] = self.add_boolean_variable(f"ON_DOWN_equip_{self.thermal_unit.name}_at_{t}")

        # 1.2.2. 'Conditional' state variables : defined only if a certain criteria on T is met.
        if self.T_start >= 1:
            # Define the start_time_steps range, i.e. the interval {1,...,T_start - 1}
            self.start_time_steps = range(1, self.T_start - 1)

            # Define the START state variable.
            for t in self.time_frame:
                self.START[t] = self.add_boolean_variable(f"START_equip_{self.thermal_unit.name}_at_{t}")

        if self.T_stop >= 1:
            # Define the stop_time_steps range.
            self.stop_time_steps = range(1, self.T_stop - 1)

            # Define the STOP state variable
            for t in self.time_frame:
                self.STOP[t] = self.add_boolean_variable(f"STOP_equip_{self.thermal_unit.name}_at_{t}")

        if self.T_stable >= 1:
            self.start_date_minus_one = self.parameters.start_date - self.parameters.time_step
            for t in self.time_frame:
                self.ON_FLAT[t] = self.add_boolean_variable(f"ON_FLAT_equip_{self.thermal_unit.name}_at_{t}")

            # For the time step start_date - 1, create optimization avariables for ON_FLAT, ON_UP and ON_DOWN
            self.ON_FLAT[self.start_date_minus_one] = self.add_boolean_variable(
                f"ON_FLAT_equip_{self.thermal_unit.name}_at_{self.start_date_minus_one}"
            )

            self.ON_DOWN[self.start_date_minus_one] = self.add_boolean_variable(
                f"ON_DOWN_equip_{self.thermal_unit.name}_at_{self.start_date_minus_one}"
            )

            self.ON_UP[self.start_date_minus_one] = self.add_boolean_variable(
                f"ON_UP_equip_{self.thermal_unit.name}_at_{self.start_date_minus_one}"
            )

        # 1.3. Auxiliary variables
        # Remark. Auxiliary variables are formally binary variables but due to their
        # defining constraints (see below), they can be defined as continuous values comprised in [0,1].
        # Constraints will ensure that the value they take is always 0 or 1.
        # Convention : auxiliary variables are written in lower case

        # 1.3.1. Create the auxiliary variables that will always be defined
        for t in self.time_frame:
            self.turned_on[t] = self.add_continuous_variable(f"turned_on_equip_{self.thermal_unit.name}_at_{t}", 0, 1)

            self.turned_off[t] = self.add_continuous_variable(f"turned_off_equip_{self.thermal_unit.name}_at_{t}", 0, 1)

        # 1.3.2. Create the condtionnal auxiliary variables if necessary.

        # Variable indicating that the unit is stable at t (sec. 6.1.3)
        # and variables to constrain the gradient U[t], D[t] and tilde_U[t], tilde_D[t] (defined in sec 6.2.4.)
        if self.T_stable >= 1:
            # Define the time_frame_union_minus_one which includes the start_date_minus_one time step.
            self.time_frame_union_minus_one = generate_datetimes(
                self.parameters.start_date - self.parameters.time_step,
                self.parameters.end_optimization_date - self.parameters.time_step,
                self.parameters.time_step,
            )

            # Define dummy bounds for the gradient auxiliaries
            self.Q_max = self.delta_q_unconstrained
            self.Q_min = -self.Q_max

            for t in self.time_frame_union_minus_one:
                # Define the auxiliary variables of this state.
                self.stable[t] = self.add_continuous_variable(f"stable_at_{t}_equip_{self.thermal_unit.name}", 0, 1)
                self.entered_up[t] = self.add_continuous_variable(
                    f"entered_up_at_{t}_equip_{self.thermal_unit.name}", 0, 1
                )
                self.entered_down[t] = self.add_continuous_variable(
                    f"entered_down_at_{t}_equip_{self.thermal_unit.name}", 0, 1
                )

            for t in self.time_frame:
                # Initialize the gradient auxiliaries.
                self.U[t] = self.add_continuous_variable(
                    f"UP_grad_at_{t}_equip_{self.thermal_unit.name}",
                    self.Q_min,
                    self.Q_max,
                )
                self.D[t] = self.add_continuous_variable(
                    f"DOWN_grad_at_{t}_equip_{self.thermal_unit.name}",
                    self.Q_min,
                    self.Q_max,
                )
                self.tilde_U[t] = self.add_continuous_variable(
                    f"aux_up_grad_at_{t}_equip_{self.thermal_unit.name}",
                    self.Q_min,
                    self.Q_max,
                )
                self.tilde_D[t] = self.add_continuous_variable(
                    f"aux_down_grad_at_{t}_equip_{self.thermal_unit.name}",
                    self.Q_min,
                    self.Q_max,
                )

    def create_objective_function(self, direction: Literal["maximize", "minimize"] = "maximize"):
        """STEP 2 : Creation of objective function"""
        # Set-up the objective function given by eq. (2) in the documentation.
        # If self.T_stable = 0, we don't need to include automatedContractedReservesUp and automatedContractedReservesDown to the objective function.
        # otherwise we need to include them.
        self.add_objective(
            objective_expr=(
                sum(
                    self.q[t]
                    * (self.parameters.time_step.total_hours())
                    * (self.prices.get_value(t) - self.thermal_unit.variable_cost.get_value(t))
                    - self.turned_on[t] * self.thermal_unit.startup_cost.get_value(t)
                    - self.parameters.manual_unprocured_reserves_penalty
                    * (self.parameters.time_step.total_hours())
                    * (self.contracted_difference_up[t] + self.contracted_difference_down[t])
                    - self.parameters.automated_unprocured_reserves_penalty
                    * (self.parameters.time_step.total_hours())
                    * (self.automated_contracted_difference_up[t] + self.automated_contracted_difference_down[t])
                    for t in self.time_frame
                )
                - self.parameters.automated_unprocured_reserves_penalty
                * (self.parameters.time_step.total_hours())
                * self.automated_unsupplied_reserves
            ),
            direction=direction,
        )

    def create_constraints_and_init_conitions(self):
        """
        STEP 3 : Constraints and initial conditions
        # Constraints and initial conditions are defined based on state and auxiliary variables.
        # Since these variables are not necessarily defined, in the following we go through all
        # 8 possible combinations of state and auxiliary variables and write the corresponding
        # initial conditions and set of constraints all at once.
        #
        # Initial conditions are defined on the previous_time_frame, constraints on the state and
        # control variables are defined on the time_frame.
        """
        self._combination_1()
        self._combination_2()
        self._combination_3()
        self._combination_4()
        self._combination_5()
        self._combination_6()
        self._combination_7()
        self._combination_8()

    def _combination_1(self):
        """Combination 1 : T_stop = self.T_stable = T_start = 0"""

        if self.T_stop == 0 and self.T_start == 0 and self.T_stable == 0:
            # In this case, there are three state variables and two auxiliary variables.
            # We review the initial conditions, then the constraints on the state variables
            # and finally the constraints on the power output.

            # A. INITIAL CONDITIONS

            # See if the program needs to be initialized as DayZero or not
            if len(self.last_power) == 0:
                # Initialization of the program as DayZero and warn the user
                if self.parameters.verbose:
                    cfg.logger.warning("***WARNING***\n The program is initialized for the first time.")
                day_zero = True  # Boolean to keep track of the status
            elif self.last_date != self.parameters.start_date - self.parameters.time_step:
                # last_date doesn't match start_date - time_step (i.e. t_{-1},
                # so we will initialize as DayZero and send a warning message
                if self.parameters.verbose:
                    cfg.logger.warning(
                        f"***WARNING***\n The last_date found in Power of equipement {self.thermal_unit.name} "
                        "does not match the start_date of the current program. \n "
                        "The program will be initialized as DayZero."
                    )
                day_zero = True
            else:
                day_zero = False
                # Setting up the initial conditions of the program
            if day_zero:
                # Remind the user how the program has been initialized
                if self.parameters.verbose:
                    cfg.logger.info(
                        f"Initial conditions of unit {self.thermal_unit.name} have been set as in equation (47)."
                    )

                for t in self.previous_time_frame:
                    # Initial conditions on the power output
                    self.q[t] = 0
                    # Initial conditions on the state variables : the unit is OFF
                    self.OFF[t] = 1
                    self.ON_UP[t] = 0
                    self.ON_DOWN[t] = 0
                    # Initial conditions on the auxiliary variables
                    self.turned_on[t] = 0
                    self.turned_off[t] = 0
            else:
                # Initial condition on the power output
                for t in self.previous_time_frame:
                    self.q[t] = self.last_power.get_value(t)

                # Initial conditions on the state variables
                # Only need to set one value, the mutual exclusion constraint being defined over the
                # whole extended time frame.
                for t in self.previous_time_frame:
                    if self.last_power.get_value(t) > 0:
                        self.OFF[t] = 0
                        self.ON_DOWN[t] = 1
                        self.ON_UP[t] = 1
                    else:
                        self.OFF[t] = 1
                        self.ON_UP[t] = 0
                        self.ON_DOWN[t] = 0

                # Initial conditions on the auxiliary variables
                for t in self.previous_time_frame:
                    # Initialize all the values to 0
                    self.turned_on[t] = 0
                    self.turned_off[t] = 0
                    if not t == self.extended_start_date:
                        # Reconstruct potential switches using the state variables
                        t_prev = t - self.parameters.time_step
                        # See if the unit has been turned off
                        if self.OFF[t] - self.OFF[t_prev] == 1:
                            self.turned_off[t] = 1
                        # Or turned on
                        elif self.OFF[t] - self.OFF[t_prev] == -1:
                            self.turned_on[t] = 1
                        else:
                            self.turned_on[t] = 0
                            self.turned_off[t] = 0

            # B. CONSTRAINTS ON THE AUXILIARY VARIABLES

            # These constraints define the auxiliary variables. In the first case, there are only two
            # of them : turned_on and turned_off.

            # Constraints on the indicator that the unit has started on t
            # Enforces equation (3)
            for t in self.time_frame:
                self.add_constraint(self.turned_on[t] <= 1 - self.OFF[t])
                self.add_constraint(self.turned_on[t] <= self.OFF[t - self.parameters.time_step])
                self.add_constraint(self.turned_on[t] >= self.OFF[t - self.parameters.time_step] - self.OFF[t])

                # Constraints on turned_off
            # STOP is not defined in this case, so we enforce equation (4)
            for t in self.time_frame:
                self.add_constraint(self.turned_off[t] <= 1 - self.OFF[t - self.parameters.time_step])
                self.add_constraint(self.turned_off[t] <= self.OFF[t])
                self.add_constraint(self.turned_off[t] >= self.OFF[t] - self.OFF[t - self.parameters.time_step])

            # C. CONSTRAINTS ON THE STATE VARIABLES

            # Mutual exclusion constraint
            for t in self.time_frame:
                # Defined over the whole time frame
                # Enforces eq. (9)
                self.add_constraint(self.OFF[t] + self.ON_UP[t] + self.ON_DOWN[t] == 1)

            # Transitions:
            # None. All transitions are allowed

            # Mininum time on and minimum time off constraints:
            # if self.T_on >= 2 or self.T_off >= 2, lock the unit in this state.
            if self.T_on >= 2:
                for t in self.time_frame:
                    time_steps = range(1, self.T_on)  # Corresponds to the set {1, ..., self.T_on -1}
                    for s in (
                        time_steps
                    ):  # Add the constraints given by eq. (31), here T_start = 0 so t - s - T_start = t - s
                        t_minus_s = t - s * self.parameters.time_step
                        self.add_constraint(
                            self.turned_on[t_minus_s] <= self.ON_UP[t] + self.ON_DOWN[t],
                            f"minimum_time_ON_{self.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                        )

            if self.T_off >= 2:
                for t in self.time_frame:
                    time_steps = range(1, self.T_off)  # Corresponds to the set {1, ..., self.T_off -1}
                    for (
                        s
                    ) in time_steps:  # Add the constraints given by eq. (32), here T_stop = 0 so t - s - T_stop = t - s
                        t_minus_s = t - s * self.parameters.time_step
                        self.add_constraint(
                            self.turned_off[t_minus_s] <= self.OFF[t],
                            f"minimum_time_OFF_{self.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                        )

            # D. CONSTRAINTS ON THE CONTROL VARIABLE

            # Reserves requirements
            # We are in a case where there is no FLAT state, so manual reserves can be provided
            # as long as the unit is online.

            # Constraints on contractedDifference (eq. (40)) and on automatedContractedDifference (eq. (39))
            self.create_contracted_diff_constraints(
                self.time_frame,
                self.contracted_difference_up,
                self.reserves_up_procured,
                self.reserves_up,
                self.contracted_difference_down,
                self.reserves_down_procured,
                self.reserves_down,
                self.automated_contracted_difference_up,
                self.feasible_automated_reserves_up_procured,
                self.automated_reserves_up,
                self.automated_contracted_difference_down,
                self.feasible_automated_reserves_down_procured,
                self.automated_reserves_down,
            )

            # Upward and downward "fill up" constraints.
            self.create_fill_up_constraints(
                self.time_frame,
                self.q,
                self.reserves_up,
                self.automated_reserves_up,
                self.unprovided_reserves_up,
                self.q_upper,
                self.parameters.epsilon,
                self.reserves_down,
                self.automated_reserves_down,
                self.unprovided_reserves_down,
                self.relaxed_reserves,
                self.q_lower,
            )

            # relaxedReserve disabling condition (eq. (43))
            for t in self.time_frame:
                self.add_constraint(
                    self.relaxed_reserves[t] <= self.q_lower.get_value(t) * (1 - self.ON_UP[t] - self.ON_DOWN[t])
                )

            # impossible commitment and stable reserves constraints (eq. (44))
            for t in self.time_frame:
                self.add_constraint(self.automated_reserves_up[t] <= self.maximum_automated * (1 - self.OFF[t]))
                self.add_constraint(self.automated_reserves_down[t] <= self.maximum_automated * (1 - self.OFF[t]))
                self.add_constraint(self.reserves_up[t] <= self.q_upper.get_value(t) * (1 - self.OFF[t]))
                self.add_constraint(self.reserves_down[t] <= self.q_upper.get_value(t) * (1 - self.OFF[t]))

                # Power output
            for t in self.time_frame:
                self.add_constraint(
                    self.q[t] >= self.q_lower.get_value(t) * (self.ON_UP[t] + self.ON_DOWN[t]),
                    f"lower_bound_of_{self.thermal_unit.name}_at_{t}",
                )  # Lower bound (eq. 33)

                self.add_constraint(
                    self.q[t] <= self.q_upper.get_value(t) * (self.ON_UP[t] + self.ON_DOWN[t]),
                    f"upper_bound_of_{self.thermal_unit.name}_at_{t}",
                )  # Upper bound (eq. 34)

            if self.delta_q > 0:  # Case where the gradient is finite.
                for t in self.gradients_time_frame:  # The gradients are defined only up to T-1.
                    t_next = t + self.parameters.time_step  # Get the next time step

                    # Upward constrained gradient (eq. 35):
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        <= self.delta_q * self.ON_UP[t] + self.delta_q_unconstrained * self.turned_on[t_next],
                        f"upward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Upward gradient

                    # Downward constrained gradient (eq. 37) :
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        >= -self.delta_q * self.ON_DOWN[t] - self.delta_q_unconstrained * self.turned_off[t_next],
                        f"downward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Downward gradient

            elif self.delta_q == 0:  # Case where the gradient is 'infinite'
                for t in self.gradients_time_frame:
                    t_next = t + self.parameters.time_step  # Get the next time step

                    # Upward unconstrained gradient (eq. 36)
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        <= self.delta_q_unconstrained * self.ON_UP[t]
                        + self.delta_q_unconstrained * self.turned_on[t_next]
                    )  # Upward gradient

                    # Downward unconstrained gradient (eq. 38)
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        >= -self.delta_q_unconstrained * self.ON_DOWN[t]
                        - self.delta_q_unconstrained * self.turned_off[t_next]
                    )  # Downward gradient
            else:  # Raise an error since no gradients have been detected.
                cfg.logger.warning(
                    f"*** WARNING ***\n No gradients have been defined for equipment {self.thermal_unit.name}. \n "
                    "Please check the value of `maximum_gradient`."
                )
                raise ValueError("Missing gradients for thermic units.")

            self.create_daily_energy_constraint(self.thermal_unit, self.time_frame, self.parameters.time_step, self.q)

    def _combination_2(self):
        """Combination 2 : T_stop >= 1, self.T_stable = T_start = 0"""

        if self.T_stop >= 1 and self.T_start == 0 and self.T_stable == 0:
            # In this case, there are four state variables and three auxiliary variables.
            # We review the initial conditions, then the constraints on the state variables
            # and finally the constraints on the power output.

            # PREAMBLE
            # Define the down_to_stop auxiliary, which is used only in this combination and in combination 7.
            down_to_stop = {}
            for t in self.time_frame:
                down_to_stop[t] = self.add_continuous_variable(
                    f"down_to_stop_equip_{self.thermal_unit.name}_at_{t}", 0, 1
                )

            # A. INITIAL CONDITIONS

            # See if the program needs to be initialized as DayZero or not
            if len(self.last_power) == 0:
                # Initialization of the program as DayZero and warn the user
                if self.parameters.verbose:
                    cfg.logger.warning("***WARNING***\n The program is initialized for the first time.")
                day_zero = True  # Boolean to keep track of the status
            elif self.last_date != self.parameters.start_date - self.parameters.time_step:
                # last_date doesn't match start_date - time_step (i.e. t_{-1}, so we will initialize as DayZero and send a warning message
                if self.parameters.verbose:
                    cfg.logger.warning(
                        f"***WARNING***\n The last_date found in Power of equipement {self.thermal_unit.name} "
                        "does not match the start_date of the current program. \n "
                        "The program will be initialized as DayZero."
                    )
                day_zero = True
            else:
                day_zero = False
                # Setting up the initial conditions of the program
            if day_zero:
                # Remind the user how the program has been initialized
                if self.parameters.verbose:
                    cfg.logger.info(
                        f"Initial conditions of unit {self.thermal_unit.name} have been set as in equation (47)."
                    )

                for t in self.previous_time_frame:
                    # Initial conditions on the power output
                    self.q[t] = 0
                    # Initial conditions on the state variables : the unit is OFF
                    self.OFF[t] = 1
                    self.ON_UP[t] = 0
                    self.ON_DOWN[t] = 0
                    self.STOP[t] = 0
                    # Initial conditions on the auxiliary variables
                    self.turned_on[t] = 0
                    self.turned_off[t] = 0
                    down_to_stop[t] = 0
            else:
                # Initial condition on the power output
                for t in self.previous_time_frame:
                    self.q[t] = self.last_power.get_value(t)

                # Initial conditions on the state variables
                # Only need to set one value, the mutual exclusion constraint being defined over the
                # whole extended time frame.
                for t in self.previous_time_frame:
                    # There are now three cases : either q_t >= q_min, 0 < q_t < q_min or q_t = 0
                    if self.last_power.get_value(t) >= self.thermal_unit.minimum_power.get_value(t):
                        self.OFF[t] = 0
                        self.STOP[t] = 0
                        self.ON_DOWN[t] = 1
                        self.ON_UP[t] = (
                            1
                            # Set both ON states to 1 in order to allow the unit to do whatever it wants as there is no
                        )
                        # stable constraint at this point.
                    elif self.last_power.get_value(t) > 0:
                        self.STOP[t] = 1
                        self.OFF[t] = 0
                        self.ON_UP[t] = 0
                        self.ON_DOWN[t] = 0
                    else:
                        self.STOP[t] = 0
                        self.OFF[t] = 1
                        self.ON_UP[t] = 0
                        self.ON_DOWN[t] = 0

                # Initial conditions on the auxiliary variables
                for t in self.previous_time_frame:
                    # Initialize all the values to 0
                    self.turned_on[t] = 0
                    self.turned_off[t] = 0
                    down_to_stop[t] = 0

                    if not t == self.extended_start_date:
                        # Reconstruct potential switches using the state variables
                        t_prev = t - self.parameters.time_step
                        # See if the unit has been turned off
                        if self.STOP[t] - self.STOP[t_prev] == 1:
                            self.turned_off[t] = 1
                        # Or turned on
                        elif self.OFF[t] - self.OFF[t_prev] == -1:
                            self.turned_on[t] = 1
                        # Reconstruct down_to_stop
                        elif self.STOP[t] - self.ON_DOWN[t_prev] == 0:
                            down_to_stop[t] = 1

            # B. CONSTRAINTS ON THE AUXILIARY VARIABLES

            # These constraints define the auxiliary variables.

            # Constraints on the indicator that the unit has started on t
            # Enforces eq. (3)
            for t in self.time_frame:
                self.add_constraint(self.turned_on[t] <= 1 - self.OFF[t])
                self.add_constraint(self.turned_on[t] <= self.OFF[t - self.parameters.time_step])
                self.add_constraint(
                    self.turned_on[t] >= self.OFF[t - self.parameters.time_step] - self.OFF[t],
                    f"constraints_defining_turned_on_{t}",
                )

            # Constraints on turned_off
            # Enforces eq. (5) since the STOP state is defined in this case.
            for t in self.time_frame:
                self.add_constraint(self.turned_off[t] <= 1 - self.STOP[t - self.parameters.time_step])
                self.add_constraint(self.turned_off[t] <= self.STOP[t])
                self.add_constraint(
                    self.turned_off[t] >= self.STOP[t] - self.STOP[t - self.parameters.time_step],
                    f"constraints_defining_turned_off_{t}",
                )

            # Constraints on down_to_stop (eq. (20))
            for t in self.time_frame:
                t_minus_one = t - self.parameters.time_step
                self.add_constraint(down_to_stop[t] <= self.STOP[t])
                self.add_constraint(down_to_stop[t] <= self.ON_DOWN[t_minus_one])
                self.add_constraint(down_to_stop[t] >= self.STOP[t] + self.ON_DOWN[t_minus_one] - 1)

            # C. CONSTRAINTS ON THE STATE VARIABLES

            # Mutual exclusion constraint
            for t in self.time_frame:
                # Defined over the whole time frame
                # Enforces eq. (9).
                self.add_constraint(
                    self.OFF[t] + self.ON_UP[t] + self.ON_DOWN[t] + self.STOP[t] == 1,
                    f"mutual_exclusion_at_{t}",
                )

            # Transitions:
            # Transitions from OFF to STOP and STOP to ON_DOWN and ON_UP are forbidden
            # Direct transitions from ON_UP and ON_DOWN to OFF are forbidden.
            for t in self.time_frame:
                t_minus_one = t - self.parameters.time_step
                self.add_constraint(self.STOP[t_minus_one] + self.ON_UP[t] <= 1)  # Eq. (13)
                self.add_constraint(self.STOP[t_minus_one] + self.ON_DOWN[t] <= 1)  # Eq. (13)
                self.add_constraint(self.OFF[t_minus_one] + self.STOP[t] <= 1)  # Eq. (12)
                self.add_constraint(self.ON_UP[t_minus_one] + self.OFF[t] <= 1)  # Eq. (18)
                self.add_constraint(
                    self.ON_DOWN[t_minus_one] + self.OFF[t] <= 1,
                    f"transitions_constraints_at_{t}",
                )  # Eq. (18)

            # Eviction constraint : force the unit to remain only T_stop time steps in the shutdown phase.
            for t in self.time_frame:
                t_minus_T_stop = t - self.T_stop * self.parameters.time_step
                # Implement equation (19)
                self.add_constraint(
                    self.turned_off[t_minus_T_stop] + self.STOP[t] <= 1,
                    f"eviction_constraint_at_{t}",
                )

            # Mininum time on, minimum time off, minimum time in the STOP state constraints:
            # if self.T_on >= 2, self.T_off >= 2 or T_stop >= 2, lock the unit in this state.
            if self.T_on >= 2:
                for t in self.time_frame:
                    time_steps = range(1, self.T_on)  # Corresponds to the set {1,...,self.T_on - 1}
                    for s in time_steps:
                        # Implement eq. (31), with T_start = 0
                        t_minus_s = t - s * self.parameters.time_step
                        self.add_constraint(
                            self.turned_on[t_minus_s] <= self.ON_UP[t] + self.ON_DOWN[t],
                            f"minimum_time_ON_{self.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                        )

            if self.T_off >= 2:
                for t in self.time_frame:
                    time_steps = range(1, self.T_off)  # Corresponds to the set {1,...,self.T_off - 1}
                    for s in time_steps:
                        # Implement eq. (32) with T_stop > 0
                        t_minus_s_minus_T_stop = (
                            t - s * self.parameters.time_step - self.T_stop * self.parameters.time_step
                        )  # Shift the index because the OFF is formally
                        # considered when entering the STOP state.
                        self.add_constraint(
                            self.turned_off[t_minus_s_minus_T_stop] <= self.OFF[t],
                            f"minimum_time_OFF_{self.thermal_unit.name}_at_{t_minus_s_minus_T_stop}_for_{t}",
                        )

            if self.T_stop >= 2:
                for t in self.time_frame:
                    for s in self.stop_time_steps:
                        # Implement eq. (24)
                        t_minus_s = t - s * self.parameters.time_step
                        self.add_constraint(
                            self.turned_off[t_minus_s] <= self.STOP[t],
                            f"shutdown_ramp_of_{self.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                        )

            # D. CONSTRAINTS ON THE CONTROL VARIABLE

            # Shutdown gradient
            q_min = self.thermal_unit.minimum_power.max()  # Get the minimum_power without the reserve requirements
            q_step = q_min / self.T_stop

            # Reserves requirements
            # We are in a case where there is no FLAT state, so manual reserves can be provided
            # as long as the unit is online.

            # Constraints on contractedDifference (eq. (40)) and on automatedContractedDifference (eq. (39))
            self.create_contracted_diff_constraints(
                self.time_frame,
                self.contracted_difference_up,
                self.reserves_up_procured,
                self.reserves_up,
                self.contracted_difference_down,
                self.reserves_down_procured,
                self.reserves_down,
                self.automated_contracted_difference_up,
                self.feasible_automated_reserves_up_procured,
                self.automated_reserves_up,
                self.automated_contracted_difference_down,
                self.feasible_automated_reserves_down_procured,
                self.automated_reserves_down,
            )

            # Upward and downward "fill up" constraints.
            self.create_fill_up_constraints(
                self.time_frame,
                self.q,
                self.reserves_up,
                self.automated_reserves_up,
                self.unprovided_reserves_up,
                self.q_upper,
                self.parameters.epsilon,
                self.reserves_down,
                self.automated_reserves_down,
                self.unprovided_reserves_down,
                self.relaxed_reserves,
                self.q_lower,
            )

            # relaxedReserve disabling condition (eq. (43))
            for t in self.time_frame:
                self.add_constraint(
                    self.relaxed_reserves[t] <= self.q_lower.get_value(t) * (1 - self.ON_UP[t] - self.ON_DOWN[t])
                )

            # impossible commitment and stable reserves constraints (eq. (44))
            for t in self.time_frame:
                self.add_constraint(
                    self.automated_reserves_up[t] <= self.maximum_automated * (1 - self.OFF[t] - self.STOP[t])
                )
                self.add_constraint(
                    self.automated_reserves_down[t] <= self.maximum_automated * (1 - self.OFF[t] - self.STOP[t])
                )
                self.add_constraint(self.reserves_up[t] <= self.q_upper.get_value(t) * (1 - self.OFF[t] - self.STOP[t]))
                self.add_constraint(
                    self.reserves_down[t] <= self.q_upper.get_value(t) * (1 - self.OFF[t] - self.STOP[t])
                )

            # Power output
            for t in self.time_frame:
                self.add_constraint(
                    self.q[t]
                    >= self.q_lower.get_value(t) * (self.ON_UP[t] + self.ON_DOWN[t])
                    + self.turned_off[t] * (q_min - q_step),
                    f"lower_bound_of_{self.thermal_unit.name}_at_{t}",
                )  # Lower bound (eq. 33)
                self.add_constraint(
                    self.q[t]
                    <= self.q_upper.get_value(t) * (self.ON_UP[t] + self.ON_DOWN[t])
                    + self.STOP[t] * q_min
                    - self.turned_off[t] * q_step,
                    f"upper_bound_of_{self.thermal_unit.name}_at_{t}",
                )  # Upper bound   (eq.34)

            if self.delta_q > 0:  # Case where the gradient is finite.
                for t in self.gradients_time_frame:  # The gradients are defined only up to T-1.
                    t_next = t + self.parameters.time_step  # Get the next time step
                    # Constrained upward gradient (eq. (35))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        <= (
                            self.delta_q * self.ON_UP[t]
                            - self.turned_off[t_next] * q_step
                            - self.STOP[t] * q_step
                            + self.delta_q_unconstrained * self.turned_on[t_next]
                        ),
                        f"upward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Upward gradient

                    # Constrained downward gradient (eq. (37))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        >= (
                            -self.delta_q * self.ON_DOWN[t]
                            - self.turned_off[t_next] * q_step
                            - self.STOP[t] * q_step
                            + down_to_stop[t_next] * self.delta_q
                        ),
                        f"downward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Downward gradient

            elif self.delta_q == 0:  # Case where the gradient is 'infinite'
                for t in self.gradients_time_frame:
                    t_next = t + self.parameters.time_step  # Get the next time step
                    # Unconstrained upward gradient (eq. (36))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        <= (
                            self.delta_q_unconstrained * self.ON_UP[t]
                            - self.turned_off[t_next] * q_step
                            - self.STOP[t] * q_step
                            + self.delta_q_unconstrained * self.turned_on[t_next]
                        ),
                        f"upward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Upward gradient

                    # Unconstrained downward gradient (eq. (38))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        >= (
                            -self.delta_q_unconstrained * self.ON_DOWN[t]
                            - self.turned_off[t_next] * q_step
                            - self.STOP[t] * q_step
                            + down_to_stop[t_next] * self.delta_q_unconstrained
                        ),
                        f"downward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Downward gradient

            else:  # Raise an error since no gradients have been detected.
                cfg.logger.error(
                    f"*** WARNING ***\n No gradients have been defined for equipment {self.thermal_unit.name}. \n "
                    "Please check the value of `maximum_gradient`."
                )
                raise ValueError("Missing gradients for thermic units.")

            self.create_daily_energy_constraint(self.thermal_unit, self.time_frame, self.parameters.time_step, self.q)

    def _combination_3(self):
        """Combination 3 : T_stop = 0, self.T_stable >= 1 T_start = 0"""

        if self.T_stop == 0 and self.T_start == 0 and self.T_stable >= 1:
            # In this case, there are four state variables and the following auxiliary variables :
            #     - turned_on[t] and turned_off[t], indicating whether the unit has been turned on or off
            #     - stable[t], indicating whether the unit entered the stable state
            #     - U[t] and D[t], implemented in two stages with tilde_D[t], tilde_D[t] as the first stage
            #     - entered_up[t] and entered_down[t] indicating that the unit entered the UP or down STATE
            #
            # We review the initial conditions, then the constraints on the state variables
            # and finally the constraints on the power output.

            # A. INITIAL CONDITIONS

            # Define the start_date - 2 time steps.
            start_date_minus_two = self.parameters.start_date - 2 * self.parameters.time_step

            # See if the program needs to be initialized as DayZero or not
            if len(self.last_power) == 0:
                # Initialization of the program as DayZero and warn the user
                if self.parameters.verbose:
                    cfg.logger.warning("***WARNING***\n The program is initialized for the first time.")
                day_zero = True  # Boolean to keep track of the status
            elif self.last_date != self.parameters.start_date - self.parameters.time_step:
                # last_date doesn't match start_date - time_step (i.e. t_{-1}, so we will initialize as DayZero and send a warning message
                if self.parameters.verbose:
                    cfg.logger.warning(
                        f"***WARNING***\n The last_date found in Power of equipement {self.thermal_unit.name} "
                        "does not match the start_date of the current program. \n "
                        "The program will be initialized as DayZero."
                    )
                day_zero = True
            else:
                day_zero = False
                # Setting up the initial conditions of the program
            if day_zero:
                # Remind the user how the program has been initialized
                if self.parameters.verbose:
                    cfg.logger.info(
                        f"Initial conditions of unit {self.thermal_unit.name} have been set as in equation (47)."
                    )

                for t in self.previous_time_frame:
                    # Initial conditions on the power output
                    self.q[t] = 0
                    # Initial conditions on the state variables : the unit is OFF
                    self.OFF[t] = 1
                    if not t == self.start_date_minus_one:
                        self.ON_UP[t] = 0
                        self.ON_DOWN[t] = 0
                        self.ON_FLAT[t] = 0
                        # Initial conditions on the auxiliary variables defined over time_frame_union_minus_one
                        self.stable[t] = 0
                        self.entered_up[t] = 0
                        self.entered_down[t] = 0

                    # Initial conditions on the remaining auxiliary variables
                    self.turned_on[t] = 0
                    self.turned_off[t] = 0
            else:
                # Setting up the initial conditions will be a bit more complex. We consecutively do the following:
                #    - Set the inital conditions on the power output
                #    - See wether the unit is ON or OFF
                #    - Initialize the auxiliaries turned_up and turned_down accordingly
                #    - For the steps where the unit is ON:
                #         - See whether the unit was UP, DOWN or FLAT
                #         - Initialize the auxiliary variables accordingly

                # Initial condition on the power output
                for t in self.previous_time_frame:
                    self.q[t] = self.last_power.get_value(t)

                # Initial conditions on the state variables OFF/ON
                for t in self.previous_time_frame:
                    if self.last_power.get_value(t) > 0:
                        self.OFF[t] = 0  # Only the OFF variable is initialized. ON_FLAT, ON_DOWN and ON_UP will be
                        # initialized afterwards.
                    else:
                        self.OFF[t] = 1
                        if not t == self.start_date_minus_one:
                            self.ON_UP[t] = 0
                            self.ON_DOWN[t] = 0
                            self.ON_FLAT[t] = 0

                # Initial conditions on the auxiliary variables turned_on and turned_off
                for t in self.previous_time_frame:
                    # Initialize all the values to 0
                    self.turned_on[t] = 0
                    self.turned_off[t] = 0
                    if not t == self.extended_start_date:
                        # Reconstruct potential switches using the state variables
                        t_prev = t - self.parameters.time_step
                        # See if the unit has been turned off
                        if self.OFF[t] - self.OFF[t_prev] == 1:
                            self.turned_off[t] = 1
                        # Or turned on
                        elif self.OFF[t] - self.OFF[t_prev] == -1:
                            self.turned_on[t] = 1

                # Reconstruct the values of UP, DOWN and FLAT and their associated
                # auxiliary variables
                for t in self.previous_time_frame[
                    :-1
                ]:  # Loop excluding last date because we are reconstructing the values of the
                    # ON variables using  variations between q[t] and q[t-1].

                    t_prev = t - self.parameters.time_step
                    if self.OFF[t_prev] == 0:
                        # See if the power output was stable, increasing or decreasing:
                        if self.q[t] > self.q[t_prev]:  # Recall that here t_prev is earlier than t.
                            self.ON_UP[t_prev] = 1
                            self.ON_DOWN[t_prev] = 0
                            self.ON_FLAT[t_prev] = 0
                        elif self.q[t] < self.q[t_prev]:
                            self.ON_UP[t_prev] = 0
                            self.ON_DOWN[t_prev] = 1
                            self.ON_FLAT[t_prev] = 0
                        elif self.q[t] == self.q[t_prev]:
                            self.ON_UP[t_prev] = 0
                            self.ON_DOWN[t_prev] = 0
                            self.ON_FLAT[t_prev] = 1

                # Initialize the auxiliary variables
                for t in self.previous_time_frame[
                    1:
                ]:  # Loop excluding start_date_minus_one, which is the first element in the previous_time_frame list.
                    # Default value set to 0
                    self.stable[t] = 0
                    self.entered_up[t] = 0
                    self.entered_down[t] = 0

                    if (not t == self.extended_start_date) and (not self.OFF[t] == 1):
                        t_prev = t - self.parameters.time_step

                        # See if the unit entered the FLAT state
                        if self.ON_FLAT[t] - self.ON_FLAT[t_prev] == 1:
                            self.stable[t] = 1
                        # or the UP state
                        if self.ON_UP[t] - self.ON_UP[t_prev] == 1:
                            self.entered_up[t] = 1
                        # or the DOWN state
                        if self.ON_DOWN[t] - self.ON_DOWN[t_prev] == 1:
                            self.entered_down[t] = 1

                            # Initialize the gradient auxiliaries. This is only required for the last time step of the
            # previous_time_frame. Only ON_UP[start_date_minus_one] and ON_DOWN[start_date_minus_one] are decision variables
            # in the expressions below.
            self.U[self.start_date_minus_one] = (
                self.ON_UP[self.start_date_minus_one]
                * self.ON_UP[start_date_minus_two]
                * (self.q[self.start_date_minus_one] - self.q[start_date_minus_two])
            )
            self.D[self.start_date_minus_one] = (
                self.ON_DOWN[self.start_date_minus_one]
                * self.ON_DOWN[start_date_minus_two]
                * (self.q[self.start_date_minus_one] - self.q[start_date_minus_two])
            )

            # B. CONSTRAINTS ON THE AUXILIARY VARIABLES

            # These constraints define the auxiliary variables. In the first case, there are only two
            # of them : turned_on and turned_off.

            # Constraints on the indicator that the unit has started on t (turned_on, sec. 6.1.1)
            # Enforces eq. (3)
            for t in self.time_frame:
                self.add_constraint(self.turned_on[t] <= 1 - self.OFF[t])
                self.add_constraint(self.turned_on[t] <= self.OFF[t - self.parameters.time_step])
                self.add_constraint(self.turned_on[t] >= self.OFF[t - self.parameters.time_step] - self.OFF[t])

                # Constraints on turned_off
            # Enforces eq. (4) as there is no STOP state in this case.
            for t in self.time_frame:
                self.add_constraint(self.turned_off[t] <= 1 - self.OFF[t - self.parameters.time_step])
                self.add_constraint(self.turned_off[t] <= self.OFF[t])
                self.add_constraint(self.turned_off[t] >= self.OFF[t] - self.OFF[t - self.parameters.time_step])

            # stable auxiliary variable
            # Enforces eq. (6)
            for t in self.time_frame_union_minus_one:
                self.add_constraint(self.stable[t] <= 1 - self.ON_FLAT[t - self.parameters.time_step])
                self.add_constraint(self.stable[t] <= self.ON_FLAT[t])
                self.add_constraint(self.stable[t] >= self.ON_FLAT[t] - self.ON_FLAT[t - self.parameters.time_step])

            # entered_up and entered_down auxiliaries
            for t in self.time_frame_union_minus_one:
                # entered_up (eq. (7))
                self.add_constraint(self.entered_up[t] <= 1 - self.ON_UP[t - self.parameters.time_step])
                self.add_constraint(self.entered_up[t] <= self.ON_UP[t])
                self.add_constraint(self.entered_up[t] >= self.ON_UP[t] - self.ON_UP[t - self.parameters.time_step])
                # entered_down (eq. (8))
                self.add_constraint(self.entered_down[t] <= 1 - self.ON_DOWN[t - self.parameters.time_step])
                self.add_constraint(self.entered_down[t] <= self.ON_DOWN[t])
                self.add_constraint(
                    self.entered_down[t] >= self.ON_DOWN[t] - self.ON_DOWN[t - self.parameters.time_step]
                )

            # UP and DOWN auxiliary variables for the gradient.
            # These auxiliary variables model the fact that if the unit is increasing (decreasing) its
            # power output twice in a row, then the second time the gradient is locked.
            # In practice, these variables are defined in two stages

            # First stage : tilde_U and tilde_D
            for t in self.time_frame:  # Loop in all the time_frame but start_date.
                t_minus_one = t - self.parameters.time_step
                # tilde_U (eq. (28))
                self.add_constraint(self.tilde_U[t] <= self.Q_max * self.ON_UP[t_minus_one])
                self.add_constraint(self.tilde_U[t] >= self.Q_min * self.ON_UP[t_minus_one])
                self.add_constraint(
                    self.tilde_U[t] <= self.q[t] - self.q[t_minus_one] - self.Q_min * (1 - self.ON_UP[t_minus_one])
                )
                self.add_constraint(
                    self.tilde_U[t] >= self.q[t] - self.q[t_minus_one] - self.Q_max * (1 - self.ON_UP[t_minus_one]),
                    f"VALUE_of_tilde_UP_at_{t}",
                )

                # tilde_D (eq. (30))
                self.add_constraint(self.tilde_D[t] <= self.Q_max * self.ON_DOWN[t_minus_one])
                self.add_constraint(self.tilde_D[t] >= self.Q_min * self.ON_DOWN[t_minus_one])
                self.add_constraint(
                    self.tilde_D[t] <= self.q[t] - self.q[t_minus_one] - self.Q_min * (1 - self.ON_DOWN[t_minus_one])
                )
                self.add_constraint(
                    self.tilde_D[t] >= self.q[t] - self.q[t_minus_one] - self.Q_max * (1 - self.ON_DOWN[t_minus_one]),
                    f"VALUE_of_tilde_DOWN_at_{t}",
                )

            # Second stage : U and D
            # These variables wil be added to the gradient constraints.
            for t in self.time_frame:
                # U (eq. (27))
                self.add_constraint(self.U[t] <= self.Q_max * self.ON_UP[t])
                self.add_constraint(self.U[t] >= self.Q_min * self.ON_UP[t])
                self.add_constraint(self.U[t] <= self.tilde_U[t] - self.Q_min * (1 - self.ON_UP[t]))
                self.add_constraint(
                    self.U[t] >= self.tilde_U[t] - self.Q_max * (1 - self.ON_UP[t]),
                    f"VALUE_of_UP_at_{t}",
                )
                # D (eq. (29))
                self.add_constraint(self.D[t] <= self.Q_max * self.ON_DOWN[t])
                self.add_constraint(self.D[t] >= self.Q_min * self.ON_DOWN[t])
                self.add_constraint(self.D[t] <= self.tilde_D[t] - self.Q_min * (1 - self.ON_DOWN[t]))
                self.add_constraint(
                    self.D[t] >= self.tilde_D[t] - self.Q_max * (1 - self.ON_DOWN[t]),
                    f"VALUE_of_DOWN_at_{t}",
                )

                # C. CONSTRAINTS ON THE STATE VARIABLES

            # Mutual exclusion constraint
            for t in self.time_frame_union_minus_one:
                # Defined over the whole time frame.
                # Enforces eq. (9)
                self.add_constraint(
                    self.OFF[t] + self.ON_UP[t] + self.ON_DOWN[t] + self.ON_FLAT[t] == 1,
                    f"mutual_exclusion_at_{t}",
                )

            # Transitions:
            # UP-DOWN and DOWN-UP transitions are forbidden.
            for t in self.time_frame_union_minus_one:
                t_minus_one = t - self.parameters.time_step
                # Implement eq. (25).
                self.add_constraint(self.ON_UP[t_minus_one] + self.ON_DOWN[t] <= 1)
                self.add_constraint(
                    self.ON_DOWN[t_minus_one] + self.ON_UP[t] <= 1,
                    f"transitions_constraints_at_{t}",
                )

            # Mininum time on and minimum time off constraints:
            # if self.T_on >= 2 or self.T_off >= 2 or self.T_stable >= 2, lock the unit in this state.
            if self.T_on >= 2:
                for t in self.time_frame_union_minus_one:
                    time_steps = range(1, self.T_on)  # Corresponds to the set {1,..., self.T_on - 1}
                    for s in time_steps:
                        # Enforces eq. (31), with T_start = 0
                        t_minus_s = t - s * self.parameters.time_step
                        self.add_constraint(
                            self.turned_on[t_minus_s] <= self.ON_UP[t] + self.ON_DOWN[t] + self.ON_FLAT[t],
                            f"minimum_time_ON_{self.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                        )
            if self.T_off >= 2:
                for t in self.time_frame:
                    time_steps = range(1, self.T_off)  # Corresponds to the set {1,..., self.T_off - 1}
                    for s in time_steps:
                        # Enforces eq. (32) with T_stop = 0
                        t_minus_s = t - s * self.parameters.time_step
                        self.add_constraint(
                            self.turned_off[t_minus_s] <= self.OFF[t],
                            f"minimum_time_OFF_{self.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                        )
            if self.T_stable >= 2:
                for t in self.time_frame_union_minus_one:
                    time_steps = range(1, self.T_stable - 1)  # Corresponds to the set {1,..., self.T_stable - 2}
                    for s in time_steps:
                        # Enforces eq. (26)
                        t_minus_s = t - s * self.parameters.time_step
                        self.add_constraint(
                            self.stable[t_minus_s] <= self.ON_FLAT[t],
                            f"minimum_time_STABLE_{self.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                        )

            # D. CONSTRAINTS ON THE CONTROL VARIABLE

            # Reserves requirements
            # We are in a case where there is a FLAT state, so manual reserves can only be provided
            # when the unit is in the FLAT state.

            # Constraints on contractedDifference (eq. (40)) and on automatedContractedDifference (eq. (39))
            self.create_contracted_diff_constraints(
                self.time_frame,
                self.contracted_difference_up,
                self.reserves_up_procured,
                self.reserves_up,
                self.contracted_difference_down,
                self.reserves_down_procured,
                self.reserves_down,
                self.automated_contracted_difference_up,
                self.feasible_automated_reserves_up_procured,
                self.automated_reserves_up,
                self.automated_contracted_difference_down,
                self.feasible_automated_reserves_down_procured,
                self.automated_reserves_down,
            )

            # Upward and downward "fill up" constraints.
            self.create_fill_up_constraints(
                self.time_frame,
                self.q,
                self.reserves_up,
                self.automated_reserves_up,
                self.unprovided_reserves_up,
                self.q_upper,
                self.parameters.epsilon,
                self.reserves_down,
                self.automated_reserves_down,
                self.unprovided_reserves_down,
                self.relaxed_reserves,
                self.q_lower,
            )

            # relaxedReserve disabling condition (eq. (43))
            for t in self.time_frame:
                self.add_constraint(
                    self.relaxed_reserves[t]
                    <= self.q_lower.get_value(t) * (1 - self.ON_UP[t] - self.ON_FLAT[t] - self.ON_DOWN[t])
                )

            # impossible commitment and stable reserves constraints (eqs. (44) and (45))
            for t in self.time_frame:
                self.add_constraint(self.automated_reserves_up[t] <= self.maximum_automated * (1 - self.OFF[t]))
                self.add_constraint(self.automated_reserves_down[t] <= self.maximum_automated * (1 - self.OFF[t]))
                self.add_constraint(
                    self.reserves_up[t]
                    <= self.q_upper.get_value(t) * (1 - self.ON_UP[t] - self.ON_DOWN[t] - self.OFF[t])
                )  # for compacity, implements both eq (44) and (45)
                self.add_constraint(
                    self.reserves_down[t]
                    <= self.q_upper.get_value(t) * (1 - self.ON_UP[t] - self.ON_DOWN[t] - self.OFF[t])
                )

            # Power output
            for t in self.time_frame:
                self.add_constraint(
                    self.q[t] >= self.q_lower.get_value(t) * (self.ON_UP[t] + self.ON_DOWN[t] + self.ON_FLAT[t]),
                    f"lower_bound_of_{self.thermal_unit.name}_at_{t}",
                )  # Lower bound (eq. (33))

                self.add_constraint(
                    self.q[t] <= self.q_upper.get_value(t) * (self.ON_UP[t] + self.ON_DOWN[t] + self.ON_FLAT[t]),
                    f"upper_bound_of_{self.thermal_unit.name}_at_{t}",
                )  # Upper bound (eq. (34))

            if self.delta_q > 0:  # Case where the gradient is finite.
                for t in self.gradients_time_frame:  # The gradients are defined only up to T-1.
                    t_next = t + self.parameters.time_step  # Get the next time step

                    # Upward constrained gradient (eq. (35))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        <= self.delta_q * self.entered_up[t]
                        + self.U[t]
                        + self.D[t]
                        + self.delta_q_unconstrained * self.turned_on[t_next],
                        f"upward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Upward gradient

                    # Downard constrained gradient (eq. (37))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        >= -self.delta_q * self.entered_down[t]
                        + self.U[t]
                        + self.D[t]
                        - self.delta_q_unconstrained * self.turned_off[t_next],
                        f"downward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Downward gradient

            elif self.delta_q == 0:  # Case where the gradient is 'infinite'
                for t in self.gradients_time_frame:
                    t_next = t + self.parameters.time_step  # Get the next time step

                    # Upward unconstrained gradient (eq. (36))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        <= self.delta_q_unconstrained * self.entered_up[t]
                        + self.U[t]
                        + self.D[t]
                        + self.delta_q_unconstrained * self.turned_on[t_next],
                        f"unconstrained_upward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Upward gradient

                    # Downward unconstrained gradient (eq. (38))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        >= -self.delta_q_unconstrained * self.entered_down[t]
                        + self.U[t]
                        + self.D[t]
                        - self.delta_q_unconstrained * self.turned_off[t_next],
                        f"unconstrained_downward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Downward gradient

            else:  # Raise an error since no gradients have been detected.
                cfg.logger.error(
                    f"*** WARNING ***\n No gradients have been defined for equipment {self.thermal_unit.name}. \n "
                    "Please check the value of `maximum_gradient`."
                )
                raise ValueError("Missing gradients for thermic units.")

            self.create_daily_energy_constraint(self.thermal_unit, self.time_frame, self.parameters.time_step, self.q)

    def _combination_4(self):
        """Combination 4 : T_start >= 1, self.T_stable = T_stop = 0"""

        if self.T_start >= 1 and self.T_stop == 0 and self.T_stable == 0:
            # In this case, there are four state variables and two auxiliary variables.
            # We review the initial conditions, then the constraints on the state variables
            # and finally the constraints on the power output.

            # A. INITIAL CONDITIONS

            # See if the program needs to be initialized as DayZero or not
            if len(self.last_power) == 0:
                # Initialization of the program as DayZero and warn the user
                if self.parameters.verbose:
                    cfg.logger.warning("***WARNING***\n The program is initialized for the first time.")
                day_zero = True  # Boolean to keep track of the status
            elif self.last_date != self.parameters.start_date - self.parameters.time_step:
                # last_date doesn't match start_date - time_step (i.e. t_{-1}, so we will initialize as DayZero and send a warning message
                if self.parameters.verbose:
                    cfg.logger.warning(
                        f"***WARNING***\n The last_date found in Power of equipement {self.thermal_unit.name} "
                        "does not match the start_date of the current program. \n "
                        "The program will be initialized as DayZero."
                    )
                day_zero = True
            else:
                day_zero = False
                # Setting up the initial conditions of the program
            if day_zero:
                # Remind the user how the program has been initialized
                if self.parameters.verbose:
                    cfg.logger.info(
                        f"Initial conditions of unit {self.thermal_unit.name} have been set as in equation (47)."
                    )

                for t in self.previous_time_frame:
                    # Initial conditions on the power output
                    self.q[t] = 0
                    # Initial conditions on the state variables : the unit is OFF
                    self.OFF[t] = 1
                    self.ON_UP[t] = 0
                    self.ON_DOWN[t] = 0
                    self.START[t] = 0
                    # Initial conditions on the auxiliary variables
                    self.turned_on[t] = 0
                    self.turned_off[t] = 0
            else:
                # Initial condition on the power output
                for t in self.previous_time_frame:
                    self.q[t] = self.last_power.get_value(t)

                # Initial conditions on the state variables
                for t in self.previous_time_frame:
                    # There are now three cases : either q_t >= q_min, 0 < q_t < q_min or q_t = 0
                    if self.last_power.get_value(t) >= self.thermal_unit.minimum_power.get_value(t):
                        self.OFF[t] = 0
                        self.START[t] = 0
                        self.ON_DOWN[t] = 1
                        self.ON_UP[t] = (
                            1
                            # Set both ON states to 1 in order to allow the unit to do whatever it wants as there is no
                        )
                        # stable constraint at this point.
                    elif self.last_power.get_value(t) > 0:
                        self.START[t] = 1
                        self.OFF[t] = 0
                        self.ON_UP[t] = 0
                        self.ON_DOWN[t] = 0
                    else:
                        self.START[t] = 0
                        self.OFF[t] = 1
                        self.ON_UP[t] = 0
                        self.ON_DOWN[t] = 0

                # Initial conditions on the auxiliary variables
                for t in self.previous_time_frame:
                    # Initialize all the values to 0
                    self.turned_on[t] = 0
                    self.turned_off[t] = 0
                    if not t == self.extended_start_date:
                        # Reconstruct potential switches using the state variables
                        t_prev = t - self.parameters.time_step
                        # See if the unit has been turned off
                        if self.OFF[t] - self.OFF[t_prev] == 1:
                            self.turned_off[t] = 1
                        # Or turned on
                        elif self.START[t] - self.START[t_prev] == 1:
                            self.turned_on[t] = 1

            # B. CONSTRAINTS ON THE AUXILIARY VARIABLES

            # These constraints define the auxiliary variables, turned_on and turned_off.

            # Constraints on the indicator that the unit has started on t
            # which is detected when OFF[t-1] = 1 and OFF[t] = 0
            # This amounts to be turned on when the unit enters the START state as in eq. (3)
            for t in self.time_frame:
                self.add_constraint(self.turned_on[t] <= 1 - self.OFF[t])
                self.add_constraint(self.turned_on[t] <= self.OFF[t - self.parameters.time_step])
                self.add_constraint(
                    self.turned_on[t] >= self.OFF[t - self.parameters.time_step] - self.OFF[t],
                    f"constraints_defining_turned_on_{t}",
                )

                # Constraints on turned_off
            # Defined here when entering the OFF state as in eq. (4) because T_stop = 0
            for t in self.time_frame:
                self.add_constraint(self.turned_off[t] <= 1 - self.OFF[t - self.parameters.time_step])
                self.add_constraint(self.turned_off[t] <= self.OFF[t])
                self.add_constraint(
                    self.turned_off[t] >= self.OFF[t] - self.OFF[t - self.parameters.time_step],
                    f"constraints_defining_turned_off_{t}",
                )

            # C. CONSTRAINTS ON THE STATE VARIABLES

            # Mutual exclusion constraint
            for t in self.time_frame:
                # Defined over the whole time frame
                # Enforces eq. (9)
                self.add_constraint(
                    self.OFF[t] + self.ON_UP[t] + self.ON_DOWN[t] + self.START[t] == 1,
                    f"mutual_exclusion_at_{t}",
                )

            # Transitions:
            # Transitions from ON_UP and ON_DOWN to START and START to OFF are forbidden
            # Direct transitions from OFF to ON_UP and ON_DOWN are forbidden.
            for t in self.time_frame:
                t_minus_one = t - self.parameters.time_step
                self.add_constraint(self.ON_UP[t_minus_one] + self.START[t] <= 1)  # eq. (10)
                self.add_constraint(self.ON_DOWN[t_minus_one] + self.START[t] <= 1)  # eq. (10)
                self.add_constraint(self.START[t_minus_one] + self.OFF[t] <= 1)  # eq. (11)
                self.add_constraint(self.OFF[t_minus_one] + self.ON_UP[t] <= 1)  # eq. (15)
                self.add_constraint(
                    self.OFF[t_minus_one] + self.ON_DOWN[t] <= 1,
                    f"transitions_constraints_at_{t}",
                )  # eq. (15)

            # Eviction constraint. This constraint forces the unit to leave the START state once the startup phase is finished.
            for t in self.time_frame:
                t_minus_T_start = t - self.T_start * self.parameters.time_step
                # Implement eqution (16)
                self.add_constraint(
                    self.turned_on[t_minus_T_start] + self.START[t] <= 1,
                    f"eviction_constraint_at_{t}",
                )

            # Mininum time on and minimum time off constraints:
            # if self.T_on >= 2, self.T_off >= 2 or T_stop >= 2, lock the unit in this state.
            if self.T_on >= 2:
                for t in self.time_frame:
                    time_steps = range(1, self.T_on)
                    for s in time_steps:
                        # Enforce eq. (31) with T_start > 0
                        t_minus_s_minus_T_start = (
                            t - s * self.parameters.time_step - self.T_start * self.parameters.time_step
                        )
                        self.add_constraint(
                            self.turned_on[t_minus_s_minus_T_start] <= self.ON_UP[t] + self.ON_DOWN[t],
                            f"minimum_time_ON_{self.thermal_unit.name}_at_{t_minus_s_minus_T_start}_for_{t}",
                        )
            if self.T_off >= 2:
                for t in self.time_frame:
                    time_steps = range(1, self.T_off)
                    for s in time_steps:
                        # Enforce eq. (32) with T_stop = 0
                        t_minus_s = t - s * self.parameters.time_step
                        self.add_constraint(
                            self.turned_off[t_minus_s] <= self.OFF[t],
                            f"minimum_time_OFF_{self.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                        )
            if self.T_start >= 2:
                for t in self.time_frame:
                    for s in self.start_time_steps:
                        t_minus_s = t - s * self.parameters.time_step
                        # Enforce eq. (17)
                        self.add_constraint(
                            self.turned_on[t_minus_s] <= self.START[t],
                            f"startup_ramp_of_{self.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                        )

            # D. CONSTRAINTS ON THE CONTROL VARIABLE

            # Start-up gradient
            q_min = self.thermal_unit.minimum_power.max()  # Get the minimum_power without the reserve requirements
            q_step = q_min / self.T_start

            # Reserves requirements
            # We are in a case where there is no FLAT state, so manual reserves can be provided
            # as long as the unit is online.

            # Constraints on contractedDifference (eq. (40)) and on automatedContractedDifference (eq. (39))
            self.create_contracted_diff_constraints(
                self.time_frame,
                self.contracted_difference_up,
                self.reserves_up_procured,
                self.reserves_up,
                self.contracted_difference_down,
                self.reserves_down_procured,
                self.reserves_down,
                self.automated_contracted_difference_up,
                self.feasible_automated_reserves_up_procured,
                self.automated_reserves_up,
                self.automated_contracted_difference_down,
                self.feasible_automated_reserves_down_procured,
                self.automated_reserves_down,
            )

            # Upward and downward "fill up" constraints.
            self.create_fill_up_constraints(
                self.time_frame,
                self.q,
                self.reserves_up,
                self.automated_reserves_up,
                self.unprovided_reserves_up,
                self.q_upper,
                self.parameters.epsilon,
                self.reserves_down,
                self.automated_reserves_down,
                self.unprovided_reserves_down,
                self.relaxed_reserves,
                self.q_lower,
            )

            # relaxedReserve disabling condition (eq. (43))
            for t in self.time_frame:
                self.add_constraint(
                    self.relaxed_reserves[t] <= self.q_lower.get_value(t) * (1 - self.ON_UP[t] - self.ON_DOWN[t])
                )

            # impossible commitment and stable reserves constraints (eq. (44))
            for t in self.time_frame:
                self.add_constraint(
                    self.automated_reserves_up[t] <= self.maximum_automated * (1 - self.OFF[t] - self.START[t])
                )
                self.add_constraint(
                    self.automated_reserves_down[t] <= self.maximum_automated * (1 - self.OFF[t] - self.START[t])
                )
                self.add_constraint(
                    self.reserves_up[t] <= self.q_upper.get_value(t) * (1 - self.OFF[t] - self.START[t])
                )
                self.add_constraint(
                    self.reserves_down[t] <= self.q_upper.get_value(t) * (1 - self.OFF[t] - self.START[t])
                )

            # Power output
            for t in self.time_frame:
                self.add_constraint(
                    self.q[t] >= self.q_lower.get_value(t) * (self.ON_UP[t] + self.ON_DOWN[t]),
                    f"lower_bound_of_{self.thermal_unit.name}_at_{t}",
                )  # Lower bound (eq. (33))
                self.add_constraint(
                    self.q[t] <= self.q_upper.get_value(t) * (self.ON_UP[t] + self.ON_DOWN[t]) + self.START[t] * q_min,
                    f"upper_bound_of_{self.thermal_unit.name}_at_{t}",
                )  # Upper bound (eq. (34))

            if self.delta_q > 0:  # Case where the gradient is finite.
                for t in self.gradients_time_frame:  # The gradients are defined only up to T-1.
                    # NB. The downward gradient implemented here requires the unit to be at most at deltaQ in order to be able to enter the stop state.
                    # The resulting constraint set is considerably more constraining than if the gradient was relaxed.
                    t_next = t + self.parameters.time_step  # Get the next time step

                    # Upward constrained gradient (eq. (35))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        <= self.delta_q * self.ON_UP[t] + self.turned_on[t_next] * q_step + self.START[t] * q_step,
                        f"upward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Upward gradient

                    # Downward constrained gradient (eq. (37))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        >= -self.delta_q * self.ON_DOWN[t]
                        + self.turned_on[t_next] * q_step
                        + self.START[t] * q_step
                        - self.delta_q_unconstrained * self.turned_off[t_next],
                        f"downward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Downward gradient

            elif self.delta_q == 0:  # Case where the gradient is 'infinite'
                for t in self.gradients_time_frame:
                    t_next = t + self.parameters.time_step  # Get the next time step

                    # Upward unconstrained gradient (eq. (36))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        <= self.delta_q_unconstrained * self.ON_UP[t]
                        + self.turned_on[t_next] * q_step
                        + self.START[t] * q_step,
                        f"unconstrained_upward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Upward gradient

                    # Downward unconstrained gradient (eq. (38))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        >= (
                            -self.delta_q_unconstrained * self.ON_DOWN[t]
                            + self.turned_on[t_next] * q_step
                            + self.START[t] * q_step
                            - self.delta_q_unconstrained * self.turned_off[t_next]
                        ),
                        f"unconstrained_downward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Downward gradient
            else:  # Raise an error since no gradients have been detected.
                cfg.logger.error(
                    f"*** WARNING ***\n No gradients have been defined for equipment {self.thermal_unit.name}. \n "
                    "Please check the value of `maximum_gradient`."
                )
                raise ValueError("Missing gradients for thermic units.")

            self.create_daily_energy_constraint(self.thermal_unit, self.time_frame, self.parameters.time_step, self.q)

    def _combination_5(self):
        """Combination 5 : T_start =0, self.T_stable = T_stop >= 1"""

        if self.T_stop >= 1 and self.T_start == 0 and self.T_stable >= 1:
            # In this case, there are four state variables and the following auxiliary variables :
            #     - turned_on[t] and turned_off[t], indicating whether the unit has been turned on or off
            #     - stable[t], indicating whether the unit entered the stable state
            #     - U[t] and D[t], implemented in two stages with tilde_D[t], tilde_D[t] as the first stage
            #     - entered_up[t] and entered_down[t] indicating that the unit entered the UP or down STATE
            #
            # We review the initial conditions, then the constraints on the state variables
            # and finally the constraints on the power output.

            # PREAMBLE
            # Definition of two additional auxiliary variables needed specifically to handle this case,
            # flat_down_stop, which detects when the unit follows a FLAT(t-2) - DOWN(t-1) and STOP(t) path
            # and DD, which detects if the unit is to be stopped at t+1 (i.e. STOP(t+1) = 1) after having been
            # in the DOWN state at time steps t and t-1.

            # flat_down_stop
            flat_down_stop = {}
            for t in self.time_frame:
                flat_down_stop[t] = self.add_continuous_variable(
                    f"flat_down_stop_at_{t}_equip_{self.thermal_unit.name}",
                    0,
                    1,
                )

            DD = {}
            for t in self.gradients_time_frame:
                DD[t] = self.add_continuous_variable(
                    f"DD_at_{t}_equip_{self.thermal_unit.name}", self.Q_min, self.Q_max
                )

            # A. INITIAL CONDITIONS

            # Define the start_date - 2 time steps.
            start_date_minus_two = self.parameters.start_date - 2 * self.parameters.time_step

            # See if the program needs to be initialized as DayZero or not
            if len(self.last_power) == 0:
                # Initialization of the program as DayZero and warn the user
                if self.parameters.verbose:
                    cfg.logger.warning("***WARNING***\n The program is initialized for the first time.")
                day_zero = True  # Boolean to keep track of the status
            elif self.last_date != self.parameters.start_date - self.parameters.time_step:
                # last_date doesn't match start_date - time_step (i.e. t_{-1}, so we will initialize as DayZero and send a warning message
                if self.parameters.verbose:
                    cfg.logger.warning(
                        f"***WARNING***\n The last_date found in Power of equipement {self.thermal_unit.name} "
                        "does not match the start_date of the current program. \n "
                        "The program will be initialized as DayZero."
                    )
                day_zero = True
            else:
                day_zero = False
                # Setting up the initial conditions of the program
            if day_zero:
                # Remind the user how the program has been initialized
                if self.parameters.verbose:
                    cfg.logger.info(
                        f"Initial conditions of unit {self.thermal_unit.name} have been set as in equation (47)."
                    )

                for t in self.previous_time_frame:
                    # Initial conditions on the power output
                    self.q[t] = 0
                    # Initial conditions on the state variables : the unit is OFF
                    self.OFF[t] = 1
                    self.STOP[t] = 0
                    if not t == self.start_date_minus_one:
                        self.ON_UP[t] = 0
                        self.ON_DOWN[t] = 0
                        self.ON_FLAT[t] = 0
                        # Initial conditions on the auxiliary variables defined over time_frame_union_minus_one
                        self.stable[t] = 0
                        self.entered_up[t] = 0
                        self.entered_down[t] = 0

                    # Initial conditions on the remaining auxiliary variables
                    self.turned_on[t] = 0
                    self.turned_off[t] = 0
                    flat_down_stop[t] = 0
            else:
                # Setting up the initial conditions will be a bit more complex. We consecutively do the following:
                #    - Set the inital conditions on the power output
                #    - See wether the unit is ON or OFF
                #    - Initialize the auxiliaries turned_up and turned_down accordingly
                #    - For the steps where the unit is ON:
                #         - See whether the unit was UP, DOWN or FLAT
                #         - Initialize the auxiliary variables accordingly

                # Initial condition on the power output
                for t in self.previous_time_frame:
                    self.q[t] = self.last_power.get_value(t)

                # Initial conditions on the state variables OFF/ON
                for t in self.previous_time_frame:
                    if self.last_power.get_value(t) >= self.thermal_unit.minimum_power.get_value(t):
                        self.OFF[t] = (
                            0  # Only the OFF and STOP variables are initialized. ON_FLAT, ON_DOWN and ON_UP will be
                        )
                        # initialized afterwards.
                        self.STOP[t] = 0
                    elif self.last_power.get_value(t) > 0:
                        self.OFF[t] = 0
                        self.STOP[t] = 1
                        if not t == self.start_date_minus_one:
                            self.ON_UP[t] = 0
                            self.ON_DOWN[t] = 0
                            self.ON_FLAT[t] = 0
                    else:
                        self.OFF[t] = 1
                        self.STOP[t] = 0
                        if not t == self.start_date_minus_one:
                            self.ON_UP[t] = 0
                            self.ON_DOWN[t] = 0
                            self.ON_FLAT[t] = 0

                # Initial conditions on the auxiliary variables turned_on turned_off and flat_down_stop
                for t in self.previous_time_frame:
                    # Initialize all the values to 0
                    self.turned_on[t] = 0
                    self.turned_off[t] = 0
                    flat_down_stop[t] = 0
                    if not t == self.extended_start_date:
                        # Reconstruct potential switches using the state variables
                        t_prev = t - self.parameters.time_step
                        # See if the unit has been turned off
                        if self.STOP[t] - self.STOP[t_prev] == 1:
                            self.turned_off[t] = 1
                        # Or turned on
                        elif self.OFF[t] - self.OFF[t_prev] == -1:
                            self.turned_on[t] = 1

                # Reconstruct the values of UP, DOWN and FLAT and their associated
                # auxiliary variables
                for t in self.previous_time_frame[
                    :-1
                ]:  # Loop excluding last date because we are reconstructing the values of the
                    # ON variables using  variations between q[t] and q[t-1].

                    t_prev = t - self.parameters.time_step
                    if self.OFF[t_prev] == 0:
                        # See if the power output was stable, increasing or decreasing:
                        if self.q[t] > self.q[t_prev]:  # Recall that here t_prev is earlier than t.
                            self.ON_UP[t_prev] = 1
                            self.ON_DOWN[t_prev] = 0
                            self.ON_FLAT[t_prev] = 0
                        elif self.q[t] < self.q[t_prev]:
                            self.ON_UP[t_prev] = 0
                            self.ON_DOWN[t_prev] = 1
                            self.ON_FLAT[t_prev] = 0
                        elif self.q[t] == self.q[t_prev]:
                            self.ON_UP[t_prev] = 0
                            self.ON_DOWN[t_prev] = 0
                            self.ON_FLAT[t_prev] = 1

                # Initialize the auxiliary variables
                for t in self.previous_time_frame[
                    1:
                ]:  # Loop excluding start_date_minus_one, which is the first element in the previous_time_frame list.
                    # Default value set to 0
                    self.stable[t] = 0
                    self.entered_up[t] = 0
                    self.entered_down[t] = 0

                    if (not t == self.extended_start_date) and (not self.OFF[t] == 1):
                        t_prev = t - self.parameters.time_step

                        # See if the unit entered the FLAT state
                        if self.ON_FLAT[t] - self.ON_FLAT[t_prev] == 1:
                            self.stable[t] = 1
                        # or the UP state
                        if self.ON_UP[t] - self.ON_UP[t_prev] == 1:
                            self.entered_up[t] = 1
                        # or the DOWN state
                        if self.ON_DOWN[t] - self.ON_DOWN[t_prev] == 1:
                            self.entered_down[t] = 1

                # Initialize flat_down_stop.
                for t in self.previous_time_frame[:-2]:
                    # Moreover, if we are after extended_start_date + time_step
                    # initialize flat_down_stop (which traces back up to two time index before)
                    t_minus_one = t - self.parameters.time_step
                    t_minus_two = t - 2 * self.parameters.time_step
                    flat_down_stop[t] = int(
                        math.floor((self.STOP[t] + self.ON_DOWN[t_minus_one] + self.ON_FLAT[t_minus_two]) / 3)
                    )

                    # Initialize the gradient auxiliaries. This is only required for the last time step of the
            # previous_time_frame. Only ON_UP[start_date_minus_one] and ON_DOWN[start_date_minus_one] are decision variables
            # in the expressions below.
            self.U[self.start_date_minus_one] = (
                self.ON_UP[self.start_date_minus_one]
                * self.ON_UP[start_date_minus_two]
                * (self.q[self.start_date_minus_one] - self.q[start_date_minus_two])
            )
            self.D[self.start_date_minus_one] = (
                self.ON_DOWN[self.start_date_minus_one]
                * self.ON_DOWN[start_date_minus_two]
                * (self.q[self.start_date_minus_one] - self.q[start_date_minus_two])
            )

            # B. CONSTRAINTS ON THE AUXILIARY VARIABLES

            # These constraints define the auxiliary variables. In the first case, there are only two
            # of them : turned_on and turned_off.

            # Constraints on the indicator that the unit has started on t
            # Enforces eq. (3)
            for t in self.time_frame:
                self.add_constraint(self.turned_on[t] <= 1 - self.OFF[t])
                self.add_constraint(self.turned_on[t] <= self.OFF[t - self.parameters.time_step])
                self.add_constraint(self.turned_on[t] >= self.OFF[t - self.parameters.time_step] - self.OFF[t])

                # Constraints on turned_off
            # Enforces eq. (5) as there a STOP state in this case.
            for t in self.time_frame:
                self.add_constraint(self.turned_off[t] <= 1 - self.STOP[t - self.parameters.time_step])
                self.add_constraint(self.turned_off[t] <= self.STOP[t])
                self.add_constraint(self.turned_off[t] >= self.STOP[t] - self.STOP[t - self.parameters.time_step])

            # stable auxiliary variable
            # Enforces eq. (6)
            for t in self.time_frame_union_minus_one:
                self.add_constraint(self.stable[t] <= 1 - self.ON_FLAT[t - self.parameters.time_step])
                self.add_constraint(self.stable[t] <= self.ON_FLAT[t])
                self.add_constraint(self.stable[t] >= self.ON_FLAT[t] - self.ON_FLAT[t - self.parameters.time_step])

            # flat_down_stop auxiliary (eq. (22))
            for t in self.time_frame:
                t_minus_one = t - self.parameters.time_step
                t_minus_two = t - 2 * self.parameters.time_step
                self.add_constraint(flat_down_stop[t] <= self.STOP[t])
                self.add_constraint(flat_down_stop[t] <= self.ON_DOWN[t_minus_one])
                self.add_constraint(flat_down_stop[t] <= self.ON_FLAT[t_minus_two])
                self.add_constraint(
                    flat_down_stop[t] >= self.STOP[t] + self.ON_DOWN[t_minus_one] + self.ON_FLAT[t_minus_two] - 2
                )

            # entered_up and entered_down auxiliaries
            for t in self.time_frame_union_minus_one:
                # entered_up (eq. (7))
                self.add_constraint(self.entered_up[t] <= 1 - self.ON_UP[t - self.parameters.time_step])
                self.add_constraint(self.entered_up[t] <= self.ON_UP[t])
                self.add_constraint(self.entered_up[t] >= self.ON_UP[t] - self.ON_UP[t - self.parameters.time_step])
                # entered_down (eq. (8))
                self.add_constraint(self.entered_down[t] <= 1 - self.ON_DOWN[t - self.parameters.time_step])
                self.add_constraint(self.entered_down[t] <= self.ON_DOWN[t])
                self.add_constraint(
                    self.entered_down[t] >= self.ON_DOWN[t] - self.ON_DOWN[t - self.parameters.time_step]
                )

            # UP and DOWN auxiliary variables for the gradient.
            # These auxiliary variables model the fact that if the unit is increasing (decreasing) its
            # power output twice in a row, then the second time the gradient is locked.
            # In practice, these variables are defined in two stages

            # First stage : tilde_U and tilde_D
            for t in self.time_frame:  # Loop in all the time_frame but start_date.
                t_minus_one = t - self.parameters.time_step
                # tilde_U (eq. (28))
                self.add_constraint(self.tilde_U[t] <= self.Q_max * self.ON_UP[t_minus_one])
                self.add_constraint(self.tilde_U[t] >= self.Q_min * self.ON_UP[t_minus_one])
                self.add_constraint(
                    self.tilde_U[t] <= self.q[t] - self.q[t_minus_one] - self.Q_min * (1 - self.ON_UP[t_minus_one])
                )
                self.add_constraint(
                    self.tilde_U[t] >= self.q[t] - self.q[t_minus_one] - self.Q_max * (1 - self.ON_UP[t_minus_one]),
                    f"VALUE_of_tilde_UP_at_{t}",
                )

                # tilde_D (eq. (30))
                self.add_constraint(self.tilde_D[t] <= self.Q_max * self.ON_DOWN[t_minus_one])
                self.add_constraint(self.tilde_D[t] >= self.Q_min * self.ON_DOWN[t_minus_one])
                self.add_constraint(
                    self.tilde_D[t] <= self.q[t] - self.q[t_minus_one] - self.Q_min * (1 - self.ON_DOWN[t_minus_one])
                )
                self.add_constraint(
                    self.tilde_D[t] >= self.q[t] - self.q[t_minus_one] - self.Q_max * (1 - self.ON_DOWN[t_minus_one]),
                    f"VALUE_of_tilde_DOWN_at_{t}",
                )

            # Second stage : U and D
            # These variables wil be added to the gradient constraints.
            for t in self.time_frame:
                # U (eq. (27))
                self.add_constraint(self.U[t] <= self.Q_max * self.ON_UP[t])
                self.add_constraint(self.U[t] >= self.Q_min * self.ON_UP[t])
                self.add_constraint(self.U[t] <= self.tilde_U[t] - self.Q_min * (1 - self.ON_UP[t]))
                self.add_constraint(
                    self.U[t] >= self.tilde_U[t] - self.Q_max * (1 - self.ON_UP[t]),
                    f"VALUE_of_UP_at_{t}",
                )
                # D (eq. (29))
                self.add_constraint(self.D[t] <= self.Q_max * self.ON_DOWN[t])
                self.add_constraint(self.D[t] >= self.Q_min * self.ON_DOWN[t])
                self.add_constraint(self.D[t] <= self.tilde_D[t] - self.Q_min * (1 - self.ON_DOWN[t]))
                self.add_constraint(
                    self.D[t] >= self.tilde_D[t] - self.Q_max * (1 - self.ON_DOWN[t]),
                    f"VALUE_of_DOWN_at_{t}",
                )

            # DD Gradient auxiliary (eq. (23))
            for t in self.gradients_time_frame:
                t_plus_one = t + self.parameters.time_step
                self.add_constraint(DD[t] <= self.Q_max * self.STOP[t_plus_one])
                self.add_constraint(DD[t] >= self.Q_min * self.STOP[t_plus_one])
                self.add_constraint(DD[t] <= self.D[t] - self.Q_min * (1 - self.STOP[t_plus_one]))
                self.add_constraint(
                    DD[t] >= self.D[t] - self.Q_max * (1 - self.STOP[t_plus_one]),
                    f"DD_gradient_auxiliary_at_{t}",
                )

            # C. CONSTRAINTS ON THE STATE VARIABLES

            # Mutual exclusion constraint
            for t in self.time_frame_union_minus_one:
                # Defined over the whole time frame.
                # Enforces eq. (9)
                self.add_constraint(
                    self.OFF[t] + self.ON_UP[t] + self.ON_DOWN[t] + self.ON_FLAT[t] + self.STOP[t] == 1,
                    f"mutual_exclusion_at_{t}",
                )

            # Transitions:
            # UP-DOWN and DOWN-UP transitions are forbidden.
            # STOP to ON transitions are also forbidden
            # OFF to STOP transitions
            # Finally, we forbid ON_UP to STOP (which never happens in practice) in order
            # to avoid defining a UU auxiliary analoguous to DD.
            for t in self.time_frame_union_minus_one:
                t_minus_one = t - self.parameters.time_step
                # Implement eq. (25)
                self.add_constraint(self.ON_UP[t_minus_one] + self.ON_DOWN[t] <= 1)
                self.add_constraint(self.ON_DOWN[t_minus_one] + self.ON_UP[t] <= 1)
                # Eq (13)
                self.add_constraint(self.STOP[t_minus_one] + self.ON_FLAT[t] <= 1)
                self.add_constraint(self.STOP[t_minus_one] + self.ON_DOWN[t] <= 1)
                self.add_constraint(
                    self.STOP[t_minus_one] + self.ON_UP[t] <= 1,
                    f"transitions_constraints_on_timeFrame_union_minus_one_at_{t}",
                )
            for t in self.time_frame:
                t_minus_one = t - self.parameters.time_step
                # ON_UP to STOP transition (eq. (21))
                self.add_constraint(self.ON_UP[t_minus_one] + self.STOP[t] <= 1)
                # Eq. (12)
                self.add_constraint(
                    self.OFF[t_minus_one] + self.STOP[t] <= 1,
                    f"transitions_constraints_at_{t}",
                )
                # The latter constraints are only defined on the time_frame because it does not involve ON variables at the t index.

            # Eviction constraint
            # The unit must leave the STOP state after T_stop time steps.
            for t in self.time_frame:
                t_minus_T_stop = t - self.T_stop * self.parameters.time_step
                # Implements equation (19)
                self.add_constraint(
                    self.turned_off[t_minus_T_stop] + self.STOP[t] <= 1,
                    f"eviction_constraint_at_{t}",
                )

                # Mininum time on and minimum time off constraints:
            # if self.T_on >= 2 or self.T_off >= 2 or self.T_stable >= 2, lock the unit in this state.
            if self.T_on >= 2:
                for t in self.time_frame_union_minus_one:
                    time_steps = range(1, self.T_on)  # Corresponds to the set {1,..., self.T_on - 1}
                    for s in time_steps:
                        # Enforces eq. (31), with T_start = 0
                        t_minus_s = t - s * self.parameters.time_step
                        self.add_constraint(
                            self.turned_on[t_minus_s] <= self.ON_UP[t] + self.ON_DOWN[t] + self.ON_FLAT[t],
                            f"minimum_time_ON_{self.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                        )
            if self.T_off >= 2:
                for t in self.time_frame:
                    time_steps = range(1, self.T_off)  # Corresponds to the set {1,..., self.T_off - 1}
                    for s in time_steps:
                        # Enforces eq. (32) with T_stop > 0
                        t_minus_s_minus_T_stop = (
                            t - s * self.parameters.time_step - self.T_stop * self.parameters.time_step
                        )
                        self.add_constraint(
                            self.turned_off[t_minus_s_minus_T_stop] <= self.OFF[t],
                            f"minimum_time_OFF_{self.thermal_unit.name}_at_{t_minus_s_minus_T_stop}_for_{t}",
                        )
            if self.T_stable >= 2:
                for t in self.time_frame_union_minus_one:
                    time_steps = range(1, self.T_stable - 1)  # Corresponds to the set {1,..., self.T_stable - 1}
                    for s in time_steps:
                        # Enforces eq. (26)
                        t_minus_s = t - s * self.parameters.time_step
                        self.add_constraint(
                            self.stable[t_minus_s] <= self.ON_FLAT[t],
                            f"minimum_time_STABLE_{self.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                        )
            if self.T_stop >= 2:
                for t in self.time_frame:
                    for s in self.stop_time_steps:
                        t_minus_s = t - s * self.parameters.time_step
                        # Enforces eq. (24)
                        self.add_constraint(
                            self.turned_off[t_minus_s] <= self.STOP[t],
                            f"shutdown_ramp_of_{self.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                        )

            # D. CONSTRAINTS ON THE CONTROL VARIABLE

            # Start-up gradient:
            q_min = self.thermal_unit.minimum_power.max()
            q_step = q_min / self.T_stop

            # Reserves requirements
            # We are in a case where there is a FLAT state, so manual reserves can only be provided
            # when the unit is in the FLAT state.

            # Constraints on contractedDifference (eq. (40)) and on automatedContractedDifference (eq. (39))
            self.create_contracted_diff_constraints(
                self.time_frame,
                self.contracted_difference_up,
                self.reserves_up_procured,
                self.reserves_up,
                self.contracted_difference_down,
                self.reserves_down_procured,
                self.reserves_down,
                self.automated_contracted_difference_up,
                self.feasible_automated_reserves_up_procured,
                self.automated_reserves_up,
                self.automated_contracted_difference_down,
                self.feasible_automated_reserves_down_procured,
                self.automated_reserves_down,
            )

            # Upward and downward "fill up" constraints.
            self.create_fill_up_constraints(
                self.time_frame,
                self.q,
                self.reserves_up,
                self.automated_reserves_up,
                self.unprovided_reserves_up,
                self.q_upper,
                self.parameters.epsilon,
                self.reserves_down,
                self.automated_reserves_down,
                self.unprovided_reserves_down,
                self.relaxed_reserves,
                self.q_lower,
            )

            # relaxedReserve disabling condition (eq. (43))
            for t in self.time_frame:
                self.add_constraint(
                    self.relaxed_reserves[t]
                    <= self.q_lower.get_value(t) * (1 - self.ON_UP[t] - self.ON_FLAT[t] - self.ON_DOWN[t])
                )

            # impossible commitment and stable reserves constraints (eqs. (44) and (45))
            for t in self.time_frame:
                self.add_constraint(
                    self.automated_reserves_up[t] <= self.maximum_automated * (1 - self.OFF[t] - self.STOP[t])
                )
                self.add_constraint(
                    self.automated_reserves_down[t] <= self.maximum_automated * (1 - self.OFF[t] - self.STOP[t])
                )
                self.add_constraint(
                    self.reserves_up[t]
                    <= self.q_upper.get_value(t) * (1 - self.ON_UP[t] - self.ON_DOWN[t] - self.OFF[t] - self.STOP[t])
                )
                # for compacity, implements both eq (44) and (45)
                self.add_constraint(
                    self.reserves_down[t]
                    <= self.q_upper.get_value(t) * (1 - self.ON_UP[t] - self.ON_DOWN[t] - self.OFF[t] - self.STOP[t])
                )

            # Power output
            for t in self.time_frame:
                self.add_constraint(
                    self.q[t]
                    >= self.q_lower.get_value(t) * (self.ON_UP[t] + self.ON_DOWN[t] + self.ON_FLAT[t])
                    + self.turned_off[t] * (q_min - q_step),
                    f"lower_bound_of_{self.thermal_unit.name}_at_{t}",
                )  # Lower bound (eq. (33))

                self.add_constraint(
                    self.q[t]
                    <= self.q_upper.get_value(t) * (self.ON_UP[t] + self.ON_DOWN[t] + self.ON_FLAT[t])
                    + self.STOP[t] * q_min
                    - self.turned_off[t] * q_step,
                    f"upper_bound_of_{self.thermal_unit.name}_at_{t}",
                )  # Upper bound (eq. (34))

            # Power gradients
            if self.delta_q > 0:  # Case where the gradient is finite.
                for t in self.gradients_time_frame:  # The gradients are defined only up to T-1.
                    t_next = t + self.parameters.time_step  # Get the next time step

                    # Upward constrained gradient (eq. (35))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        <= (
                            self.delta_q * self.entered_up[t]
                            + self.U[t]
                            + self.D[t]
                            - q_step * self.turned_off[t_next]
                            - self.STOP[t] * q_step
                            + self.delta_q_unconstrained * self.turned_on[t_next]
                            - DD[t]
                        ),
                        f"upward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Upward gradient

                    # Downward constrained gradient (eq. (37))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        >= (
                            -self.delta_q * self.entered_down[t]
                            + self.U[t]
                            + self.D[t]
                            - q_step * self.turned_off[t_next]
                            - self.STOP[t] * q_step
                            + flat_down_stop[t_next] * self.delta_q
                            - DD[t]
                        ),
                        f"downward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Downward gradient

            elif self.delta_q == 0:  # Case where the gradient is 'infinite'
                for t in self.gradients_time_frame:
                    t_next = t + self.parameters.time_step  # Get the next time step

                    # Upward unconstrained gradient (eq. (36))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        <= (
                            self.delta_q_unconstrained * self.entered_up[t]
                            + self.U[t]
                            + self.D[t]
                            - q_step * self.turned_off[t_next]
                            - self.STOP[t] * q_step
                            + self.delta_q_unconstrained * self.turned_on[t_next]
                        ),
                        f"unconstrained_upward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Upward gradient

                    # Downward unconstrained gradient (eq. (38))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        >= (
                            -self.delta_q_unconstrained * self.entered_down[t]
                            + self.U[t]
                            + self.D[t]
                            - q_step * self.turned_off[t_next]
                            - self.STOP[t] * q_step
                            + flat_down_stop[t_next] * self.delta_q_unconstrained
                            - DD[t]
                        ),
                        f"unconstrained_downward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Downward gradient

            else:  # Raise an error since no gradients have been detected.
                cfg.logger.error(
                    f"*** WARNING ***\n No gradients have been defined for equipment {self.thermal_unit.name}. \n "
                    "Please check the value of `maximum_gradient`."
                )
                raise ValueError("Missing gradients for thermic units.")

            self.create_daily_energy_constraint(self.thermal_unit, self.time_frame, self.parameters.time_step, self.q)

    def _combination_6(self):
        """Combination 6 : T_stop =0, self.T_stable = T_start >= 1"""

        if self.T_stop == 0 and self.T_start >= 1 and self.T_stable >= 1:
            # In this case, there are five state variables and the following auxiliary variables :
            #     - turned_on[t] and turned_off[t], indicating whether the unit has been turned on or off
            #     - stable[t], indicating whether the unit entered the stable state
            #     - U[t] and D[t], implemented in two stages with tilde_D[t], tilde_D[t] as the first stage
            #     - entered_up[t] and entered_down[t] indicating that the unit entered the UP or down STATE
            #
            # We review the initial conditions, then the constraints on the state variables
            # and finally the constraints on the power output.

            # A. INITIAL CONDITIONS

            # Define the start_date - 2 time steps.
            start_date_minus_two = self.parameters.start_date - 2 * self.parameters.time_step

            # See if the program needs to be initialized as DayZero or not
            if len(self.last_power) == 0:
                # Initialization of the program as DayZero and warn the user
                if self.parameters.verbose:
                    cfg.logger.warning("***WARNING***\n The program is initialized for the first time.")
                day_zero = True  # Boolean to keep track of the status
            elif self.last_date != self.parameters.start_date - self.parameters.time_step:
                # last_date doesn't match start_date - time_step (i.e. t_{-1}, so we will initialize as DayZero and send a warning message
                if self.parameters.verbose:
                    cfg.logger.warning(
                        f"***WARNING***\n The last_date found in Power of equipement {self.thermal_unit.name} "
                        "does not match the start_date of the current program. \n "
                        "The program will be initialized as DayZero."
                    )
                day_zero = True
            else:
                day_zero = False
                # Setting up the initial conditions of the program
            if day_zero:
                # Remind the user how the program has been initialized
                if self.parameters.verbose:
                    cfg.logger.info(
                        f"Initial conditions of unit {self.thermal_unit.name} have been set as in equation (47)."
                    )

                for t in self.previous_time_frame:
                    # Initial conditions on the power output
                    self.q[t] = 0
                    # Initial conditions on the state variables : the unit is OFF
                    self.OFF[t] = 1
                    self.START[t] = 0
                    if not t == self.start_date_minus_one:
                        self.ON_UP[t] = 0
                        self.ON_DOWN[t] = 0
                        self.ON_FLAT[t] = 0
                        # Initial conditions on the auxiliary variables defined over time_frame_union_minus_one
                        self.stable[t] = 0
                        self.entered_up[t] = 0
                        self.entered_down[t] = 0

                    # Initial conditions on the remaining auxiliary variables
                    self.turned_on[t] = 0
                    self.turned_off[t] = 0
            else:
                # Setting up the initial conditions will be a bit more complex. We consecutively do the following:
                #    - Set the inital conditions on the power output
                #    - See wether the unit is ON, OFF or START
                #    - Initialize the auxiliaries turned_up and turned_down accordingly
                #    - For the steps where the unit is ON:
                #         - See whether the unit was UP, DOWN or FLAT
                #         - Initialize the auxiliary variables accordingly

                # Initial condition on the power output
                for t in self.previous_time_frame:
                    self.q[t] = self.last_power.get_value(t)

                # Initial conditions on the state variables.
                # The initialization is done in two times. If we are not at start_date_minus_one and not ON,
                # we initialize all the state variables, otherwise an additional loop will be done to
                # initialize the ON state variables from start_date_minus_two.
                for t in self.previous_time_frame:
                    if self.last_power.get_value(t) >= self.thermal_unit.minimum_power.get_value(t):
                        self.OFF[t] = 0
                        self.START[t] = 0
                    elif self.last_power.get_value(t) > 0:
                        self.OFF[t] = 0
                        self.START[t] = 1
                        if not t == self.start_date_minus_one:
                            self.ON_UP[t] = 0
                            self.ON_FLAT[t] = 0
                            self.ON_DOWN[t] = 0
                    else:
                        self.OFF[t] = 1
                        self.START[t] = 0
                        if not t == self.start_date_minus_one:
                            self.ON_UP[t] = 0
                            self.ON_DOWN[t] = 0
                            self.ON_FLAT[t] = 0

                # Reconstruct the values of UP, DOWN and FLAT state variables
                for t in self.previous_time_frame[
                    :-1
                ]:  # Loop excluding last date because we are reconstructing the values of the
                    # ON variables using  variations between q[t] and q[t-1].
                    t_prev = t - self.parameters.time_step
                    if self.q[t_prev] >= self.thermal_unit.minimum_power.get_value(t_prev):
                        # See if the power output was stable, increasing or decreasing:
                        if self.q[t] > self.q[t_prev]:  # Recall that here t_prev is earlier than t.
                            self.ON_UP[t_prev] = 1
                            self.ON_DOWN[t_prev] = 0
                            self.ON_FLAT[t_prev] = 0
                        elif self.q[t] < self.q[t_prev]:
                            self.ON_UP[t_prev] = 0
                            self.ON_DOWN[t_prev] = 1
                            self.ON_FLAT[t_prev] = 0
                        elif self.q[t] == self.q[t_prev]:
                            self.ON_UP[t_prev] = 0
                            self.ON_DOWN[t_prev] = 0
                            self.ON_FLAT[t_prev] = 1

                # Initial conditions on the auxiliary variables turned_on and turned_off.
                for t in self.previous_time_frame:
                    # Initialize all the values to 0
                    self.turned_on[t] = 0
                    self.turned_off[t] = 0
                    if not t == self.extended_start_date:
                        # Reconstruct potential switches using the state variables
                        t_prev = t - self.parameters.time_step
                        # See if the unit has been turned off
                        if self.OFF[t] - self.OFF[t_prev] == 1:
                            self.turned_off[t] = 1
                        # Or turned on
                        elif self.START[t] - self.START[t_prev] == 1:
                            self.turned_on[t] = 1

                # Initialize the auxiliary variables entered_up, entered_down and stable.
                for t in self.previous_time_frame[
                    1:
                ]:  # Loop excluding start_date_minus_one, which is the first element in the previous_time_frame list.
                    # Default value set to 0
                    self.stable[t] = 0
                    self.entered_up[t] = 0
                    self.entered_down[t] = 0

                    if (not t == self.extended_start_date) and (not self.OFF[t] == 1):
                        t_prev = t - self.parameters.time_step

                        # See if the unit entered the FLAT state
                        if self.ON_FLAT[t] - self.ON_FLAT[t_prev] == 1:
                            self.stable[t] = 1
                        # or the UP state
                        if self.ON_UP[t] - self.ON_UP[t_prev] == 1:
                            self.entered_up[t] = 1
                        # or the DOWN state
                        if self.ON_DOWN[t] - self.ON_DOWN[t_prev] == 1:
                            self.entered_down[t] = 1

                            # Initialize the gradient auxiliaries. This is only required for the last time step of the
            # previous_time_frame. Only ON_UP[start_date_minus_one] and ON_DOWN[start_date_minus_one] are decision variables
            # in the expressions below.
            self.U[self.start_date_minus_one] = (
                self.ON_UP[self.start_date_minus_one]
                * self.ON_UP[start_date_minus_two]
                * (self.q[self.start_date_minus_one] - self.q[start_date_minus_two])
            )
            self.D[self.start_date_minus_one] = (
                self.ON_DOWN[self.start_date_minus_one]
                * self.ON_DOWN[start_date_minus_two]
                * (self.q[self.start_date_minus_one] - self.q[start_date_minus_two])
            )

            # B. CONSTRAINTS ON THE AUXILIARY VARIABLES

            # These constraints define the auxiliary variables. In the first case, there are only two
            # of them : turned_on and turned_off.

            # Constraints on the indicator that the unit has started on t
            # Enforces eq. (3)
            for t in self.time_frame:
                self.add_constraint(self.turned_on[t] <= 1 - self.OFF[t])
                self.add_constraint(self.turned_on[t] <= self.OFF[t - self.parameters.time_step])
                self.add_constraint(self.turned_on[t] >= self.OFF[t - self.parameters.time_step] - self.OFF[t])

                # Constraints on turned_off
            # Enforces eq. (4) as there is no STOP state in this case.
            for t in self.time_frame:
                self.add_constraint(self.turned_off[t] <= 1 - self.OFF[t - self.parameters.time_step])
                self.add_constraint(self.turned_off[t] <= self.OFF[t])
                self.add_constraint(self.turned_off[t] >= self.OFF[t] - self.OFF[t - self.parameters.time_step])

            # stable auxiliary variable
            # Enforces eq. (6)
            for t in self.time_frame_union_minus_one:
                self.add_constraint(self.stable[t] <= 1 - self.ON_FLAT[t - self.parameters.time_step])
                self.add_constraint(self.stable[t] <= self.ON_FLAT[t])
                self.add_constraint(self.stable[t] >= self.ON_FLAT[t] - self.ON_FLAT[t - self.parameters.time_step])

            # entered_up and entered_down auxiliaries
            for t in self.time_frame_union_minus_one:
                # entered_up (eq. (7))
                self.add_constraint(self.entered_up[t] <= 1 - self.ON_UP[t - self.parameters.time_step])
                self.add_constraint(self.entered_up[t] <= self.ON_UP[t])
                self.add_constraint(self.entered_up[t] >= self.ON_UP[t] - self.ON_UP[t - self.parameters.time_step])
                # entered_down (eq. (8))
                self.add_constraint(self.entered_down[t] <= 1 - self.ON_DOWN[t - self.parameters.time_step])
                self.add_constraint(self.entered_down[t] <= self.ON_DOWN[t])
                self.add_constraint(
                    self.entered_down[t] >= self.ON_DOWN[t] - self.ON_DOWN[t - self.parameters.time_step]
                )

            # UP and DOWN auxiliary variables for the gradient.
            # These auxiliary variables model the fact that if the unit is increasing (decreasing) its
            # power output twice in a row, then the second time the gradient is locked.
            # In practice, these variables are defined in two stages

            # First stage : tilde_U and tilde_D
            for t in self.time_frame:  # Loop in all the time_frame but start_date.
                t_minus_one = t - self.parameters.time_step
                # tilde_U (eq. (28))
                self.add_constraint(self.tilde_U[t] <= self.Q_max * self.ON_UP[t_minus_one])
                self.add_constraint(self.tilde_U[t] >= self.Q_min * self.ON_UP[t_minus_one])
                self.add_constraint(
                    self.tilde_U[t] <= self.q[t] - self.q[t_minus_one] - self.Q_min * (1 - self.ON_UP[t_minus_one])
                )
                self.add_constraint(
                    self.tilde_U[t] >= self.q[t] - self.q[t_minus_one] - self.Q_max * (1 - self.ON_UP[t_minus_one]),
                    f"VALUE_of_tilde_UP_at_{t}",
                )

                # tilde_D (eq. (30))
                self.add_constraint(self.tilde_D[t] <= self.Q_max * self.ON_DOWN[t_minus_one])
                self.add_constraint(self.tilde_D[t] >= self.Q_min * self.ON_DOWN[t_minus_one])
                self.add_constraint(
                    self.tilde_D[t] <= self.q[t] - self.q[t_minus_one] - self.Q_min * (1 - self.ON_DOWN[t_minus_one])
                )
                self.add_constraint(
                    self.tilde_D[t] >= self.q[t] - self.q[t_minus_one] - self.Q_max * (1 - self.ON_DOWN[t_minus_one]),
                    f"VALUE_of_tilde_DOWN_at_{t}",
                )

            # Second stage : U and D
            # These variables wil be added to the gradient constraints.
            for t in self.time_frame:
                # U (eq. (27))
                self.add_constraint(self.U[t] <= self.Q_max * self.ON_UP[t])
                self.add_constraint(self.U[t] >= self.Q_min * self.ON_UP[t])
                self.add_constraint(self.U[t] <= self.tilde_U[t] - self.Q_min * (1 - self.ON_UP[t]))
                self.add_constraint(
                    self.U[t] >= self.tilde_U[t] - self.Q_max * (1 - self.ON_UP[t]),
                    f"VALUE_of_UP_at_{t}",
                )
                # D (eq. (29))
                self.add_constraint(self.D[t] <= self.Q_max * self.ON_DOWN[t])
                self.add_constraint(self.D[t] >= self.Q_min * self.ON_DOWN[t])
                self.add_constraint(self.D[t] <= self.tilde_D[t] - self.Q_min * (1 - self.ON_DOWN[t]))
                self.add_constraint(
                    self.D[t] >= self.tilde_D[t] - self.Q_max * (1 - self.ON_DOWN[t]),
                    f"VALUE_of_DOWN_at_{t}",
                )

            # C. CONSTRAINTS ON THE STATE VARIABLES

            # Mutual exclusion constraint
            for t in self.time_frame_union_minus_one:
                # Defined over the whole time frame.
                # Enforces eq. (9)
                self.add_constraint(
                    self.OFF[t] + self.ON_UP[t] + self.ON_DOWN[t] + self.ON_FLAT[t] + self.START[t] == 1,
                    f"mutual_exclusion_at_{t}",
                )

            # Transitions:
            # UP-DOWN and DOWN-UP transitions are forbidden.
            for t in self.time_frame_union_minus_one:
                t_minus_one = t - self.parameters.time_step
                # Implement eq. (25).
                self.add_constraint(self.ON_UP[t_minus_one] + self.ON_DOWN[t] <= 1)
                self.add_constraint(self.ON_DOWN[t_minus_one] + self.ON_UP[t] <= 1)

            # Constraints involving START and OFF are only defined on the time_frame time frame.
            for t in self.time_frame:
                t_minus_one = t - self.parameters.time_step
                # Eq. (10)
                self.add_constraint(self.ON_UP[t_minus_one] + self.START[t] <= 1)
                self.add_constraint(self.ON_DOWN[t_minus_one] + self.START[t] <= 1)
                self.add_constraint(self.ON_FLAT[t_minus_one] + self.START[t] <= 1)
                # Eq. (11)
                self.add_constraint(self.START[t_minus_one] + self.OFF[t] <= 1)
                # Eq. (15)
                self.add_constraint(self.OFF[t_minus_one] + self.ON_UP[t] <= 1)
                self.add_constraint(self.OFF[t_minus_one] + self.ON_DOWN[t] <= 1)
                self.add_constraint(
                    self.OFF[t_minus_one] + self.ON_FLAT[t] <= 1,
                    f"transitions_constraints_at_{t}",
                )

            # Eviction constraint
            # The unit must leave the START state after T_start time steps.
            for t in self.time_frame:
                t_minus_T_start = t - self.T_start * self.parameters.time_step
                # Implement equation (16)
                self.add_constraint(
                    self.turned_on[t_minus_T_start] + self.START[t] <= 1,
                    f"eviction_constraint_at_{t}",
                )

            # Mininum time on and minimum time off constraints:
            # if self.T_on >= 2 or self.T_off >= 2 or self.T_stable >= 2, lock the unit in this state.
            if self.T_on >= 2:
                for t in self.time_frame_union_minus_one:
                    time_steps = range(1, self.T_on)  # Corresponds to the set {1,..., self.T_on - 1}
                    for s in time_steps:
                        # Enforces eq. (31), with T_start > 0
                        t_minus_s_minus_T_start = (
                            t - s * self.parameters.time_step - self.T_start * self.parameters.time_step
                        )
                        self.add_constraint(
                            self.turned_on[t_minus_s_minus_T_start]
                            <= self.ON_UP[t] + self.ON_DOWN[t] + self.ON_FLAT[t],
                            f"minimum_time_ON_{self.thermal_unit.name}_at_{t_minus_s_minus_T_start}_for_{t}",
                        )
            if self.T_off >= 2:
                for t in self.time_frame:
                    time_steps = range(1, self.T_off)  # Corresponds to the set {1,..., self.T_off - 1}
                    for s in time_steps:
                        # Enforces eq. (32) with T_stop = 0
                        t_minus_s = t - s * self.parameters.time_step
                        self.add_constraint(
                            self.turned_off[t_minus_s] <= self.OFF[t],
                            f"minimum_time_OFF_{self.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                        )
            if self.T_stable >= 2:
                for t in self.time_frame_union_minus_one:
                    time_steps = range(1, self.T_stable - 1)  # Corresponds to the set {1,..., self.T_stable - 2}
                    for s in time_steps:
                        # Enforces eq. (26)
                        t_minus_s = t - s * self.parameters.time_step
                        self.add_constraint(
                            self.stable[t_minus_s] <= self.ON_FLAT[t],
                            f"minimum_time_STABLE_{self.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                        )
            if self.T_start >= 2:
                for t in self.time_frame:
                    for s in self.start_time_steps:
                        t_minus_s = t - s * self.parameters.time_step
                        # Enforces eq. (17)
                        self.add_constraint(
                            self.turned_on[t_minus_s] <= self.START[t],
                            f"start_up_ramp_of_{self.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                        )

            # D. CONSTRAINTS ON THE CONTROL VARIABLE

            # Start-up gradient:
            q_min = self.thermal_unit.minimum_power.max()
            q_step = q_min / self.T_start

            # Reserves requirements
            # We are in a case where there is a FLAT state, so manual reserves can only be provided
            # when the unit is in the FLAT state.

            # Constraints on contractedDifference (eq. (40)) and on automatedContractedDifference (eq. (39))
            self.create_contracted_diff_constraints(
                self.time_frame,
                self.contracted_difference_up,
                self.reserves_up_procured,
                self.reserves_up,
                self.contracted_difference_down,
                self.reserves_down_procured,
                self.reserves_down,
                self.automated_contracted_difference_up,
                self.feasible_automated_reserves_up_procured,
                self.automated_reserves_up,
                self.automated_contracted_difference_down,
                self.feasible_automated_reserves_down_procured,
                self.automated_reserves_down,
            )

            # Upward and downward "fill up" constraints.
            self.create_fill_up_constraints(
                self.time_frame,
                self.q,
                self.reserves_up,
                self.automated_reserves_up,
                self.unprovided_reserves_up,
                self.q_upper,
                self.parameters.epsilon,
                self.reserves_down,
                self.automated_reserves_down,
                self.unprovided_reserves_down,
                self.relaxed_reserves,
                self.q_lower,
            )

            # relaxedReserve disabling condition (eq. (43))
            for t in self.time_frame:
                self.add_constraint(
                    self.relaxed_reserves[t]
                    <= self.q_lower.get_value(t) * (1 - self.ON_UP[t] - self.ON_FLAT[t] - self.ON_DOWN[t])
                )

            # impossible commitment and stable reserves constraints (eqs. (44) and (45))
            for t in self.time_frame:
                self.add_constraint(
                    self.automated_reserves_up[t] <= self.maximum_automated * (1 - self.OFF[t] - self.START[t])
                )
                self.add_constraint(
                    self.automated_reserves_down[t] <= self.maximum_automated * (1 - self.OFF[t] - self.START[t])
                )
                self.add_constraint(
                    self.reserves_up[t]
                    <= self.q_upper.get_value(t) * (1 - self.ON_UP[t] - self.ON_DOWN[t] - self.OFF[t] - self.START[t])
                )
                # for compacity, implements both eq (44) and (45)
                self.add_constraint(
                    self.reserves_down[t]
                    <= self.q_upper.get_value(t) * (1 - self.ON_UP[t] - self.ON_DOWN[t] - self.OFF[t] - self.START[t])
                )

            # Power output
            for t in self.time_frame:
                self.add_constraint(
                    self.q[t] >= self.q_lower.get_value(t) * (self.ON_UP[t] + self.ON_DOWN[t] + self.ON_FLAT[t]),
                    f"lower_bound_of_{self.thermal_unit.name}_at_{t}",
                )  # Lower bound (eq. (33))
                self.add_constraint(
                    self.q[t]
                    <= self.q_upper.get_value(t) * (self.ON_UP[t] + self.ON_DOWN[t] + self.ON_FLAT[t])
                    + self.START[t] * q_min,
                    f"upper_bound_of_{self.thermal_unit.name}_at_{t}",
                )  # Upper bound (eq. (34))

            if self.delta_q > 0:  # Case where the gradient is finite.
                for t in self.gradients_time_frame:  # The gradients are defined only up to T-1.
                    t_next = t + self.parameters.time_step  # Get the next time step

                    # Upward constrained gradient (eq. (35))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        <= self.delta_q * self.entered_up[t]
                        + self.U[t]
                        + self.D[t]
                        + q_step * self.turned_on[t_next]
                        + self.START[t] * q_step,
                        f"upward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Upward gradient

                    # Downard constrained gradient (eq. (37))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        >= (
                            -self.delta_q * self.entered_down[t]
                            + self.U[t]
                            + self.D[t]
                            - self.delta_q_unconstrained * self.turned_off[t_next]
                            + q_step * self.turned_on[t_next]
                            + self.START[t] * q_step
                        ),
                        f"downward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Downward gradient

            elif self.delta_q == 0:  # Case where the gradient is 'infinite'
                for t in self.gradients_time_frame:
                    t_next = t + self.parameters.time_step  # Get the next time step

                    # Upward unconstrained gradient (eq. (36))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        <= self.delta_q_unconstrained * self.entered_up[t]
                        + self.U[t]
                        + self.D[t]
                        + q_step * self.turned_on[t_next]
                        + self.START[t] * q_step,
                        f"unconstrained_upward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Upward gradient

                    # Downward unconstrained gradient (eq. (38))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        >= (
                            -self.delta_q_unconstrained * self.entered_down[t]
                            + self.U[t]
                            + self.D[t]
                            - self.delta_q_unconstrained * self.turned_off[t_next]
                            + q_step * self.turned_on[t_next]
                            + self.START[t] * q_step
                        ),
                        f"unconstrained_downward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Downward gradient

            else:  # Raise an error since no gradients have been detected.
                cfg.logger.error(
                    f"*** WARNING ***\n No gradients have been defined for equipment {self.thermal_unit.name}. \n "
                    "Please check the value of `maximum_gradient`."
                )
                raise ValueError("Missing gradients for thermic units.")

            self.create_daily_energy_constraint(self.thermal_unit, self.time_frame, self.parameters.time_step, self.q)

    def _combination_7(self):
        """Combination 7 : T_stop >= 1, self.T_stable = 0 T_start >= 1"""

        if self.T_stop >= 1 and self.T_start >= 1 and self.T_stable == 0:
            # In this case, there are five state variables and two auxiliary variables.
            # We review the initial conditions, then the constraints on the state variables
            # and finally the constraints on the power output.

            # PREAMBLE
            # Define the down_to_stop auxiliary, which is used in this combination and in combination 2
            down_to_stop = {}
            for t in self.time_frame:
                down_to_stop[t] = self.add_continuous_variable(
                    f"down_to_stop_equip_{self.thermal_unit.name}_at_{t}", 0, 1
                )

            # A. INITIAL CONDITIONS

            # See if the program needs to be initialized as DayZero or not
            if len(self.last_power) == 0:
                # Initialization of the program as DayZero and warn the user
                if self.parameters.verbose:
                    cfg.logger.warning("***WARNING***\n The program is initialized for the first time.")
                day_zero = True  # Boolean to keep track of the status
            elif self.last_date != self.parameters.start_date - self.parameters.time_step:
                # last_date doesn't match start_date - time_step (i.e. t_{-1}, so we will initialize as DayZero and send a warning message
                if self.parameters.verbose:
                    cfg.logger.warning(
                        f"***WARNING***\n The last_date found in Power of equipement {self.thermal_unit.name} "
                        "does not match the start_date of the current program. \n "
                        "The program will be initialized as DayZero."
                    )
                day_zero = True
            else:
                day_zero = False
                # Setting up the initial conditions of the program
            if day_zero:
                # Remind the user how the program has been initialized
                if self.parameters.verbose:
                    cfg.logger.info(
                        f"Initial conditions of unit {self.thermal_unit.name} have been set as in equation (47)."
                    )

                for t in self.previous_time_frame:
                    # Initial conditions on the power output
                    self.q[t] = 0
                    # Initial conditions on the state variables : the unit is OFF
                    self.OFF[t] = 1
                    self.ON_UP[t] = 0
                    self.ON_DOWN[t] = 0
                    self.STOP[t] = 0
                    self.START[t] = 0
                    # Initial conditions on the auxiliary variables
                    self.turned_on[t] = 0
                    self.turned_off[t] = 0
                    down_to_stop[t] = 0
            else:
                # Initial condition on the power output
                for t in self.previous_time_frame:
                    self.q[t] = self.last_power.get_value(t)

                # Initial conditions on the state variables
                for t in self.previous_time_frame:
                    # There are now three cases : either q_t >= q_min, 0 < q_t < q_min or q_t = 0
                    if self.last_power.get_value(t) >= self.thermal_unit.minimum_power.get_value(t):
                        self.OFF[t] = 0
                        self.STOP[t] = 0
                        self.START[t] = 0
                        self.ON_DOWN[t] = 1
                        self.ON_UP[t] = (
                            1
                            # Set both ON states to 1 in order to allow the unit to do whatever it wants as there is no
                        )
                        # stable constraint at this point.
                    elif (
                        self.last_power.get_value(t) > 0
                    ):  # We will below see whether the unit was being turned on or turned off.
                        self.STOP[t] = 1
                        self.START[t] = 1
                        self.OFF[t] = 0
                        self.ON_UP[t] = 0
                        self.ON_DOWN[t] = 0
                    else:
                        self.STOP[t] = 0
                        self.START[t] = 0
                        self.OFF[t] = 1
                        self.ON_UP[t] = 0
                        self.ON_DOWN[t] = 0

                # Distinguish between start-ups and shutdowns
                # discard the extended_start_date only.
                for t in self.previous_time_frame[:-1]:
                    t_prev = t - self.parameters.time_step
                    if self.START[t] == 1:  # Take start or stop, does not matter.
                        if self.q[t] > self.q[t_prev]:  # If the power output increases, then we are starting up.
                            self.STOP[t] = 0
                            self.START[t] = 1
                        elif self.q[t] < self.q[t_prev]:  # otherwise we are shutting down the unit.
                            self.STOP[t] = 1
                            self.START[t] = 0

                            # Initial conditions on the auxiliary variables
                for t in self.previous_time_frame:
                    # Initialize all the values to 0
                    self.turned_on[t] = 0
                    self.turned_off[t] = 0
                    down_to_stop[t] = 0
                    if not t == self.extended_start_date:
                        # Reconstruct potential switches using the state variables
                        t_prev = t - self.parameters.time_step
                        # See if the unit has been turned off
                        if self.STOP[t] - self.STOP[t_prev] == 1:
                            self.turned_off[t] = 1
                        # Or turned on
                        elif self.START[t] - self.START[t_prev] == 1:
                            self.turned_on[t] = 1
                        # Reconstruction of down_to_stop
                        elif self.STOP[t] - self.ON_DOWN[t_prev] == 0:
                            down_to_stop[t] = 1

            # B. CONSTRAINTS ON THE AUXILIARY VARIABLES

            # These constraints define the auxiliary variables. In the first case, there are only two
            # of them : turned_on and turned_off.

            # Constraints on the indicator that the unit has started on t
            # Amounts to leaving the OFF state, due to the mutual exclusion and transition constraints.
            # Enforces eq (3).
            for t in self.time_frame:
                self.add_constraint(self.turned_on[t] <= 1 - self.OFF[t])
                self.add_constraint(self.turned_on[t] <= self.OFF[t - self.parameters.time_step])
                self.add_constraint(
                    self.turned_on[t] >= self.OFF[t - self.parameters.time_step] - self.OFF[t],
                    f"constraints_defining_turned_on_{t}",
                )

            # Constraints on turned_off
            # Defined here when entering the STOP state as in eq. (5) because T_stop > 0
            for t in self.time_frame:
                self.add_constraint(self.turned_off[t] <= 1 - self.STOP[t - self.parameters.time_step])
                self.add_constraint(self.turned_off[t] <= self.STOP[t])
                self.add_constraint(
                    self.turned_off[t] >= self.STOP[t] - self.STOP[t - self.parameters.time_step],
                    f"constraints_defining_turned_off_{t}",
                )

            # Constraints on down_to_stop (eq. (20))
            for t in self.time_frame:
                t_minus_one = t - self.parameters.time_step
                self.add_constraint(down_to_stop[t] <= self.STOP[t])
                self.add_constraint(down_to_stop[t] <= self.ON_DOWN[t_minus_one])
                self.add_constraint(down_to_stop[t] >= self.STOP[t] + self.ON_DOWN[t_minus_one] - 1)

            # C. CONSTRAINTS ON THE STATE VARIABLES

            # Mutual exclusion constraint
            for t in self.time_frame:
                # Defined over the whole time frame
                # Enforces eq. (9)
                self.add_constraint(
                    self.OFF[t] + self.ON_UP[t] + self.ON_DOWN[t] + self.STOP[t] + self.START[t] == 1,
                    f"mutual_exclusion_at_{t}",
                )

            # Transitions:
            # Transitions from OFF to STOP and STOP to ON_DOWN and ON_UP are forbidden
            # Direct transitions from ON_UP and ON_DOWN to OFF are forbidden.
            # Transitions from ON_UP and ON_DOWN to START and START to OFF are forbidden
            # Direct transitions from OFF to ON_UP and ON_DOWN are forbidden.
            for t in self.time_frame:
                t_minus_one = t - self.parameters.time_step
                # STOP to ON (eq. (13))
                self.add_constraint(self.STOP[t_minus_one] + self.ON_UP[t] <= 1)
                self.add_constraint(self.STOP[t_minus_one] + self.ON_DOWN[t] <= 1)
                # OFF to STOP (eq. (12))
                self.add_constraint(self.OFF[t_minus_one] + self.STOP[t] <= 1)
                # ON to OFF (eq.(18) )
                self.add_constraint(self.ON_UP[t_minus_one] + self.OFF[t] <= 1)
                self.add_constraint(self.ON_DOWN[t_minus_one] + self.OFF[t] <= 1)
                # ON to START (eq. (10))
                self.add_constraint(self.ON_UP[t_minus_one] + self.START[t] <= 1)
                self.add_constraint(self.ON_DOWN[t_minus_one] + self.START[t] <= 1)
                # START to OFF (eq. (11))
                self.add_constraint(self.START[t_minus_one] + self.OFF[t] <= 1)
                # START to STOP and STOP to START (eq. (14))
                self.add_constraint(self.START[t_minus_one] + self.STOP[t] <= 1)
                self.add_constraint(self.STOP[t_minus_one] + self.START[t] <= 1)
                # OFF to ON (eq. (15))
                self.add_constraint(self.OFF[t_minus_one] + self.ON_UP[t] <= 1)
                self.add_constraint(
                    self.OFF[t_minus_one] + self.ON_DOWN[t] <= 1,
                    f"transitions_constraints_at_{t}",
                )

                # Eviction constraints.
            for t in self.time_frame:
                # Define t - T_start and t - T_stop.
                t_minus_T_start = t - self.T_start * self.parameters.time_step
                t_minus_T_stop = t - self.T_stop * self.parameters.time_step
                # Add the constraints.
                # Implements equation (16)
                self.add_constraint(
                    self.turned_on[t_minus_T_start] + self.START[t] <= 1,
                    f"START_eviction_constraint_at_{t}",
                )
                # Implements equation (19)
                self.add_constraint(
                    self.turned_off[t_minus_T_stop] + self.STOP[t] <= 1,
                    f"STOP_eviction_constraint_at_{t}",
                )

            # Mininum time on and minimum time off constraints:
            # if self.T_on >= 2, self.T_off >= 2 or T_stop >= 2, lock the unit in this state.
            if self.T_on >= 2:
                for t in self.time_frame:
                    time_steps = range(1, self.T_on)
                    for s in time_steps:
                        # Enforces eq. (31) with T_start > 0
                        t_minus_s_minus_T_start = (
                            t - s * self.parameters.time_step - self.T_start * self.parameters.time_step
                        )
                        self.add_constraint(
                            self.turned_on[t_minus_s_minus_T_start] <= self.ON_UP[t] + self.ON_DOWN[t],
                            f"minimum_time_ON_{self.thermal_unit.name}_at_{t_minus_s_minus_T_start}_for_{t}",
                        )
            if self.T_off >= 2:
                for t in self.time_frame:
                    time_steps = range(1, self.T_off)
                    for s in time_steps:
                        # Enforces eq. (32) with T_stop > 0
                        # Shift the index because the OFF is formally considered when entering the STOP state.
                        t_minus_s_minus_T_stop = (
                            t - s * self.parameters.time_step - self.T_stop * self.parameters.time_step
                        )
                        self.add_constraint(
                            self.turned_off[t_minus_s_minus_T_stop] <= self.OFF[t],
                            f"minimum_time_OFF_{self.thermal_unit.name}_at_{t_minus_s_minus_T_stop}_for_{t}",
                        )
            if self.T_stop >= 2:
                for t in self.time_frame:
                    for s in self.stop_time_steps:
                        # Enforces eq. (24)
                        t_minus_s = t - s * self.parameters.time_step
                        self.add_constraint(
                            self.turned_off[t_minus_s] <= self.STOP[t],
                            f"shutdown_ramp_of_{self.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                        )
            if self.T_start >= 2:
                for t in self.time_frame:
                    for s in self.start_time_steps:
                        # Enforces eq. (17)
                        t_minus_s = t - s * self.parameters.time_step
                        self.add_constraint(
                            self.turned_on[t_minus_s] <= self.START[t],
                            f"start_up_ramp_of_{self.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                        )

            # D. CONSTRAINTS ON THE CONTROL VARIABLE

            # Shutdown and start_up gradients
            q_min = self.thermal_unit.minimum_power.max()  # Get the minimum_power without the reserve requirements
            q_step_up = q_min / self.T_start
            q_step_down = q_min / self.T_stop

            # Reserves requirements
            # We are in a case where there is no FLAT state, so manual reserves can be provided
            # as long as the unit is online.

            # Constraints on contractedDifference (eq. (40)) and on automatedContractedDifference (eq. (39))
            self.create_contracted_diff_constraints(
                self.time_frame,
                self.contracted_difference_up,
                self.reserves_up_procured,
                self.reserves_up,
                self.contracted_difference_down,
                self.reserves_down_procured,
                self.reserves_down,
                self.automated_contracted_difference_up,
                self.feasible_automated_reserves_up_procured,
                self.automated_reserves_up,
                self.automated_contracted_difference_down,
                self.feasible_automated_reserves_down_procured,
                self.automated_reserves_down,
            )

            # Upward and downward "fill up" constraints.
            self.create_fill_up_constraints(
                self.time_frame,
                self.q,
                self.reserves_up,
                self.automated_reserves_up,
                self.unprovided_reserves_up,
                self.q_upper,
                self.parameters.epsilon,
                self.reserves_down,
                self.automated_reserves_down,
                self.unprovided_reserves_down,
                self.relaxed_reserves,
                self.q_lower,
            )

            # relaxedReserve disabling condition (eq. (43))
            for t in self.time_frame:
                self.add_constraint(
                    self.relaxed_reserves[t] <= self.q_lower.get_value(t) * (1 - self.ON_UP[t] - self.ON_DOWN[t])
                )

            # impossible commitment and stable reserves constraints (eq. (44))
            for t in self.time_frame:
                self.add_constraint(
                    self.automated_reserves_up[t]
                    <= self.maximum_automated * (1 - self.OFF[t] - self.START[t] - self.STOP[t])
                )
                self.add_constraint(
                    self.automated_reserves_down[t]
                    <= self.maximum_automated * (1 - self.OFF[t] - self.START[t] - self.STOP[t])
                )
                self.add_constraint(
                    self.reserves_up[t] <= self.q_upper.get_value(t) * (1 - self.OFF[t] - self.START[t] - self.STOP[t])
                )
                self.add_constraint(
                    self.reserves_down[t]
                    <= self.q_upper.get_value(t) * (1 - self.OFF[t] - self.START[t] - self.STOP[t])
                )

            # Power output
            for t in self.time_frame:
                self.add_constraint(
                    self.q[t]
                    >= self.q_lower.get_value(t) * (self.ON_UP[t] + self.ON_DOWN[t])
                    + self.turned_off[t] * (q_min - q_step_down),
                    f"lower_bound_of_{self.thermal_unit.name}_at_{t}",
                )
                # Lower bound (eq. (33))
                self.add_constraint(
                    self.q[t]
                    <= self.q_upper.get_value(t) * (self.ON_UP[t] + self.ON_DOWN[t])
                    + self.STOP[t] * q_min
                    + self.START[t] * q_min
                    - self.turned_off[t] * q_step_down,
                    f"upper_bound_of_{self.thermal_unit.name}_at_{t}",
                )
                # Upper bound (eq. (34))

            if self.delta_q > 0:  # Case where the gradient is finite.
                for t in self.gradients_time_frame:  # The gradients are defined only up to T-1.
                    # NB. The downward gradient implemented here requires the unit to be at most at deltaQ in order to be able to enter the stop state.
                    # The resulting constraint set is considerably more constraining than if the gradient was relaxed.
                    t_next = t + self.parameters.time_step  # Get the next time step

                    # Upward constrained gradient (eq. (35))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        <= (
                            self.delta_q * self.ON_UP[t]
                            - self.turned_off[t_next] * q_step_down
                            - self.STOP[t] * q_step_down
                            + self.turned_on[t_next] * q_step_up
                            + self.START[t] * q_step_up
                        ),
                        f"upward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Upward gradient

                    # Downward constrained gradient (eq. (37))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        >= (
                            -self.delta_q * self.ON_DOWN[t]
                            - self.turned_off[t_next] * q_step_down
                            - self.STOP[t] * q_step_down
                            + down_to_stop[t_next] * self.delta_q
                            + self.turned_on[t_next] * q_step_up
                            + self.START[t] * q_step_up
                        ),
                        f"downward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Downward gradient
            elif self.delta_q == 0:
                for t in self.gradients_time_frame:
                    t_next = t + self.parameters.time_step

                    # Upward unconstrained gradient (eq. (36))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        <= (
                            self.delta_q_unconstrained * self.ON_UP[t]
                            - self.turned_off[t_next] * q_step_down
                            - self.STOP[t] * q_step_down
                            + self.turned_on[t_next] * q_step_up
                            + self.START[t] * q_step_up
                        ),
                        f"unconstrained_upward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Upward gradient

                    # Downward unconstrained gradient (eq. (38))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        >= (
                            -self.delta_q_unconstrained * self.ON_DOWN[t]
                            - self.turned_off[t_next] * q_step_down
                            - self.STOP[t] * q_step_down
                            + down_to_stop[t_next] * self.delta_q_unconstrained
                            + self.turned_on[t_next] * q_step_up
                            + self.START[t] * q_step_up
                        ),
                        f"unconstrained_downward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Downward gradient
            else:  # Raise an error since no gradients have been detected.
                cfg.logger.error(
                    f"*** WARNING ***\n No gradients have been defined for equipment {self.thermal_unit.name}. \n "
                    "Please check the value of `maximum_gradient`."
                )
                raise ValueError("Missing gradients for thermic units.")

            self.create_daily_energy_constraint(self.thermal_unit, self.time_frame, self.parameters.time_step, self.q)

    def _combination_8(self):
        """Combination 8 : T_start = self.T_stable = T_stop >= 1"""

        if self.T_stop >= 1 and self.T_start >= 1 and self.T_stable >= 1:
            # In this case, there are six state variables and the following auxiliary variables :
            #     - turned_on[t] and turned_off[t], indicating whether the unit has been turned on or off
            #     - stable[t], indicating whether the unit entered the stable state
            #     - U[t] and D[t], implemented in two stages with tilde_D[t], tilde_D[t] as the first stage
            #     - entered_up[t] and entered_down[t] indicating that the unit entered the UP or down STATE
            #
            # We also need the gradient auxiliaries DD[t] and flat_down_stop[t] to follow the shut down procedure of
            # the unit.
            #
            # We review the initial conditions, then the constraints on the state variables
            # and finally the constraints on the power output.

            # PREAMBLE
            # Definition of two additional auxiliary variables needed specifically to handle this case,
            # flat_down_stop, which detects when the unit follows a FLAT(t-2) - DOWN(t-1) and STOP(t) path
            # and DD, which detects if the unit is to be stopped at t+1 (i.e. STOP(t+1) = 1) after having been
            # in the DOWN state at time steps t and t-1.

            # flat_down_stop
            flat_down_stop = {}
            for t in self.time_frame:
                flat_down_stop[t] = self.add_continuous_variable(
                    f"flat_down_stop_at_{t}_equip_{self.thermal_unit.name}",
                    0,
                    1,
                )

            DD = {}
            for t in self.gradients_time_frame:
                DD[t] = self.add_continuous_variable(f"DD_{t}_equip_{self.thermal_unit.name}", self.Q_min, self.Q_max)

            # A. INITIAL CONDITIONS

            # Define the start_date - 2 time steps.
            start_date_minus_two = self.parameters.start_date - 2 * self.parameters.time_step

            # See if the program needs to be initialized as DayZero or not
            if len(self.last_power) == 0:
                # Initialization of the program as DayZero and warn the user
                cfg.logger.warning("***WARNING***\n The program is initialized for the first time.")
                day_zero = True  # Boolean to keep track of the status
            elif self.last_date != self.parameters.start_date - self.parameters.time_step:
                # last_date doesn't match start_date - time_step (i.e. t_{-1}, so we will initialize as DayZero and send a warning message
                cfg.logger.warning(
                    f"***WARNING***\n The last_date found in Power of equipement {self.thermal_unit.name} "
                    "does not match the start_date of the current program. \n "
                    "The program will be initialized as DayZero."
                )
                day_zero = True
            else:
                day_zero = False
                # Setting up the initial conditions of the program
            if day_zero:
                # Remind the user how the program has been initialized
                cfg.logger.info(
                    f"Initial conditions of unit {self.thermal_unit.name} have been set as in equation (47)."
                )

                for t in self.previous_time_frame:
                    # Initial conditions on the power output
                    self.q[t] = 0
                    # Initial conditions on the state variables : the unit is OFF
                    self.OFF[t] = 1
                    self.STOP[t] = 0
                    self.START[t] = 0
                    if not t == self.start_date_minus_one:
                        self.ON_UP[t] = 0
                        self.ON_DOWN[t] = 0
                        self.ON_FLAT[t] = 0
                        # Initial conditions on the auxiliary variables defined over time_frame_union_minus_one
                        self.stable[t] = 0
                        self.entered_up[t] = 0
                        self.entered_down[t] = 0

                    # Initial conditions on the remaining auxiliary variables
                    self.turned_on[t] = 0
                    self.turned_off[t] = 0
                    flat_down_stop[t] = 0
            else:
                # Setting up the initial conditions will be a bit more complex. We consecutively do the following:
                #    - Set the inital conditions on the power output
                #    - See wether the unit is ON or OFF
                #    - Initialize the auxiliaries turned_up and turned_down accordingly
                #    - For the steps where the unit is ON:
                #         - See whether the unit was UP, DOWN or FLAT
                #         - Initialize the auxiliary variables accordingly

                # Initial condition on the power output
                for t in self.previous_time_frame:
                    self.q[t] = self.last_power.get_value(t)

                # Initial conditions on the state variables OFF/ON
                for t in self.previous_time_frame:
                    if self.last_power.get_value(t) >= self.thermal_unit.minimum_power.get_value(t):
                        self.OFF[t] = (
                            0  # Only the OFF and STOP variables are initialized. ON_FLAT, ON_DOWN and ON_UP will be
                        )
                        # initialized afterwards.
                        self.STOP[t] = 0
                        self.START[t] = 0
                    elif self.last_power.get_value(t) > 0:
                        self.OFF[t] = 0
                        self.STOP[t] = 1  # Set both START and STOP at 1 for now, will be distinguished afterwards.
                        self.START[t] = 1
                        if not t == self.start_date_minus_one:
                            self.ON_UP[t] = 0
                            self.ON_DOWN[t] = 0
                            self.ON_FLAT[t] = 0
                    else:
                        self.OFF[t] = 1
                        self.STOP[t] = 0
                        self.START[t] = 0
                        if not t == self.start_date_minus_one:
                            self.ON_UP[t] = 0
                            self.ON_DOWN[t] = 0
                            self.ON_FLAT[t] = 0

                            # Distinguish between start-ups and shutdowns
                # discard the extended_start_date only.
                for t in self.previous_time_frame[:-1]:
                    t_prev = t - self.parameters.time_step
                    if self.START[t] == 1:  # Take start or stop, does not matter.
                        if self.q[t] > self.q[t_prev]:  # If the power output increases, then we are starting up.
                            self.STOP[t] = 0
                            self.START[t] = 1
                        elif self.q[t] < self.q[t_prev]:  # otherwise we are shutting down the unit.
                            self.STOP[t] = 1
                            self.START[t] = 0

                            # Initial conditions on the auxiliary variables turned_on turned_off
                for t in self.previous_time_frame:
                    # Initialize all the values to 0
                    self.turned_on[t] = 0
                    self.turned_off[t] = 0
                    if not t == self.extended_start_date:
                        # Reconstruct potential switches using the state variables
                        t_prev = t - self.parameters.time_step
                        # See if the unit has been turned off
                        if self.STOP[t] - self.STOP[t_prev] == 1:
                            self.turned_off[t] = 1
                        # Or turned on
                        elif self.START[t] - self.START[t_prev] == 1:
                            self.turned_on[t] = 1

                # Reconstruct the values of UP, DOWN and FLAT and their associated
                # auxiliary variables
                for t in self.previous_time_frame[
                    :-1
                ]:  # Loop excluding last date because we are reconstructing the values of the
                    # ON variables using  variations between q[t] and q[t-1].

                    t_prev = t - self.parameters.time_step
                    if self.OFF[t_prev] == 0:
                        # See if the power output was stable, increasing or decreasing:
                        if self.q[t] > self.q[t_prev]:  # Recall that here t_prev is earlier than t.
                            self.ON_UP[t_prev] = 1
                            self.ON_DOWN[t_prev] = 0
                            self.ON_FLAT[t_prev] = 0
                        elif self.q[t] < self.q[t_prev]:
                            self.ON_UP[t_prev] = 0
                            self.ON_DOWN[t_prev] = 1
                            self.ON_FLAT[t_prev] = 0
                        elif self.q[t] == self.q[t_prev]:
                            self.ON_UP[t_prev] = 0
                            self.ON_DOWN[t_prev] = 0
                            self.ON_FLAT[t_prev] = 1

                # Initialize the auxiliary variables
                for t in self.previous_time_frame[
                    1:
                ]:  # Loop excluding start_date_minus_one, which is the first element in the previous_time_frame list.
                    # Default value set to 0
                    self.stable[t] = 0
                    self.entered_up[t] = 0
                    self.entered_down[t] = 0

                    if (not t == self.extended_start_date) and (not self.OFF[t] == 1):
                        t_prev = t - self.parameters.time_step

                        # See if the unit entered the FLAT state
                        if self.ON_FLAT[t] - self.ON_FLAT[t_prev] == 1:
                            self.stable[t] = 1
                        # or the UP state
                        if self.ON_UP[t] - self.ON_UP[t_prev] == 1:
                            self.entered_up[t] = 1
                        # or the DOWN state
                        if self.ON_DOWN[t] - self.ON_DOWN[t_prev] == 1:
                            self.entered_down[t] = 1

                # Initialize flat_down_stop.
                for t in self.previous_time_frame[:-2]:
                    # Moreover, if we are after extended_start_date + time_step
                    # initialize flat_down_stop (which traces back up to two time index before)
                    t_minus_one = t - self.parameters.time_step
                    t_minus_two = t - 2 * self.parameters.time_step
                    flat_down_stop[t] = int(
                        math.floor((self.STOP[t] + self.ON_DOWN[t_minus_one] + self.ON_FLAT[t_minus_two]) / 3)
                    )

                    # Initialize the gradient auxiliaries. This is only required for the last time step of the
            # previous_time_frame. Only ON_UP[start_date_minus_one] and ON_DOWN[start_date_minus_one] are decision variables
            # in the expressions below.
            self.U[self.start_date_minus_one] = (
                self.ON_UP[self.start_date_minus_one]
                * self.ON_UP[start_date_minus_two]
                * (self.q[self.start_date_minus_one] - self.q[start_date_minus_two])
            )
            self.D[self.start_date_minus_one] = (
                self.ON_DOWN[self.start_date_minus_one]
                * self.ON_DOWN[start_date_minus_two]
                * (self.q[self.start_date_minus_one] - self.q[start_date_minus_two])
            )

            # B. CONSTRAINTS ON THE AUXILIARY VARIABLES

            # These constraints define the auxiliary variables. In the first case, there are only two
            # of them : turned_on and turned_off.

            # Constraints on the indicator that the unit has started on t
            # Enforces eq. (3)
            for t in self.time_frame:
                self.add_constraint(self.turned_on[t] <= 1 - self.OFF[t])
                self.add_constraint(self.turned_on[t] <= self.OFF[t - self.parameters.time_step])
                self.add_constraint(self.turned_on[t] >= self.OFF[t - self.parameters.time_step] - self.OFF[t])

                # Constraints on turned_off
            # Enforces eq. (5)
            for t in self.time_frame:
                self.add_constraint(self.turned_off[t] <= 1 - self.STOP[t - self.parameters.time_step])
                self.add_constraint(self.turned_off[t] <= self.STOP[t])
                self.add_constraint(self.turned_off[t] >= self.STOP[t] - self.STOP[t - self.parameters.time_step])

            # stable auxiliary variable
            # Enforces eq. (6)
            for t in self.time_frame_union_minus_one:
                self.add_constraint(self.stable[t] <= 1 - self.ON_FLAT[t - self.parameters.time_step])
                self.add_constraint(self.stable[t] <= self.ON_FLAT[t])
                self.add_constraint(self.stable[t] >= self.ON_FLAT[t] - self.ON_FLAT[t - self.parameters.time_step])

            # flat_down_stop auxiliary (eq. (22))
            for t in self.time_frame:
                t_minus_one = t - self.parameters.time_step
                t_minus_two = t - 2 * self.parameters.time_step
                self.add_constraint(flat_down_stop[t] <= self.STOP[t])
                self.add_constraint(flat_down_stop[t] <= self.ON_DOWN[t_minus_one])
                self.add_constraint(flat_down_stop[t] <= self.ON_FLAT[t_minus_two])
                self.add_constraint(
                    flat_down_stop[t] >= self.STOP[t] + self.ON_DOWN[t_minus_one] + self.ON_FLAT[t_minus_two] - 2
                )

            # entered_up and entered_down auxiliaries (defined in sections 6.1.4 and 6.1.5)
            for t in self.time_frame_union_minus_one:
                # entered_up (eq. (7))
                self.add_constraint(self.entered_up[t] <= 1 - self.ON_UP[t - self.parameters.time_step])
                self.add_constraint(self.entered_up[t] <= self.ON_UP[t])
                self.add_constraint(self.entered_up[t] >= self.ON_UP[t] - self.ON_UP[t - self.parameters.time_step])
                # entered_down (eq. (8))
                self.add_constraint(self.entered_down[t] <= 1 - self.ON_DOWN[t - self.parameters.time_step])
                self.add_constraint(self.entered_down[t] <= self.ON_DOWN[t])
                self.add_constraint(
                    self.entered_down[t] >= self.ON_DOWN[t] - self.ON_DOWN[t - self.parameters.time_step]
                )

            # UP and DOWN auxiliary variables for the gradient.
            # These auxiliary variables model the fact that if the unit is increasing (decreasing) its
            # power output twice in a row, then the second time the gradient is locked.
            # In practice, these variables are defined in two stages

            # First stage : tilde_U and tilde_D
            for t in self.time_frame:  # Loop in all the time_frame but start_date.
                t_minus_one = t - self.parameters.time_step
                # tilde_U (eq. (28))
                self.add_constraint(self.tilde_U[t] <= self.Q_max * self.ON_UP[t_minus_one])
                self.add_constraint(self.tilde_U[t] >= self.Q_min * self.ON_UP[t_minus_one])
                self.add_constraint(
                    self.tilde_U[t] <= self.q[t] - self.q[t_minus_one] - self.Q_min * (1 - self.ON_UP[t_minus_one])
                )
                self.add_constraint(
                    self.tilde_U[t] >= self.q[t] - self.q[t_minus_one] - self.Q_max * (1 - self.ON_UP[t_minus_one]),
                    f"VALUE_of_tilde_UP_at_{t}",
                )

                # tilde_D (eq. (30))
                self.add_constraint(self.tilde_D[t] <= self.Q_max * self.ON_DOWN[t_minus_one])
                self.add_constraint(self.tilde_D[t] >= self.Q_min * self.ON_DOWN[t_minus_one])
                self.add_constraint(
                    self.tilde_D[t] <= self.q[t] - self.q[t_minus_one] - self.Q_min * (1 - self.ON_DOWN[t_minus_one])
                )
                self.add_constraint(
                    self.tilde_D[t] >= self.q[t] - self.q[t_minus_one] - self.Q_max * (1 - self.ON_DOWN[t_minus_one]),
                    f"VALUE_of_tilde_DOWN_at_{t}",
                )

            # Second stage : U and D
            # These variables wil be added to the gradient constraints.
            for t in self.time_frame:
                # U (eq. (27))
                self.add_constraint(self.U[t] <= self.Q_max * self.ON_UP[t])
                self.add_constraint(self.U[t] >= self.Q_min * self.ON_UP[t])
                self.add_constraint(self.U[t] <= self.tilde_U[t] - self.Q_min * (1 - self.ON_UP[t]))
                self.add_constraint(
                    self.U[t] >= self.tilde_U[t] - self.Q_max * (1 - self.ON_UP[t]),
                    f"VALUE_of_UP_at_{t}",
                )
                # D (eq. (29))
                self.add_constraint(self.D[t] <= self.Q_max * self.ON_DOWN[t])
                self.add_constraint(self.D[t] >= self.Q_min * self.ON_DOWN[t])
                self.add_constraint(self.D[t] <= self.tilde_D[t] - self.Q_min * (1 - self.ON_DOWN[t]))
                self.add_constraint(
                    self.D[t] >= self.tilde_D[t] - self.Q_max * (1 - self.ON_DOWN[t]),
                    f"VALUE_of_DOWN_at_{t}",
                )

            # DD Gradient auxiliary (eq. (23))
            for t in self.gradients_time_frame:
                t_plus_one = t + self.parameters.time_step
                self.add_constraint(DD[t] <= self.Q_max * self.STOP[t_plus_one])
                self.add_constraint(DD[t] >= self.Q_min * self.STOP[t_plus_one])
                self.add_constraint(DD[t] <= self.D[t] - self.Q_min * (1 - self.STOP[t_plus_one]))
                self.add_constraint(
                    DD[t] >= self.D[t] - self.Q_max * (1 - self.STOP[t_plus_one]),
                    f"DD_gradient_auxiliary_at_{t}",
                )

            # C. CONSTRAINTS ON THE STATE VARIABLES

            # Mutual exclusion constraint
            for t in self.time_frame_union_minus_one:
                # Defined over the whole time frame.
                # Enforces eq. (9)
                self.add_constraint(
                    self.OFF[t] + self.ON_UP[t] + self.ON_DOWN[t] + self.ON_FLAT[t] + self.STOP[t] + self.START[t] == 1,
                    f"mutual_exclusion_at_{t}",
                )

            # Transitions:
            # UP-DOWN and DOWN-UP transitions are forbidden.
            # STOP to ON transitions are also forbidden
            # OFF to STOP transitions
            # START to OFF
            # ON to START
            # START to STOP and STOP to START
            # OFF to ON
            # Finally, we forbid ON_UP to STOP (which never happens in practice) in order
            # to avoid defining a UU auxiliary analoguous to DD.
            for t in self.time_frame_union_minus_one:
                t_minus_one = t - self.parameters.time_step
                # Implement eq. (25).
                self.add_constraint(self.ON_UP[t_minus_one] + self.ON_DOWN[t] <= 1)
                self.add_constraint(self.ON_DOWN[t_minus_one] + self.ON_UP[t] <= 1)
                # STOP to ON (eq. (13))
                self.add_constraint(self.STOP[t_minus_one] + self.ON_FLAT[t] <= 1)
                self.add_constraint(self.STOP[t_minus_one] + self.ON_DOWN[t] <= 1)
                self.add_constraint(
                    self.STOP[t_minus_one] + self.ON_UP[t] <= 1,
                    f"transitions_constraints_on_timeFrame_union_minus_one_at_{t}",
                )
            for t in self.time_frame:
                t_minus_one = t - self.parameters.time_step
                # ON_UP to STOP transition (eq. (21))
                self.add_constraint(self.ON_UP[t_minus_one] + self.STOP[t] <= 1)
                # OFF to STOP (eq. (13)).
                self.add_constraint(self.OFF[t_minus_one] + self.STOP[t] <= 1)
                # ON to START (eq. (10))
                self.add_constraint(self.ON_UP[t_minus_one] + self.START[t] <= 1)
                self.add_constraint(self.ON_DOWN[t_minus_one] + self.START[t] <= 1)
                self.add_constraint(self.ON_FLAT[t_minus_one] + self.START[t] <= 1)
                # START to OFF (eq. (11))
                self.add_constraint(self.START[t_minus_one] + self.OFF[t] <= 1)
                # START to STOP and STOP to START (eq. (14))
                self.add_constraint(self.START[t_minus_one] + self.STOP[t] <= 1)
                self.add_constraint(self.STOP[t_minus_one] + self.START[t] <= 1)
                # OFF to ON (eq. (15))
                self.add_constraint(self.OFF[t_minus_one] + self.ON_UP[t] <= 1)
                self.add_constraint(self.OFF[t_minus_one] + self.ON_FLAT[t] <= 1)
                self.add_constraint(
                    self.OFF[t_minus_one] + self.ON_DOWN[t] <= 1,
                    f"transitions_constraints_at_{t}",
                )
                # The latter constraints are only defined on the time_frame because it does not involve ON variables at the t index.

            # Eviction constraints
            # The unit must leave the STOP state after T_stop time steps.
            # and the START state after T_start time steps.
            for t in self.time_frame:
                t_minus_T_stop = t - self.T_stop * self.parameters.time_step
                t_minus_T_start = t - self.T_start * self.parameters.time_step
                # Implements equation (19)
                self.add_constraint(
                    self.turned_off[t_minus_T_stop] + self.STOP[t] <= 1,
                    f"STOP_eviction_constraint_at_{t}",
                )
                # Implements equation (16)
                self.add_constraint(
                    self.turned_on[t_minus_T_start] + self.START[t] <= 1,
                    f"START_eviction_constraint_at_{t}",
                )

                # Mininum time on and minimum time off constraints:
            # if self.T_on >= 2 or self.T_off >= 2 or self.T_stable >= 2, lock the unit in this state.
            if self.T_on >= 2:
                for t in self.time_frame_union_minus_one:
                    time_steps = range(1, self.T_on)  # Corresponds to the set {1,..., self.T_on - 1}
                    for s in time_steps:
                        # Enforces eq. (31), with T_start > 0
                        t_minus_s_minus_T_start = (
                            t - s * self.parameters.time_step - self.T_start * self.parameters.time_step
                        )
                        self.add_constraint(
                            self.turned_on[t_minus_s_minus_T_start]
                            <= self.ON_UP[t] + self.ON_DOWN[t] + self.ON_FLAT[t],
                            f"minimum_time_ON_{self.thermal_unit.name}_at_{t_minus_s_minus_T_start}_for_{t}",
                        )
            if self.T_off >= 2:
                for t in self.time_frame:
                    time_steps = range(1, self.T_off)  # Corresponds to the set {1,..., self.T_off - 1}
                    for s in time_steps:
                        # Enforces eq. (32) with T_stop > 0
                        t_minus_s_minus_T_stop = (
                            t - s * self.parameters.time_step - self.T_stop * self.parameters.time_step
                        )
                        self.add_constraint(
                            self.turned_off[t_minus_s_minus_T_stop] <= self.OFF[t],
                            f"minimum_time_OFF_{self.thermal_unit.name}_at_{t_minus_s_minus_T_stop}_for_{t}",
                        )
            if self.T_stable >= 2:
                for t in self.time_frame_union_minus_one:
                    time_steps = range(1, self.T_stable - 1)  # Corresponds to the set {1,..., self.T_stable - 2}
                    for s in time_steps:
                        # Enforces eq. (26)
                        t_minus_s = t - s * self.parameters.time_step
                        self.add_constraint(
                            self.stable[t_minus_s] <= self.ON_FLAT[t],
                            f"minimum_time_STABLE_{self.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                        )
            if self.T_stop >= 2:
                for t in self.time_frame:
                    for s in self.stop_time_steps:
                        t_minus_s = t - s * self.parameters.time_step
                        # Enforces eq. (24)
                        self.add_constraint(
                            self.turned_off[t_minus_s] <= self.STOP[t],
                            f"shutdown_ramp_of_{self.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                        )
            if self.T_start >= 2:
                for t in self.time_frame:
                    for s in self.start_time_steps:
                        t_minus_s = t - s * self.parameters.time_step
                        # Enforces eq. (17)
                        self.add_constraint(
                            self.turned_on[t_minus_s] <= self.START[t],
                            f"start_up_ramp_of_{self.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                        )

            # D. CONSTRAINTS ON THE CONTROL VARIABLE

            # Start-up gradient:
            q_min = self.thermal_unit.minimum_power.max()
            q_step_down = q_min / self.T_stop
            q_step_up = q_min / self.T_start

            # Reserves requirements
            # We are in a case where there is a FLAT state, so manual reserves can only be provided
            # when the unit is in the FLAT state.

            # Constraints on contractedDifference (eq. (40)) and on automatedContractedDifference (eq. (39))
            self.create_contracted_diff_constraints(
                self.time_frame,
                self.contracted_difference_up,
                self.reserves_up_procured,
                self.reserves_up,
                self.contracted_difference_down,
                self.reserves_down_procured,
                self.reserves_down,
                self.automated_contracted_difference_up,
                self.feasible_automated_reserves_up_procured,
                self.automated_reserves_up,
                self.automated_contracted_difference_down,
                self.feasible_automated_reserves_down_procured,
                self.automated_reserves_down,
            )

            # Upward and downward "fill up" constraints.
            self.create_fill_up_constraints(
                self.time_frame,
                self.q,
                self.reserves_up,
                self.automated_reserves_up,
                self.unprovided_reserves_up,
                self.q_upper,
                self.parameters.epsilon,
                self.reserves_down,
                self.automated_reserves_down,
                self.unprovided_reserves_down,
                self.relaxed_reserves,
                self.q_lower,
            )

            # relaxedReserve disabling condition (eq. (43))
            for t in self.time_frame:
                self.add_constraint(
                    self.relaxed_reserves[t]
                    <= self.q_lower.get_value(t) * (1 - self.ON_UP[t] - self.ON_FLAT[t] - self.ON_DOWN[t])
                )

            # impossible commitment and stable reserves constraints (eqs. (44) and (45))
            for t in self.time_frame:
                self.add_constraint(
                    self.automated_reserves_up[t]
                    <= self.maximum_automated * (1 - self.OFF[t] - self.START[t] - self.STOP[t])
                )
                self.add_constraint(
                    self.automated_reserves_down[t]
                    <= self.maximum_automated * (1 - self.OFF[t] - self.START[t] - self.STOP[t])
                )
                self.add_constraint(
                    self.reserves_up[t]
                    <= self.q_upper.get_value(t)
                    * (1 - self.ON_UP[t] - self.ON_DOWN[t] - self.OFF[t] - self.START[t] - self.STOP[t])
                )
                # for compacity, implements both eq (44) and (45)
                self.add_constraint(
                    self.reserves_down[t]
                    <= self.q_upper.get_value(t)
                    * (1 - self.ON_UP[t] - self.ON_DOWN[t] - self.OFF[t] - self.START[t] - self.STOP[t])
                )

            # Power output
            for t in self.time_frame:
                self.add_constraint(
                    self.q[t]
                    >= self.q_lower.get_value(t) * (self.ON_UP[t] + self.ON_DOWN[t] + self.ON_FLAT[t])
                    + self.turned_off[t] * (q_min - q_step_down),
                    f"lower_bound_of_{self.thermal_unit.name}_at_{t}",
                )  # Lower bound (eq. (33))
                self.add_constraint(
                    self.q[t]
                    <= self.q_upper.get_value(t) * (self.ON_UP[t] + self.ON_DOWN[t] + self.ON_FLAT[t])
                    + (self.STOP[t] + self.START[t]) * q_min
                    - self.turned_off[t] * q_step_down,
                    f"upper_bound_of_{self.thermal_unit.name}_at_{t}",
                )  # Upper bound (eq. (34))

            # Power gradients
            if self.delta_q > 0:  # Case where the gradient is finite.
                for t in self.gradients_time_frame:  # The gradients are defined only up to T-1.
                    t_next = t + self.parameters.time_step  # Get the next time step

                    # Upward constrained gradient (eq. (35))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        <= (
                            self.delta_q * self.entered_up[t]
                            + self.U[t]
                            + self.D[t]
                            - q_step_down * self.turned_off[t_next]
                            - self.STOP[t] * q_step_down
                            + q_step_up * self.turned_on[t_next]
                            + self.START[t] * q_step_up
                            - DD[t]
                        ),
                        f"upward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Upward gradient

                    # Downward constrained gradient (eq. (37))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        >= (
                            -self.delta_q * self.entered_down[t]
                            + self.U[t]
                            + self.D[t]
                            - q_step_down * self.turned_off[t_next]
                            - self.STOP[t] * q_step_down
                            + flat_down_stop[t_next] * self.delta_q
                            - DD[t]
                            + q_step_up * self.turned_on[t_next]
                            + self.START[t] * q_step_up
                        ),
                        f"downward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Downward gradient

            elif self.delta_q == 0:  # Case where the gradient is 'infinite'
                for t in self.gradients_time_frame:
                    t_next = t + self.parameters.time_step  # Get the next time step

                    # Upward unconstrained gradient (eq. (36))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        <= (
                            self.delta_q_unconstrained * self.entered_up[t]
                            + self.U[t]
                            + self.D[t]
                            - q_step_down * self.turned_off[t_next]
                            - self.STOP[t] * q_step_down
                            + q_step_up * self.turned_on[t_next]
                            + self.START[t] * q_step_up
                            - DD[t]
                        ),
                        f"upward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Upward gradient

                    # Downward unconstrained gradient (eq. (38))
                    self.add_constraint(
                        self.q[t_next] - self.q[t]
                        >= (
                            -self.delta_q_unconstrained * self.entered_down[t]
                            + self.U[t]
                            + self.D[t]
                            - q_step_down * self.turned_off[t_next]
                            - self.STOP[t] * q_step_down
                            + flat_down_stop[t_next] * self.delta_q_unconstrained
                            - DD[t]
                            + q_step_up * self.turned_on[t_next]
                            + self.START[t] * q_step_up
                        ),
                        f"downward_gradient_of_{self.thermal_unit.name}_at_{t}",
                    )  # Downward gradient

            else:  # Raise an error since no gradients have been detected.
                cfg.logger.error(
                    f"*** WARNING ***\n No gradients have been defined for equipment {self.thermal_unit.name}. \n "
                    "Please check the value of `maximum_gradient`."
                )
                raise ValueError("Missing gradients for thermic units.")

            self.create_daily_energy_constraint(self.thermal_unit, self.time_frame, self.parameters.time_step, self.q)

    def solve_thermal_optimization_program(self):
        """
        STEP 4 : Solving the problem
        :return: - `results`: a dictionnary containing the optimal values of the decision variables,
                    namely :
                        . q*, the optimal power output
                        . ON_.*, OFF*, START* and STOP* (when relevant), the optimal values of the state variables
                    All these results are returned in the form of a TimeSeries object ranging over the optimization period
                    (i.e. [start_date, end_optimization_date]).
        """
        self.set_solver_specific_parameters_as_string(
            f"MIPRELSTOP {self.parameters.duality_gap} PRESOLVE {int(self.parameters.presolve)} MAXTIME {self.parameters.time_out}"
        )
        if self.parameters.debug:
            lp_file_name = os.path.join(
                self.parameters.output_folder, f"{self.thermal_unit.name}_price_{self.price_type}.lp"
            )
            self.export_model(lp_file_name)

        self.solve(self.parameters.solver_time_out.total_minutes())

        """STEP 5 : Return the results"""

        # Export the results
        # Final step : export the results of the program. We initialize a dictionnary that will store the results.
        # This dictionnary is returned to the user.
        # Initialize the dictionnary
        results = {}

        # Power output
        q_star = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, default_value=0
        )

        results["q"] = {}
        for t in self.time_frame:
            q_star[t] = self.q[t].solution_value()

        # If verbose is activated, inform the user if the optimal program is such that the unit
        # provides no output
        if self.parameters.verbose:
            if abs(q_star.min() - 0.0) <= 1e-6 and abs(q_star.max() - 0.0) <= 1e-6:
                zero_output_message = f"""*** Info ***
                The optimal solution for the unit {self.thermal_unit.name} is such that the unit remains offline and
                delivers no power output.
                """
                cfg.logger.info(zero_output_message)

        # contractedDifference.
        # This variable is returned as together with the procuredReserves it allows to know the exact amount
        # of reserves supplied (and unsupplied) for each time step. the reserves variables can take inexact values on the time steps
        # where there is no reserve to provide due to the fill up constraints.
        # Create the time series
        contracted_difference_up_star = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, default_value=0
        )
        contracted_difference_down_star = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, default_value=0
        )
        # Initialize the dictionnary keys
        results["contracted_difference_up"] = {}
        results["contracted_difference_down"] = {}
        # Add the automatedDifference
        # Create the time series
        automated_contracted_difference_up_star = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, default_value=0
        )
        automated_contracted_difference_down_star = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, default_value=0
        )
        # Initialize the dictionnary keys
        results["automated_contracted_difference_up"] = {}
        results["automated_contracted_difference_down"] = {}
        # Populate the time series
        for t in self.time_frame:
            contracted_difference_up_star[t] = self.contracted_difference_up[t].solution_value()
            contracted_difference_down_star[t] = self.contracted_difference_down[t].solution_value()
        # Populate the automatedDifference time series
        for t in self.time_frame:
            automated_contracted_difference_up_star[t] = self.automated_contracted_difference_up[t].solution_value()
            automated_contracted_difference_down_star[t] = self.automated_contracted_difference_down[t].solution_value()

        # Populate the dictionnary
        results["q"] = q_star
        results["contracted_difference_up"] = contracted_difference_up_star
        results["contracted_difference_down"] = contracted_difference_down_star
        # Add the automatedDifference
        results["automated_contracted_difference_up"] = automated_contracted_difference_up_star
        results["automated_contracted_difference_down"] = automated_contracted_difference_down_star

        # Status and auxiliary variables
        # Permanent variables
        ON_UP_star = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, default_value=0
        )
        ON_DOWN_star = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, default_value=0
        )
        OFF_star = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, default_value=0
        )

        # Initialize the corresponding keys in the dictionnary
        results["ON_UP"] = {}
        results["ON_DOWN"] = {}
        results["OFF"] = {}

        # Populate the time series
        for t in self.time_frame:
            ON_UP_star[t] = self.ON_UP[t].solution_value()
            ON_DOWN_star[t] = self.ON_DOWN[t].solution_value()
            OFF_star[t] = self.OFF[t].solution_value()

        # Populate the dictionnary
        results["ON_UP"] = ON_UP_star
        results["ON_DOWN"] = ON_DOWN_star
        results["OFF"] = OFF_star

        # Conditional variables
        if self.T_start >= 1:
            START_star = Timeseries.from_index(
                self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, default_value=0
            )
            # Add the keys in the dictionnary
            results["START"] = {}
            for t in self.time_frame:
                START_star[t] = self.START[t].solution_value()
                # Add the time series to the dictionnary.
            results["START"] = START_star
        if self.T_stop >= 1:
            STOP_star = Timeseries.from_index(
                self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, default_value=0
            )
            results["STOP"] = {}
            for t in self.time_frame:
                STOP_star[t] = self.STOP[t].solution_value()
            # Add the time series to the dictionnary.
            results["STOP"] = STOP_star
        if self.T_stable >= 1:
            ON_FLAT_star = Timeseries.from_index(
                self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, default_value=0
            )
            results["ON_FLAT"] = {}
            for t in self.time_frame:
                ON_FLAT_star[t] = self.ON_FLAT[t].solution_value()
            results["ON_FLAT"] = ON_FLAT_star

        return results

    def create_fill_up_constraints(
        self,
        time_frame: list[pendulum.DateTime],
        q: dict,
        reserves_up: dict,
        automated_reserves_up: dict,
        unprovided_reserves_up: dict,
        q_upper: Timeseries,
        epsilon: float,
        reserves_down: dict,
        automated_reserves_down: dict,
        unprovided_reserves_down: dict,
        relaxed_reserves: dict,
        q_lower: Timeseries,
    ):
        """Upward and downward "fill up" constraints"""
        for t in time_frame:
            self.add_constraint(
                q[t] + reserves_up[t] + automated_reserves_up[t] + unprovided_reserves_up[t]
                <= q_upper.get_value(t) + epsilon
            )  # Upward constraint - eq. (41)
            self.add_constraint(
                q[t] + reserves_up[t] + automated_reserves_up[t] + unprovided_reserves_up[t]
                >= q_upper.get_value(t) - epsilon
            )  # Upward constraint - eq. (41)

            self.add_constraint(
                (
                    q[t]
                    - reserves_down[t]
                    - automated_reserves_down[t]
                    - unprovided_reserves_down[t]
                    + relaxed_reserves[t]
                )
                <= q_lower.get_value(t) + epsilon
            )  # Downward constraint - eq. (42)
            self.add_constraint(
                (
                    q[t]
                    - reserves_down[t]
                    - automated_reserves_down[t]
                    - unprovided_reserves_down[t]
                    + relaxed_reserves[t]
                )
                >= q_lower.get_value(t) - epsilon
            )  # Downward constraint - eq. (42)

    def create_contracted_diff_constraints(
        self,
        time_frame: list[pendulum.DateTime],
        contracted_difference_up: dict,
        reserves_up_procured: Timeseries,
        reserves_up: dict,
        contracted_difference_down: dict,
        reserves_down_procured: Timeseries,
        reserves_down: dict,
        automated_contracted_difference_up: dict,
        feasible_automated_reserves_up_procured: Timeseries,
        automated_reserves_up: dict,
        automated_contracted_difference_down: dict,
        feasible_automated_reserves_down_procured: Timeseries,
        automated_reserves_down: dict,
    ):
        """Constraints on contractedDifference (eq. (40)) and on automatedContractedDifference (eq. (39))"""
        for t in time_frame:
            # contractedDifference
            self.add_constraint(contracted_difference_up[t] >= reserves_up_procured.get_value(t) - reserves_up[t])
            self.add_constraint(contracted_difference_down[t] >= reserves_down_procured.get_value(t) - reserves_down[t])
            # automatedContractedDifference
            self.add_constraint(
                automated_contracted_difference_up[t]
                >= feasible_automated_reserves_up_procured[t] - automated_reserves_up[t]
            )
            self.add_constraint(
                automated_contracted_difference_down[t]
                >= feasible_automated_reserves_down_procured[t] - automated_reserves_down[t]
            )

    def create_daily_energy_constraint(
        self, thermal_unit: Thermal, time_frame: list[pendulum.DateTime], time_step: Duration, q: dict
    ):
        # Energy limits
        if thermal_unit.has_daily_energy_constraint:
            days_in_time_frame = []

            for local_time in time_frame:
                if datetime(local_time.year, local_time.month, local_time.day, 0, 0, 0) not in days_in_time_frame:
                    days_in_time_frame.append(datetime(local_time.year, local_time.month, local_time.day, 0, 0, 0))

            for date in days_in_time_frame:
                upper_bound = thermal_unit.maximum_daily_energy.get_value(date)

                matching_steps = []
                for local_time in time_frame:
                    if (
                        (local_time.year == date.year)
                        and (local_time.month == date.month)
                        and (local_time.day == date.day)
                    ):
                        matching_steps.append(local_time)

                if matching_steps:  # Add a constraint only if the list of filtered dates is not empty.
                    # Enforce eq. (37)
                    self.add_constraint(
                        sum(q[t] for t in matching_steps) <= upper_bound * time_step.total_days() * len(matching_steps),
                        f"energy_limit_of_{thermal_unit.name}_at_{date}",
                    )
