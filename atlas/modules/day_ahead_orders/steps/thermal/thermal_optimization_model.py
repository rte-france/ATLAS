"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import math
from datetime import datetime
from typing import Literal

from pendulum import DateTime

import atlas.config as cfg
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.models.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.objects.equipment.thermal import Thermal
from atlas.solver.model_var import ModelVar
from atlas.solver.models import SolverOptions
from atlas.solver.solver_interface import OptimisationModel
from atlas.timing import generate_datetimes


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
    START_EQUIP_AT_KEY = "START_equip_"
    STOP_EQUIP_AT_KEY = "STOP_equip_"
    ON_FLAT_EQUIP_AT_KEY = "ON_FLAT_equip_"
    TURNED_ON_EQUIP_AT_KEY = "turned_on_equip_"
    TURNED_OFF_EQUIP_AT_KEY = "turned_off_equip_"
    STABLE_AT_KEY = "stable_at_"
    ENTERED_UP_AT_KEY = "entered_up_at_"
    ENTERED_DOWN_AT_KEY = "entered_down_at_"
    POWER_EQUIP_KEY = "power_equip_"
    UP_GRAD_AT_KEY = "UP_grad_at_"
    DOWN_GRAD_AT_KEY = "DOWN_grad_at_"

    extended_start_date: DateTime
    q_lower: Timeseries
    q_upper: Timeseries
    reserves_up_procured: Timeseries
    reserves_down_procured: Timeseries
    feasible_automated_reserves_up_procured: Timeseries
    feasible_automated_reserves_down_procured: Timeseries
    last_power: Timeseries
    last_date: DateTime | None
    start_date_minus_one: DateTime
    time_frame_union_minus_one: list[DateTime]
    start_time_steps: range
    stop_time_steps: range

    def __init__(
        self,
        parameters: DayAheadOrdersParameters,
        thermal_unit: ThermalDAO,
        prices: Timeseries,
        price_type: str,
        solver_options: SolverOptions,
    ):
        """
        :param parameters: a DayAheadOrdersParameters instance
        :type parameters: DayAheadOrdersParameters
        :param thermal_unit: a Thermal instance
        :type thermal_unit: ThermalDAO
        :param prices: a price timeseries based on which optimization will be conducted.
        :type prices: Timeseries
        :param price_type: the price_type
        :type price_type: str
        :param solver_options: the solver options
        :type solver_options: SolverOptions
        """
        super().__init__(
            solver_name=parameters.solver.solver_name,
            name=f"Optimization program for thermal unit {thermal_unit.name}",
            options=solver_options,
        )
        self.parameters: DayAheadOrdersParameters = parameters
        # Quick sanity check on the class of the equipment supplied as input.
        if not isinstance(thermal_unit, Thermal):
            cfg.logger.error(f"Equipement {thermal_unit.name} is not of type thermic.")
            raise ValueError("Wrong equipment type for the thermic optimization program.")
        self.thermal_unit: ThermalDAO = thermal_unit
        self.prices: Timeseries = prices
        self.price_type: str = price_type
        self.time_frame: list[DateTime] = []
        self.previous_time_frame: list[DateTime] = []
        self.q = ModelVar(
            lambda t: self.get_variable(self.power_equip_at(t)),
            lambda t: self.add_continuous_variable(self.power_equip_at(t), 0, self.q_upper.get_value(t)),
        )
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
        self.START = ModelVar(
            lambda t: self.get_variable(self.start_equip_at(t)),
            lambda t: self.add_boolean_variable(self.start_equip_at(t)),
        )
        self.STOP = ModelVar(
            lambda t: self.get_variable(self.stop_equip_at(t)),
            lambda t: self.add_boolean_variable(self.stop_equip_at(t)),
        )
        self.ON_FLAT = ModelVar(
            lambda t: self.get_variable(self.on_flat_equip_at(t)),
            lambda t: self.add_boolean_variable(self.on_flat_equip_at(t)),
        )
        # Corresponding to the variable defined in sec. 6.1.1
        self.turned_on = ModelVar(
            lambda t: self.get_variable(self.turned_on_equip_at(t)),
            lambda t: self.add_continuous_variable(self.turned_on_equip_at(t), 0, 1),
        )
        # Corresponding to the variable defined in sec. 6.1.2
        self.turned_off = ModelVar(
            lambda t: self.get_variable(self.turned_off_equip_at(t)),
            lambda t: self.add_continuous_variable(self.turned_off_equip_at(t), 0, 1),
        )
        # This auxiliary variable indicates when the unit enters the FLAT state
        self.stable = ModelVar(
            lambda t: self.get_variable(self.stable_at(t)),
            lambda t: self.add_continuous_variable(self.stable_at(t), 0, 1),
        )
        # This variable replaces ON_UP in the definition of the gradient and will bound the gradient for only one time step
        self.entered_up = ModelVar(
            lambda t: self.get_variable(self.entered_up_at(t)),
            lambda t: self.add_continuous_variable(self.entered_up_at(t), 0, 1),
        )
        # Same as single_on_up but for on down
        self.entered_down = ModelVar(
            lambda t: self.get_variable(self.entered_down_at(t)),
            lambda t: self.add_continuous_variable(self.entered_down_at(t), 0, 1),
        )
        # This variable will be implemented in the gradient and bound the upward gradient
        self.U = ModelVar(
            lambda t: self.get_variable(self.up_grad_at(t)),
            lambda t: self.add_continuous_variable(self.up_grad_at(t), self.Q_min, self.Q_max),
        )
        # This variable will be implemented in the gradient and bound the downward gradient
        self.D = ModelVar(
            lambda t: self.get_variable(self.down_grad_at(t)),
            lambda t: self.add_continuous_variable(self.down_grad_at(t), self.Q_min, self.Q_max),
        )
        # Power gradients
        # Definition of the gradients_time_frame : starts at start_date - time_step and goes until T-1
        # Gradients are defined on a "shifted" time frame.
        self.gradients_time_frame = generate_datetimes(
            self.parameters.temporal.start_date - self.parameters.temporal.timestep,
            self.parameters.temporal.end_date
            + self.thermal_unit.additional_hours
            - 2 * self.parameters.temporal.timestep,
            self.parameters.temporal.timestep,
        )

        self.T_on: int = 0
        self.T_off: int = 0
        self.T_stable: int = 0
        self.T_start: int = 0
        self.T_stop: int = 0
        self.maximum_automated: float = 0.0
        self.automated_unsupplied_reserves: float = 0.0
        self.delta_q: float = 0.0
        self.delta_q_unconstrained: float = 0.0
        self.Q_max: float = 0.0
        self.Q_min: float = 0.0

        self._initial_setup()
        self._define_time_frame_variables()

    def off_equip_at(self, t: DateTime) -> str:
        return f"{self.OFF_EQUIP_AT_KEY}{self.thermal_unit.name}_at_{t}"

    def on_down_equip_at(self, t: DateTime) -> str:
        return f"{self.ON_DOWN_EQUIP_AT_KEY}{self.thermal_unit.name}_at_{t}"

    def on_up_equip_at(self, t: DateTime) -> str:
        return f"{self.ON_UP_EQUIP_AT_KEY}{self.thermal_unit.name}_at_{t}"

    def start_equip_at(self, t: DateTime) -> str:
        return f"{self.START_EQUIP_AT_KEY}{self.thermal_unit.name}_at_{t}"

    def stop_equip_at(self, t: DateTime) -> str:
        return f"{self.STOP_EQUIP_AT_KEY}{self.thermal_unit.name}_at_{t}"

    def on_flat_equip_at(self, t: DateTime) -> str:
        return f"{self.ON_FLAT_EQUIP_AT_KEY}{self.thermal_unit.name}_at_{t}"

    def turned_on_equip_at(self, t: DateTime) -> str:
        return f"{self.TURNED_ON_EQUIP_AT_KEY}{self.thermal_unit.name}_at_{t}"

    def turned_off_equip_at(self, t: DateTime) -> str:
        return f"{self.TURNED_OFF_EQUIP_AT_KEY}{self.thermal_unit.name}_at_{t}"

    def stable_at(self, t: DateTime) -> str:
        return f"{self.STABLE_AT_KEY}{t}_equip_{self.thermal_unit.name}"

    def entered_up_at(self, t: DateTime) -> str:
        return f"{self.ENTERED_UP_AT_KEY}{t}_equip_{self.thermal_unit.name}"

    def entered_down_at(self, t: DateTime) -> str:
        return f"{self.ENTERED_DOWN_AT_KEY}{t}_equip_{self.thermal_unit.name}"

    def power_equip_at(self, t: DateTime) -> str:
        return f"{self.POWER_EQUIP_KEY}{self.thermal_unit.name}_at_{t}"

    def up_grad_at(self, t: DateTime) -> str:
        return f"{self.UP_GRAD_AT_KEY}{t}_equip_{self.thermal_unit.name}"

    def down_grad_at(self, t: DateTime) -> str:
        return f"{self.DOWN_GRAD_AT_KEY}{t}_equip_{self.thermal_unit.name}"

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
        """
        STEP 0 : Retrieve the parameters of the program and set up the time frame
        :return: None
        """

        # Sanity check on the start_date and the end_date. A warning message is sent to the user if the start_date is later
        # than the end_date.
        if self.parameters.temporal.start_date > self.parameters.temporal.end_date + self.thermal_unit.additional_hours:
            cfg.logger.error(
                "The end_optimization_date is earlier than or identical to the start_date. \n"
                "The time frame cannot be defined. Please check the values of start_date, end date and AdditionalHours"
            )
            raise ValueError("Improper dates")

        # Get the parameters of the unit
        fcr_up_procured = Timeseries.from_index(
            self.parameters.temporal.start_date,
            self.parameters.temporal.timestep,
            self.parameters.temporal.end_date + self.thermal_unit.additional_hours,
            0,
        )
        fcr_down_procured = Timeseries.from_index(
            self.parameters.temporal.start_date,
            self.parameters.temporal.timestep,
            self.parameters.temporal.end_date + self.thermal_unit.additional_hours,
            0,
        )
        afrr_up_procured = Timeseries.from_index(
            self.parameters.temporal.start_date,
            self.parameters.temporal.timestep,
            self.parameters.temporal.end_date + self.thermal_unit.additional_hours,
            0,
        )
        afrr_down_procured = Timeseries.from_index(
            self.parameters.temporal.start_date,
            self.parameters.temporal.timestep,
            self.parameters.temporal.end_date + self.thermal_unit.additional_hours,
            0,
        )
        mfrr_up_procured = Timeseries.from_index(
            self.parameters.temporal.start_date,
            self.parameters.temporal.timestep,
            self.parameters.temporal.end_date + self.thermal_unit.additional_hours,
            0,
        )
        mfrr_down_procured = Timeseries.from_index(
            self.parameters.temporal.start_date,
            self.parameters.temporal.timestep,
            self.parameters.temporal.end_date + self.thermal_unit.additional_hours,
            0,
        )
        rr_up_procured = Timeseries.from_index(
            self.parameters.temporal.start_date,
            self.parameters.temporal.timestep,
            self.parameters.temporal.end_date + self.thermal_unit.additional_hours,
            0,
        )
        rr_down_procured = Timeseries.from_index(
            self.parameters.temporal.start_date,
            self.parameters.temporal.timestep,
            self.parameters.temporal.end_date + self.thermal_unit.additional_hours,
            0,
        )
        if self.thermal_unit.fcr_up_procured:
            fcr_up_procured = self.thermal_unit.fcr_up_procured.get_forecast(
                self.parameters.temporal.execution_date,
                self.parameters.temporal.start_date,
                self.parameters.temporal.end_date + self.thermal_unit.additional_hours,
            )
        if self.thermal_unit.fcr_down_procured:
            fcr_down_procured = self.thermal_unit.fcr_down_procured.get_forecast(
                self.parameters.temporal.execution_date,
                self.parameters.temporal.start_date,
                self.parameters.temporal.end_date + self.thermal_unit.additional_hours,
            )
        if self.thermal_unit.afrr_up_procured:
            afrr_up_procured = self.thermal_unit.afrr_up_procured.get_forecast(
                self.parameters.temporal.execution_date,
                self.parameters.temporal.start_date,
                self.parameters.temporal.end_date + self.thermal_unit.additional_hours,
            )
        if self.thermal_unit.afrr_down_procured:
            afrr_down_procured = self.thermal_unit.afrr_down_procured.get_forecast(
                self.parameters.temporal.execution_date,
                self.parameters.temporal.start_date,
                self.parameters.temporal.end_date + self.thermal_unit.additional_hours,
            )
        if self.thermal_unit.mfrr_up_procured:
            mfrr_up_procured = self.thermal_unit.mfrr_up_procured.get_forecast(
                self.parameters.temporal.execution_date,
                self.parameters.temporal.start_date,
                self.parameters.temporal.end_date + self.thermal_unit.additional_hours,
            )
        if self.thermal_unit.mfrr_down_procured:
            mfrr_down_procured = self.thermal_unit.mfrr_down_procured.get_forecast(
                self.parameters.temporal.execution_date,
                self.parameters.temporal.start_date,
                self.parameters.temporal.end_date + self.thermal_unit.additional_hours,
            )
        if self.thermal_unit.rr_up_procured:
            rr_up_procured = self.thermal_unit.rr_up_procured.get_forecast(
                self.parameters.temporal.execution_date,
                self.parameters.temporal.start_date,
                self.parameters.temporal.end_date + self.thermal_unit.additional_hours,
            )
        if self.thermal_unit.rr_down_procured:
            rr_down_procured = self.thermal_unit.rr_down_procured.get_forecast(
                self.parameters.temporal.execution_date,
                self.parameters.temporal.start_date,
                self.parameters.temporal.end_date + self.thermal_unit.additional_hours,
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
                        math.ceil(self.thermal_unit.minimum_time_on / self.parameters.temporal.timestep),
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
                        math.ceil(self.thermal_unit.minimum_time_off / self.parameters.temporal.timestep),
                    )
                )
                + 1
            )
        else:
            self.T_off = 0
        self.T_start = int(math.floor(self.thermal_unit.startup_duration / self.parameters.temporal.timestep))
        self.T_stop = int(math.floor(self.thermal_unit.shutdown_duration / self.parameters.temporal.timestep))

        if minimum_stable_power_duration >= self.parameters.temporal.timestep:
            self.T_stable = int(math.ceil(minimum_stable_power_duration / self.parameters.temporal.timestep)) + 1
        else:
            self.T_stable = 0

        # Rescale self.T_stable so that it is either equal to 0 or >= 2:
        self.T_stable = self.T_stable if self.T_stable >= 2 else 0

        # Set-up the time frames
        # Definition of the time_frame time frame : the time frame on which the optimization program will be solved.
        # Remark: we define the time series until end_date - time_step because
        # we want all time steps to lie in the [start_date, end_optimization_date] range.
        end_date = (
            self.parameters.temporal.end_date + self.thermal_unit.additional_hours - self.parameters.temporal.timestep
        )
        self.time_frame = generate_datetimes(
            self.parameters.temporal.start_date, end_date, self.parameters.temporal.timestep
        )

        # Define T_traceback, the number of timesteps we need to go before start_date to define the initial conditions.
        # We add +1 in order to avoid out-of-bounds errors when defining the ON_FLAT state.
        T_traceback = int(max(self.T_on + self.T_start, self.T_off + self.T_stop)) + 1

        # Define manually the previous_time_frame, which contains all time steps from start_date to (start_date - T_traceback * time_step)
        for k in range(1, T_traceback + 1):
            self.previous_time_frame.append(self.parameters.temporal.start_date - k * self.parameters.temporal.timestep)

        # Define the extendedTimeFrame, ranging from the last element of the previous_time_frame to end_optimization_date.
        # We also start from 1 in order to exclude start_date from the previous_time_frame.
        self.extended_start_date = self.previous_time_frame[-1]  # Last date in the previous_time_frame

        # Retrieve the values of the Power attribute over previous_time_frame
        if self.thermal_unit.power:
            self.last_power = self.thermal_unit.power.get_forecast(
                self.parameters.temporal.execution_date,
                self.extended_start_date,
                self.parameters.temporal.start_date - self.parameters.temporal.timestep,
                default_value=0.0,
            )  # Extract the time series corresponding to the previous period
        else:
            self.last_power = Timeseries.from_index(
                self.extended_start_date,
                self.parameters.temporal.timestep,
                self.parameters.temporal.start_date - self.parameters.temporal.timestep,
                0,
            )

        self.last_date = self.last_power.last_date()  # get the last date with a recorded value

        # Set-up the power bounds : copy maximum- and minimum_power
        # because q_lower and q_upper may be modified afterwards.
        self.q_lower = Timeseries.from_timeseries(self.thermal_unit.minimum_power)
        self.q_upper = Timeseries.from_timeseries(self.thermal_unit.maximum_power)

        # Set-up the reserve requirements
        # Compute the maximum_automated
        maximum_afrr = self.thermal_unit.maximum_afrr if self.thermal_unit.maximum_afrr is not None else 0.0
        maximum_fcr = self.thermal_unit.maximum_fcr if self.thermal_unit.maximum_fcr is not None else 0.0
        self.maximum_automated = maximum_afrr + maximum_fcr

        # Add the manual reserves (referred to as "reserves" in the following)
        # Reserves
        self.reserves_up_procured = mfrr_up_procured + rr_up_procured
        self.reserves_down_procured = mfrr_down_procured + rr_down_procured
        # Compute the feasibleAutomatedReserves. This is to accomodate for the fact that the maximumAFRR and maximumFCR capacities
        # may be different.If the unit has a procurement greater than its capacity, the remaning part will be unsupplied and counted
        # in a penalty added in the objective function.

        # Create the time series of feasible automated reserves procurements
        self.feasible_automated_reserves_up_procured = Timeseries.from_index(
            self.parameters.temporal.start_date, self.parameters.temporal.timestep, end_date, default_value=0
        )
        self.feasible_automated_reserves_down_procured = Timeseries.from_index(
            self.parameters.temporal.start_date, self.parameters.temporal.timestep, end_date, default_value=0
        )

        # Populate the time series and retrieve the infeasible automated reserve procurements.
        for t in self.time_frame:
            # retrieve the feasible part in the feasible time series
            if t in self.feasible_automated_reserves_up_procured:
                self.feasible_automated_reserves_up_procured.set_value(
                    t,
                    min(afrr_up_procured.get_value(t), maximum_afrr) + min(fcr_up_procured.get_value(t), maximum_fcr),
                )
            else:
                self.feasible_automated_reserves_up_procured.add_index(
                    t,
                    min(afrr_up_procured.get_value(t), maximum_afrr) + min(fcr_up_procured.get_value(t), maximum_fcr),
                )
            if t in self.feasible_automated_reserves_down_procured:
                self.feasible_automated_reserves_down_procured.set_value(
                    t,
                    min(afrr_down_procured.get_value(t), maximum_afrr)
                    + min(fcr_down_procured.get_value(t), maximum_fcr),
                )
            else:
                self.feasible_automated_reserves_down_procured.add_index(
                    t,
                    min(afrr_down_procured.get_value(t), maximum_afrr)
                    + min(fcr_down_procured.get_value(t), maximum_fcr),
                )

            # retrieve and save the infeasible part
            self.automated_unsupplied_reserves += (
                max(afrr_up_procured.get_value(t) - maximum_afrr, 0)
                + max(fcr_up_procured.get_value(t) - maximum_fcr, 0)
                + max(afrr_down_procured.get_value(t) - maximum_afrr, 0)
                + max(fcr_down_procured.get_value(t) - maximum_fcr, 0)
            )

        cfg.logger.debug(f"automated unsupplied reserves : {self.automated_unsupplied_reserves}")

        # Set-up the power gradients
        self.delta_q = self.thermal_unit.maximum_gradient * self.parameters.temporal.timestep.total_minutes()
        self.delta_q_unconstrained = self.thermal_unit.maximum_power.max()

    def _define_time_frame_variables(self) -> None:
        """
        STEP 1 : Definition of the state, auxiliary and control variables over the time_frame.
        :return: none
        """

        # 1.1. Control variables :
        #    - the power output of the unit
        #    - the reserves of the unit and the mirror variables
        #    - contracted difference which corresponds to max(procured - provided, 0).
        # Define the main optimization variable. Bounds : O and self.q_upper
        for t in self.time_frame:
            self.q.set_model_var(t)

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
                self.START.set_model_var(t)

        if self.T_stop >= 1:
            # Define the stop_time_steps range.
            self.stop_time_steps = range(1, self.T_stop - 1)

            # Define the STOP state variable
            for t in self.time_frame:
                self.STOP.set_model_var(t)

        if self.T_stable >= 1:
            self.start_date_minus_one = self.parameters.temporal.start_date - self.parameters.temporal.timestep
            for t in self.time_frame:
                self.ON_FLAT.set_model_var(t)

            # For the time step start_date - 1, create optimization avariables for ON_FLAT, ON_UP and ON_DOWN
            self.ON_FLAT.set_model_var(self.start_date_minus_one)

            self.ON_DOWN.set_model_var(self.start_date_minus_one)
            self.ON_UP.set_model_var(self.start_date_minus_one)

        # 1.3. Auxiliary variables
        # Remark. Auxiliary variables are formally binary variables but due to their
        # defining constraints (see below), they can be defined as continuous values comprised in [0,1].
        # Constraints will ensure that the value they take is always 0 or 1.
        # Convention : auxiliary variables are written in lower case

        # 1.3.1. Create the auxiliary variables that will always be defined
        for t in self.time_frame:
            self.turned_on.set_model_var(t)
            self.turned_off.set_model_var(t)

        # 1.3.2. Create the condtionnal auxiliary variables if necessary.

        # Variable indicating that the unit is stable at t (sec. 6.1.3)
        # and variables to constrain the gradient U[t], D[t] and tilde_U[t], tilde_D[t] (defined in sec 6.2.4.)
        if self.T_stable >= 1:
            # Define the time_frame_union_minus_one which includes the start_date_minus_one time step.
            self.time_frame_union_minus_one = generate_datetimes(
                self.parameters.temporal.start_date - self.parameters.temporal.timestep,
                self.parameters.temporal.end_date
                + self.thermal_unit.additional_hours
                - self.parameters.temporal.timestep,
                self.parameters.temporal.timestep,
            )

            # Define dummy bounds for the gradient auxiliaries
            self.Q_max = self.delta_q_unconstrained
            self.Q_min = -self.Q_max

            for t in self.time_frame_union_minus_one:
                # Define the auxiliary variables of this state.
                self.stable.set_model_var(t)
                self.entered_up.set_model_var(t)
                self.entered_down.set_model_var(t)

            for t in self.time_frame:
                # Initialize the gradient auxiliaries.
                self.U.set_model_var(t)
                self.D.set_model_var(t)
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
        """
        STEP 2 : Creation of objective function
        :param direction: the direction of the objective function
        :type direction: Literal["maximize", "minimize"]
        :return: None
        """
        # Set-up the objective function given by eq. (2) in the documentation.
        # If self.T_stable = 0, we don't need to include automatedContractedReservesUp and automatedContractedReservesDown to the objective function.
        # otherwise we need to include them.
        self.set_direction(direction)
        self.add_objective(
            objective_expr=(
                sum(
                    self.q.get_value(t)
                    * (self.parameters.temporal.timestep.total_hours())
                    * (self.prices.get_value(t) - self.thermal_unit.variable_cost.get_value(t))
                    - self.turned_on.get_value(t) * self.thermal_unit.startup_cost.get_value(t)
                    - self.parameters.manual_unprocured_reserves_penalty
                    * (self.parameters.temporal.timestep.total_hours())
                    * (
                        self.get_variable(self.contracted_difference_up_at(t))
                        + self.get_variable(self.contracted_difference_down_at(t))
                    )
                    - self.parameters.automated_unprocured_reserves_penalty
                    * (self.parameters.temporal.timestep.total_hours())
                    * (
                        self.get_variable(self.automated_contracted_difference_up_at(t))
                        + self.get_variable(self.automated_contracted_difference_down_at(t))
                    )
                    for t in self.time_frame
                )
                - self.parameters.automated_unprocured_reserves_penalty
                * (self.parameters.temporal.timestep.total_hours())
                * self.automated_unsupplied_reserves
            ),
        )

    def determine_combination(self) -> int:
        """
        Determine which of the 8 constraint combinations to use.
        STEP 3 : Constraints and initial conditions
        Constraints and initial conditions are defined based on state and auxiliary variables.
        Since these variables are not necessarily defined, in the following we go through all
        8 possible combinations of state and auxiliary variables and write the corresponding
        initial conditions and set of constraints all at once.

        Initial conditions are defined on the previous_time_frame, constraints on the state and
        control variables are defined on the time_frame.

        :return: determine the combination to use
        :rtype: int
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
        :return: results: a dictionary containing the optimal values of the decision variables,
                    namely :
                        . q*, the optimal power output
                        . ON_.*, OFF*, START* and STOP* (when relevant), the optimal values of the state variables
                    All these results are returned in the form of a TimeSeries object ranging over the optimization period
                    (i.e. [start_date, end_optimization_date]).
        :rtype: dict[str, Timeseries]
        """

        if self.parameters.solver.export_lp:
            output_path = self.parameters.get_output_dir() / "lp_export"
            output_path.mkdir(parents=True, exist_ok=True)
            lp_file_path = output_path / f"{self.thermal_unit.name}_price_{self.price_type}.lp"
            self.export_model(str(lp_file_path))

        cfg.logger.info(f"Optimisation model '{self.name}' with price type '{self.price_type}'")
        self.solve()

        status = self.solution_info.status if self.solution_info else None
        cfg.logger.debug(f"Solver status: {status}")
        cfg.logger.debug(f"Objective function value: {self._objective}")

        """STEP 5 : Return the results"""

        # Export the results
        # Final step : export the results of the program. We initialize a dictionnary that will store the results.
        # This dictionnary is returned to the user.
        results: dict[str, Timeseries] = {}

        # Power output
        q_star = Timeseries.from_index(
            self.parameters.temporal.start_date,
            self.parameters.temporal.timestep,
            self.parameters.temporal.end_date,
            default_value=0,
        )
        for t in self.time_frame:
            q_star.set_value(t, self.q.get_model_var(t).solution_value())

        # inform the user if the optimal program is such that the unit
        # provides no output
        if abs(q_star.min() - 0.0) <= 1e-6 and abs(q_star.max() - 0.0) <= 1e-6:
            zero_output_message = f"""*** Info ***
            The optimal solution for the unit {self.thermal_unit.name} is such that the unit remains offline and
            delivers no power output.
            """
            cfg.logger.debug(zero_output_message)

        # contractedDifference.
        # This variable is returned as together with the procuredReserves it allows to know the exact amount
        # of reserves supplied (and unsupplied) for each time step. the reserves variables can take inexact values on the time steps
        # where there is no reserve to provide due to the fill up constraints.
        # Create the time series
        contracted_difference_up_star = Timeseries.from_index(
            self.parameters.temporal.start_date,
            self.parameters.temporal.timestep,
            self.parameters.temporal.end_date,
            default_value=0,
        )
        contracted_difference_down_star = Timeseries.from_index(
            self.parameters.temporal.start_date,
            self.parameters.temporal.timestep,
            self.parameters.temporal.end_date,
            default_value=0,
        )

        # Add the automatedDifference
        # Create the time series
        automated_contracted_difference_up_star = Timeseries.from_index(
            self.parameters.temporal.start_date,
            self.parameters.temporal.timestep,
            self.parameters.temporal.end_date,
            default_value=0,
        )
        automated_contracted_difference_down_star = Timeseries.from_index(
            self.parameters.temporal.start_date,
            self.parameters.temporal.timestep,
            self.parameters.temporal.end_date,
            default_value=0,
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
            self.parameters.temporal.start_date,
            self.parameters.temporal.timestep,
            self.parameters.temporal.end_date,
            default_value=0,
        )
        ON_DOWN_star = Timeseries.from_index(
            self.parameters.temporal.start_date,
            self.parameters.temporal.timestep,
            self.parameters.temporal.end_date,
            default_value=0,
        )
        OFF_star = Timeseries.from_index(
            self.parameters.temporal.start_date,
            self.parameters.temporal.timestep,
            self.parameters.temporal.end_date,
            default_value=0,
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
                self.parameters.temporal.start_date,
                self.parameters.temporal.timestep,
                self.parameters.temporal.end_date,
                default_value=0,
            )
            for t in self.time_frame:
                START_star.set_value(t, self.START.get_model_var(t).solution_value())
                # Add the time series to the dictionnary.
            results["START"] = START_star
        if self.T_stop >= 1:
            STOP_star = Timeseries.from_index(
                self.parameters.temporal.start_date,
                self.parameters.temporal.timestep,
                self.parameters.temporal.end_date,
                default_value=0,
            )
            for t in self.time_frame:
                STOP_star.set_value(t, self.STOP.get_model_var(t).solution_value())
            # Add the time series to the dictionnary.
            results["STOP"] = STOP_star
        if self.T_stable >= 1:
            ON_FLAT_star = Timeseries.from_index(
                self.parameters.temporal.start_date,
                self.parameters.temporal.timestep,
                self.parameters.temporal.end_date,
                default_value=0,
            )
            for t in self.time_frame:
                ON_FLAT_star.set_value(t, self.ON_FLAT.get_model_var(t).solution_value())
            results["ON_FLAT"] = ON_FLAT_star

        return results

    def create_fill_up_constraints(
        self, time_frame: list[DateTime], q: ModelVar, q_upper: Timeseries, epsilon: float, q_lower: Timeseries
    ) -> None:
        """
        Upward and downward "fill up" constraints
        :param time_frame: the time frame
        :type time_frame: list[DateTime]
        :param q: the model variable
        :type q: ModelVar
        :param q_upper: power bound
        :type q_upper: Timeseries
        :param epsilon: epsilon parameter
        :type epsilon: float
        :param q_lower: power bound
        :type q_lower: Timeseries
        :return: None
        """
        for t in time_frame:
            self.add_constraint(
                q.get_value(t)
                + self.get_variable(self.reserves_up_equip_at(t))
                + self.get_variable(self.automated_reserves_up_at(t))
                + self.get_variable(self.unprovided_reserves_up_at(t))
                <= q_upper.get_value(t) + epsilon
            )  # Upward constraint - eq. (41)
            self.add_constraint(
                q.get_value(t)
                + self.get_variable(self.reserves_up_equip_at(t))
                + self.get_variable(self.automated_reserves_up_at(t))
                + self.get_variable(self.unprovided_reserves_up_at(t))
                >= q_upper.get_value(t) - epsilon
            )  # Upward constraint - eq. (41)

            self.add_constraint(
                (
                    q.get_value(t)
                    - self.get_variable(self.reserves_down_equip_at(t))
                    - self.get_variable(self.automated_reserves_down_at(t))
                    - self.get_variable(self.unprovided_reserves_down_at(t))
                    + self.get_variable(self.relaxed_reserves_at(t))
                )
                <= q_lower.get_value(t) + epsilon
            )  # Downward constraint - eq. (42)
            self.add_constraint(
                (
                    q.get_value(t)
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
        """
        Constraints on contractedDifference (eq. (40)) and on automatedContractedDifference (eq. (39))
        :param time_frame: the time frame
        :type time_frame: list[DateTime]
        :param reserves_up_procured: manual reserves
        :type reserves_up_procured: Timeseries
        :param reserves_down_procured: manual reserves
        :type reserves_down_procured: Timeseries
        :param feasible_automated_reserves_up_procured: time series of feasible automated reserves procurements
        :type feasible_automated_reserves_up_procured: Timeseries
        :param feasible_automated_reserves_down_procured: time series of feasible automated reserves procurements
        :type feasible_automated_reserves_down_procured: Timeseries
        :return: None
        """
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

    def add_daily_energy_constraint(self) -> None:
        """
        Add daily energy constraint to the optimization model.
        This constraint limits the total energy output per day.
        Should be called once after all combination constraints are added.

        :return: None
        """
        if self.thermal_unit.has_daily_energy_constraint:
            days_in_time_frame = sorted({datetime(t.year, t.month, t.day, 0, 0, 0) for t in self.time_frame})

            for date in days_in_time_frame:
                matching_steps = [
                    t for t in self.time_frame if (t.year == date.year and t.month == date.month and t.day == date.day)
                ]

                if matching_steps and self.thermal_unit.maximum_daily_energy is not None:
                    constraint_expr = sum(
                        self.q.get_value(t) for t in matching_steps
                    ) <= self.thermal_unit.maximum_daily_energy.get_value(
                        date
                    ) * self.parameters.temporal.timestep.total_days() * len(matching_steps)
                    self.add_constraint(constraint_expr, f"energy_limit_of_{self.thermal_unit.name}_at_{date}")

    def is_day_zero(self) -> bool:
        """
        See if the program needs to be initialized as DayZero or not
        :return: if the program needs to be initialized as DayZero or not
        :rtype: bool
        """
        if len(self.last_power) == 0:
            # Initialization of the program as DayZero and warn the user
            cfg.logger.info("The program is initialized for the first time.")
            day_zero = True  # Boolean to keep track of the status
        elif self.last_date != self.parameters.temporal.start_date - self.parameters.temporal.timestep:
            # last_date doesn't match start_date - time_step (i.e. t_{-1}, so we will initialize as DayZero and send a warning message
            cfg.logger.warning(
                f"The last_date found in Power of equipement {self.thermal_unit.name} "
                "does not match the start_date of the current program. \n "
                "The program will be initialized as DayZero."
            )
            day_zero = True
        else:
            day_zero = False
            # Setting up the initial conditions of the program
        return day_zero
