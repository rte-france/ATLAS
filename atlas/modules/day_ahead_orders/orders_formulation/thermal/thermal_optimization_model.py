"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import math
import os
from datetime import datetime
from typing import Any, Literal

from pendulum._pendulum import Duration
from pydantic_extra_types.pendulum_dt import DateTime

import atlas.config as cfg
from atlas import OptimisationModel, generate_datetimes
from atlas.enum import SolverEnum
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.thermal import Thermal
from atlas.modules.day_ahead_orders.dao_parameters import DayAheadOrdersParameters
from atlas.solver.model_var import ModelVar


class ThermalOptimizationModel(OptimisationModel):
    """
    This class modelize the optimization program associated to the thermic units. It only
    performs the optimization for one unit, passed as an argument.
    Optimization is done over the extended optimization period, ie between start_date - epsilon
    and end_optimization_date + epsilon where epsilon is an additional time corresponding to
    the maximum between the minimum duration time and the startup duration.
    Optimization is done with respect to a given price sequence given.
    """

    RESERVES_UP_EQUIP_KEY = "reservesUp_equip_"
    RESERVES_DOWN_EQUIP_KEY = "reservesDown_equip_"
    UNPROVIDED_RESERVES_UP_KEY = "unprovidedReservesUp_equip_"
    UNPROVIDED_RESERVES_DOWN_KEY = "unprovidedReservesDown_equip_"
    RELAXED_RESERVES_KEY = "relaxedReserves_equip_"
    AUTOMATED_RESERVES_UP_KEY = "automatedReservesUp_equip_"
    AUTOMATED_RESERVES_DOWN_KEY = "automatedReservesDown_equip_"
    CONTRACTED_DIFFERENCE_UP_KEY = "contractedDifferenceUp_equip_"
    CONTRACTED_DIFFERENCE_DOWN_KEY = "contractedDifferenceDown_equip_"
    AUTOMATED_CONTRACTED_DIFFERENCE_UP_KEY = "automatedContractedDifferenceUp_equip_"
    AUTOMATED_CONTRACTED_DIFFERENCE_DOWN_KEY = "automatedContractedDifferenceDown_equip_"
    AUX_UP_GRAD_AT_KEY = "aux_up_grad_at_"
    AUX_DOWN_GRAD_AT_KEY = "aux_down_grad_at_"
    OFF_EQUIP_AT_KEY = "OFF_equip_"
    ON_DOWN_EQUIP_AT_KEY = "ON_DOWN_equip_"
    ON_UP_EQUIP_AT_KEY = "ON_UP_equip_"

    def __init__(
        self,
        parameters: DayAheadOrdersParameters,
        thermal_unit: Thermal,
        prices: Timeseries,
        price_type: str,
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
        self.prices: Timeseries = prices
        self.price_type: str = price_type
        self.T_on: int = None
        self.T_off: int = None
        self.T_stable: int = None
        self.time_frame: list[DateTime] = []
        self.T_start: int = None
        self.T_stop: int = None
        self.previous_time_frame: list[DateTime] = []
        self.extended_start_date: DateTime = None
        self.q_lower: Timeseries = None
        self.q_upper: Timeseries = None
        self.maximum_automated: float = None
        self.reserves_up_procured: Timeseries = None
        self.reserves_down_procured: Timeseries = None
        self.feasible_automated_reserves_up_procured: Timeseries = None
        self.feasible_automated_reserves_down_procured: Timeseries = None
        self.automated_unsupplied_reserves: float = 0
        self.delta_q: float = None
        self.delta_q_unconstrained: float = None
        self.q: dict[DateTime, Any] = {}
        self.OFF = ModelVar(
            lambda t: self.get_variable(self.off_equip_at(t)), lambda t: self.add_boolean_variable(self.off_equip_at(t))
        )
        self.ON_DOWN = ModelVar(
            lambda t: self.get_variable(self.on_down_equip_at(t)),
            lambda t: self.add_boolean_variable(self.on_down_equip_at(t)),
        )
        self.ON_UP = ModelVar(
            lambda t: self.get_variable(self.on_up_equip_at(t)),
            lambda t: self.add_boolean_variable(self.on_up_equip_at(t)),
        )
        self.start_time_steps = None
        self.stop_time_steps = None
        self.START: dict[DateTime, Any] = {}
        self.STOP: dict[DateTime, Any] = {}
        self.start_date_minus_one: DateTime = None
        self.ON_FLAT: dict[DateTime, Any] = {}
        self.turned_on: dict[DateTime, Any] = {}  # Corresponding to the variable defined in sec. 6.1.1
        self.turned_off: dict[DateTime, Any] = {}  # Corresponding to the variable defined in sec. 6.1.2
        self.time_frame_union_minus_one: list[DateTime] = None
        self.Q_max: float = None
        self.Q_min: float = None
        self.stable: dict[DateTime, Any] = {}  # This auxiliary variable indicates when the unit enters the FLAT state
        # This variable replaces ON_UP in the definition of the gradient and will bound the gradient for only one time step
        self.entered_up: dict[DateTime, Any] = {}
        self.entered_down: dict[DateTime, Any] = {}  # Same as single_on_up but for on down
        # This variable will be implemented in the gradient and bound the upward gradient
        self.U: dict[DateTime, Any] = {}
        # This variable will be implemented in the gradient and bound the downward gradient
        self.D: dict[DateTime, Any] = {}
        self.last_power: Timeseries = None
        self.last_date: DateTime = None

        # Power gradients
        # Definition of the gradients_time_frame : starts at start_date - time_step and goes until T-1
        # Gradients are defined on a "shifted" time frame.
        self.gradients_time_frame = generate_datetimes(
            self.parameters.start_date - self.parameters.time_step,
            self.parameters.end_optimization_date - 2 * self.parameters.time_step,
            self.parameters.time_step,
        )

        self._initial_setup()
        self._define_time_frame_variables()

    def off_equip_at(self, t: DateTime) -> str:
        return f"{self.OFF_EQUIP_AT_KEY}{self.thermal_unit.name}_at_{t}"

    def on_down_equip_at(self, t: DateTime) -> str:
        return f"{self.ON_DOWN_EQUIP_AT_KEY}{self.thermal_unit.name}_at_{t}"

    def on_up_equip_at(self, t: DateTime) -> str:
        return f"{self.ON_UP_EQUIP_AT_KEY}{self.thermal_unit.name}_at_{t}"

    def reserves_up_equip_at(self, t: DateTime) -> str:
        return f"{self.RESERVES_UP_EQUIP_KEY}{self.thermal_unit.name}_at_{t}"

    def reserves_down_equip_at(self, t: DateTime) -> str:
        return f"{self.RESERVES_DOWN_EQUIP_KEY}{self.thermal_unit.name}_at_{t}"

    def unprovided_reserves_up_at(self, t: DateTime) -> str:
        return f"{self.UNPROVIDED_RESERVES_UP_KEY}{self.thermal_unit.name}_at_{t}"

    def unprovided_reserves_down_at(self, t: DateTime) -> str:
        return f"{self.UNPROVIDED_RESERVES_DOWN_KEY}{self.thermal_unit.name}_at_{t}"

    def relaxed_reserves_at(self, t: DateTime) -> str:
        return f"{self.RELAXED_RESERVES_KEY}{self.thermal_unit.name}_at_{t}"

    def automated_reserves_up_at(self, t: DateTime) -> str:
        return f"{self.AUTOMATED_RESERVES_UP_KEY}{self.thermal_unit.name}_at_{t}"

    def automated_reserves_down_at(self, t: DateTime) -> str:
        return f"{self.AUTOMATED_RESERVES_DOWN_KEY}{self.thermal_unit.name}_at_{t}"

    def contracted_difference_up_at(self, t: DateTime) -> str:
        return f"{self.CONTRACTED_DIFFERENCE_UP_KEY}{self.thermal_unit.name}_at_{t}"

    def contracted_difference_down_at(self, t: DateTime) -> str:
        return f"{self.CONTRACTED_DIFFERENCE_DOWN_KEY}{self.thermal_unit.name}_at_{t}"

    def automated_contracted_difference_up_at(self, t: DateTime) -> str:
        return f"{self.AUTOMATED_CONTRACTED_DIFFERENCE_UP_KEY}{self.thermal_unit.name}_at_{t}"

    def automated_contracted_difference_down_at(self, t: DateTime) -> str:
        return f"{self.AUTOMATED_CONTRACTED_DIFFERENCE_DOWN_KEY}{self.thermal_unit.name}_at_{t}"

    def aux_down_grad_at(self, t: DateTime) -> str:
        return f"{self.AUX_DOWN_GRAD_AT_KEY}{t}_equip_{self.thermal_unit.name}"

    def aux_up_grad_at(self, t: DateTime) -> str:
        return f"{self.AUX_UP_GRAD_AT_KEY}{t}_equip_{self.thermal_unit.name}"

    def _initial_setup(self) -> None:
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
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_optimization_date, 0
        )
        fcr_down_procured = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_optimization_date, 0
        )
        afrr_up_procured = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_optimization_date, 0
        )
        afrr_down_procured = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_optimization_date, 0
        )
        mfrr_up_procured = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_optimization_date, 0
        )
        mfrr_down_procured = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_optimization_date, 0
        )
        rr_up_procured = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_optimization_date, 0
        )
        rr_down_procured = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_optimization_date, 0
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
                        math.ceil(self.thermal_unit.minimum_time_on / self.parameters.time_step),
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
                        math.ceil(self.thermal_unit.minimum_time_off / self.parameters.time_step),
                    )
                )
                + 1
            )
        else:
            self.T_off = 0
        self.T_start = int(math.floor(self.thermal_unit.startup_duration / self.parameters.time_step))
        self.T_stop = int(math.floor(self.thermal_unit.shutdown_duration / self.parameters.time_step))

        if minimum_stable_power_duration >= self.parameters.time_step:
            self.T_stable = int(math.ceil(minimum_stable_power_duration / self.parameters.time_step)) + 1
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
            self.feasible_automated_reserves_up_procured.set_value(
                t,
                min(afrr_up_procured.get_value(t), self.thermal_unit.maximum_afrr)
                + min(fcr_up_procured.get_value(t), self.thermal_unit.maximum_fcr),
            )
            self.feasible_automated_reserves_down_procured.set_value(
                t,
                min(afrr_down_procured.get_value(t), self.thermal_unit.maximum_afrr)
                + min(fcr_down_procured.get_value(t), self.thermal_unit.maximum_fcr),
            )

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
        self.delta_q = self.thermal_unit.maximum_gradient * self.parameters.time_step.total_minutes()
        self.delta_q_unconstrained = self.thermal_unit.maximum_power.max()

    def _define_time_frame_variables(self) -> None:
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
            self.add_continuous_variable(self.reserves_up_equip_at(t), 0, self.q_upper.get_value(t))
            self.add_continuous_variable(self.reserves_down_equip_at(t), 0, self.q_upper.get_value(t))
            self.add_continuous_variable(self.unprovided_reserves_up_at(t), 0, self.q_upper.get_value(t))
            self.add_continuous_variable(self.unprovided_reserves_down_at(t), 0, self.q_upper.get_value(t))
            self.add_continuous_variable(self.relaxed_reserves_at(t), 0, self.q_lower.get_value(t))

        # create the automatedReserves control variables.
        for t in self.time_frame:
            self.add_continuous_variable(self.automated_reserves_up_at(t), 0, self.maximum_automated)
            self.add_continuous_variable(self.automated_reserves_down_at(t), 0, self.maximum_automated)

        # Create the contractedDifference variables. These variables are implemented as control variables will be included in the
        # objective function and constrained by constraint (40).
        for t in self.time_frame:
            self.add_continuous_variable(self.contracted_difference_up_at(t), 0, self.q_upper.get_value(t))
            self.add_continuous_variable(self.contracted_difference_down_at(t), 0, self.q_upper.get_value(t))

        # Automated contracted difference variables. These variables will be constrained by equation (39).
        for t in self.time_frame:
            self.add_continuous_variable(self.automated_contracted_difference_up_at(t), 0, self.q_upper.get_value(t))
            self.add_continuous_variable(self.automated_contracted_difference_down_at(t), 0, self.q_upper.get_value(t))

        # 1.2. State variables (always in upper case)

        # 1.2.1. Initialization of the state variables that are always defined :
        # OFF, ON_UP, ON_FLAT and ON_DOWN

        # Create the state variables for each time step over the extended time frame.
        for t in self.time_frame:
            self.OFF.set_model_var(t)
            self.ON_UP.set_model_var(t)
            self.ON_DOWN.set_model_var(t)

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

            self.ON_DOWN.set_model_var(self.start_date_minus_one)
            self.ON_UP.set_model_var(self.start_date_minus_one)

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
                self.add_continuous_variable(
                    self.aux_up_grad_at(t),
                    self.Q_min,
                    self.Q_max,
                )
                self.add_continuous_variable(
                    self.aux_down_grad_at(t),
                    self.Q_min,
                    self.Q_max,
                )

    def create_objective_function(self, direction: Literal["maximize", "minimize"] = "maximize") -> None:
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
                    * (
                        self.get_variable(self.contracted_difference_up_at(t))
                        + self.get_variable(self.contracted_difference_down_at(t))
                    )
                    - self.parameters.automated_unprocured_reserves_penalty
                    * (self.parameters.time_step.total_hours())
                    * (
                        self.get_variable(self.automated_contracted_difference_up_at(t))
                        + self.get_variable(self.automated_contracted_difference_down_at(t))
                    )
                    for t in self.time_frame
                )
                - self.parameters.automated_unprocured_reserves_penalty
                * (self.parameters.time_step.total_hours())
                * self.automated_unsupplied_reserves
            ),
            direction=direction,
        )

    def determine_combination(self) -> int:
        """Determine which of the 8 constraint combinations to use.
        STEP 3 : Constraints and initial conditions
        # Constraints and initial conditions are defined based on state and auxiliary variables.
        # Since these variables are not necessarily defined, in the following we go through all
        # 8 possible combinations of state and auxiliary variables and write the corresponding
        # initial conditions and set of constraints all at once.
        #
        # Initial conditions are defined on the previous_time_frame, constraints on the state and
        # control variables are defined on the time_frame.
        """
        if self.T_stop == 0 and self.T_start == 0 and self.T_stable == 0:
            return 1
        elif self.T_stop >= 1 and self.T_start == 0 and self.T_stable == 0:
            return 2
        elif self.T_stop == 0 and self.T_start == 0 and self.T_stable >= 1:
            return 3
        elif self.T_start >= 1 and self.T_stop == 0 and self.T_stable == 0:
            return 4
        elif self.T_stop >= 1 and self.T_start == 0 and self.T_stable >= 1:
            return 5
        elif self.T_stop == 0 and self.T_start >= 1 and self.T_stable >= 1:
            return 6
        elif self.T_stop >= 1 and self.T_start >= 1 and self.T_stable == 0:
            return 7
        elif self.T_stop >= 1 and self.T_start >= 1 and self.T_stable >= 1:
            return 8
        else:
            return 1  # Default fallback

    def solve_thermal_optimization(self) -> dict[str, Timeseries]:
        """
        STEP 4 : Solving the problem
        :return: - `results`: a dictionnary containing the optimal values of the decision variables,
                    namely :
                        . q*, the optimal power output
                        . ON_.*, OFF*, START* and STOP* (when relevant), the optimal values of the state variables
                    All these results are returned in the form of a TimeSeries object ranging over the optimization period
                    (i.e. [start_date, end_optimization_date]).
        """
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
        results: dict[str, Timeseries] = {}

        # Power output
        q_star = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, default_value=0
        )

        for t in self.time_frame:
            q_star.set_value(t, self.q[t].solution_value())

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

        # Add the automatedDifference
        # Create the time series
        automated_contracted_difference_up_star = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, default_value=0
        )
        automated_contracted_difference_down_star = Timeseries.from_index(
            self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, default_value=0
        )

        # Populate the time series
        for t in self.time_frame:
            contracted_difference_up_star.set_value(
                t, self.get_variable(self.contracted_difference_up_at(t)).solution_value()
            )
            contracted_difference_down_star.set_value(
                t, self.get_variable(self.contracted_difference_down_at(t)).solution_value()
            )
        # Populate the automatedDifference time series
        for t in self.time_frame:
            automated_contracted_difference_up_star.set_value(
                t, self.get_variable(self.automated_contracted_difference_up_at(t)).solution_value()
            )
            automated_contracted_difference_down_star.set_value(
                t, self.get_variable(self.automated_contracted_difference_down_at(t)).solution_value()
            )

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

        # Populate the time series
        for t in self.time_frame:
            ON_UP_star.set_value(t, self.ON_UP.get_model_var(t).solution_value())
            ON_DOWN_star.set_value(t, self.ON_DOWN.get_model_var(t).solution_value())
            OFF_star.set_value(t, self.OFF.get_model_var(t).solution_value())

        # Populate the dictionnary
        results["ON_UP"] = ON_UP_star
        results["ON_DOWN"] = ON_DOWN_star
        results["OFF"] = OFF_star

        # Conditional variables
        if self.T_start >= 1:
            START_star = Timeseries.from_index(
                self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, default_value=0
            )
            for t in self.time_frame:
                START_star.set_value(t, self.START[t].solution_value())
                # Add the time series to the dictionnary.
            results["START"] = START_star
        if self.T_stop >= 1:
            STOP_star = Timeseries.from_index(
                self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, default_value=0
            )
            for t in self.time_frame:
                STOP_star.set_value(t, self.STOP[t].solution_value())
            # Add the time series to the dictionnary.
            results["STOP"] = STOP_star
        if self.T_stable >= 1:
            ON_FLAT_star = Timeseries.from_index(
                self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, default_value=0
            )
            for t in self.time_frame:
                ON_FLAT_star.set_value(t, self.ON_FLAT[t].solution_value())
            results["ON_FLAT"] = ON_FLAT_star

        return results

    def create_fill_up_constraints(
        self, time_frame: list[DateTime], q: dict, q_upper: Timeseries, epsilon: float, q_lower: Timeseries
    ) -> None:
        """Upward and downward "fill up" constraints"""
        for t in time_frame:
            self.add_constraint(
                q[t]
                + self.get_variable(self.reserves_up_equip_at(t))
                + self.get_variable(self.automated_reserves_up_at(t))
                + self.get_variable(self.unprovided_reserves_up_at(t))
                <= q_upper.get_value(t) + epsilon
            )  # Upward constraint - eq. (41)
            self.add_constraint(
                q[t]
                + self.get_variable(self.reserves_up_equip_at(t))
                + self.get_variable(self.automated_reserves_up_at(t))
                + self.get_variable(self.unprovided_reserves_up_at(t))
                >= q_upper.get_value(t) - epsilon
            )  # Upward constraint - eq. (41)

            self.add_constraint(
                (
                    q[t]
                    - self.get_variable(self.reserves_down_equip_at(t))
                    - self.get_variable(self.automated_reserves_down_at(t))
                    - self.get_variable(self.unprovided_reserves_down_at(t))
                    + self.get_variable(self.relaxed_reserves_at(t))
                )
                <= q_lower.get_value(t) + epsilon
            )  # Downward constraint - eq. (42)
            self.add_constraint(
                (
                    q[t]
                    - self.get_variable(self.reserves_down_equip_at(t))
                    - self.get_variable(self.automated_reserves_down_at(t))
                    - self.get_variable(self.unprovided_reserves_down_at(t))
                    + self.get_variable(self.relaxed_reserves_at(t))
                )
                >= q_lower.get_value(t) - epsilon
            )  # Downward constraint - eq. (42)

    def create_contracted_diff_constraints(
        self,
        time_frame: list[DateTime],
        reserves_up_procured: Timeseries,
        reserves_down_procured: Timeseries,
        feasible_automated_reserves_up_procured: Timeseries,
        feasible_automated_reserves_down_procured: Timeseries,
    ) -> None:
        """Constraints on contractedDifference (eq. (40)) and on automatedContractedDifference (eq. (39))"""
        for t in time_frame:
            # contractedDifference
            self.add_constraint(
                self.get_variable(self.contracted_difference_up_at(t))
                >= reserves_up_procured.get_value(t) - self.get_variable(self.reserves_up_equip_at(t))
            )
            self.add_constraint(
                self.get_variable(self.contracted_difference_down_at(t))
                >= reserves_down_procured.get_value(t) - self.get_variable(self.reserves_down_equip_at(t))
            )
            # automatedContractedDifference
            self.add_constraint(
                self.get_variable(self.automated_contracted_difference_up_at(t))
                >= feasible_automated_reserves_up_procured.get_value(t)
                - self.get_variable(self.automated_reserves_up_at(t))
            )
            self.add_constraint(
                self.get_variable(self.automated_contracted_difference_down_at(t))
                >= feasible_automated_reserves_down_procured.get_value(t)
                - self.get_variable(self.automated_reserves_down_at(t))
            )

    def create_daily_energy_constraint(
        self, thermal_unit: Thermal, time_frame: list[DateTime], time_step: Duration, q: dict
    ) -> None:
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

    def is_day_zero(self) -> bool:
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
        return day_zero
