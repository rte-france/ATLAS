"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import math

from pendulum import DateTime

import atlas.config as cfg
from atlas import generate_datetimes
from atlas.enum import ThermalStrategy
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.dao_output_dataset import DayAheadOrdersOutputDataset
from atlas.modules.day_ahead_orders.dao_parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.dao_timeseries import DAOTimeseries
from atlas.modules.day_ahead_orders.data_models.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.orders_formulation.thermal.thermal_unit_orders import ThermalUnitOrders


class ThermalBaseLoadOrders(ThermalUnitOrders):
    """Order formulation for each strategy"""

    def __init__(
        self, dataset: DayAheadOrdersOutputDataset, orders_time: list[DateTime], parameters: DayAheadOrdersParameters
    ):
        super().__init__(dataset, orders_time, parameters)

    def formulate_thermal_baseload_orders(self) -> None:
        """
        This function formulates offers for the thermic baseload units.
        Baseload units are identified thanks to an attribute of the thermic class.

        Returns None
        """

        # Filter the baseload instances
        equipments_list = [eqt for eqt in self.dataset.thermal if eqt.strategy == ThermalStrategy.BASE]

        # We stop here if there is no baseload load units in the dataset
        if not equipments_list:
            cfg.logger.info("No baseload units were found in the dataset.")
            return None

        # Start the formulation of the orders
        for unit in equipments_list:
            # Get the states sequence and the inconsistency status of the unit.
            states_sequence, inconsistent = self.determine_baseload_states_sequence(unit)
            if inconsistent:  # skip the unit if its states sequence is inconsistent.
                cfg.logger.warning(
                    f"*** WARNING ***\n Equipment {unit.name}'s states sequence is inconsistent. "
                    "No orders have been formulated for this unit"
                )
                continue

            # Retrieve the time steps over which the unit is oneline.
            list_of_online_timeframes = self.extract_online_sequences(states_sequence)

            # Formulate the orders over each online timeframe.
            for online_timeframe in list_of_online_timeframes:
                self.formulate_unit_orders(online_timeframe, unit)

    def determine_baseload_states_sequence(self, unit: ThermalDAO) -> tuple[Timeseries, bool]:
        """
        Computes the sequence of states on a single time frame for the baseload unit passed as input.

        The encoding of the states is the following:
        - 0 if the unit is offline at t
        - 1 if the unit is online at t
        - 2 if the unit is in its start up phase at t
        - 3 if the unit is in its shutdown phase at t

        The sequence of states is computed over the extended time frame, retrieved with the input parameters.
        For the baseload unit, the extentedTimeFrame corresponds to start_date - T_traceback * time_step , ... , end_date + T_traceback * time_step

        REMARK : if there are more than one start up and one shutdown over the period, the program will be considered as inconsistent.

        Arguments :
        unit : the unit to be analysed

        Returns :
        states_sequence : a timeSeries object encoding the states at each time t.
        inconsistent : a boolean indicating whether the reconstructed time series exhibits any inconsistency
                       with respect to the unit's parameters.
        """

        # Intialize the value of the boolean inconsistent
        inconsistent = False

        # Sanity check : see whether the unit passed as an input is a baselaod unit. Otherwise raise an error.
        if not unit.strategy == ThermalStrategy.BASE:
            cfg.logger.error(f"*** WARNING ***\n Equipement {unit.name} is not of strategy 'Base'.")
            raise ValueError("Wrong equipment type for the thermic optimization program.")

        # Parameters from the unit
        T_on = int(max(1, math.ceil(unit.minimum_time_on / self.parameters.time_step)))
        T_off = int(max(1, math.ceil(unit.minimum_time_off / self.parameters.time_step)))
        T_start = int(math.floor(unit.startup_duration / self.parameters.time_step))
        T_stop = int(math.floor(unit.shutdown_duration / self.parameters.time_step))

        # MaximumPower of the unit
        maximum_power = unit.maximum_power

        # Compute T_traceback
        T_traceback = int(max(T_on + T_start, T_off + T_stop)) + 1

        # extended_start_date and extended_end_date
        extended_start_date = self.parameters.start_date - T_traceback * self.parameters.time_step
        extended_end_date = self.parameters.end_date - T_traceback * self.parameters.time_step

        # extended_time_frame
        extended_time_frame = generate_datetimes(extended_start_date, extended_end_date, self.parameters.time_step)

        # Initialize the output time series
        states_sequence = DAOTimeseries(
            Timeseries.from_index(
                start_date=extended_start_date,
                frequency=self.parameters.time_step,
                end_date=extended_end_date,
                default_value=0,
            )
        )

        # Iterate trough the unit's maximum_power and based on the current value, determine whether the unit
        for t in extended_time_frame:
            if maximum_power is not None and t in maximum_power and maximum_power.get_value(t) > 0:
                states_sequence.set_or_add_value(t, 1)

        # See if there is only one startup or shutdown over the time frame. If it is not the case,
        # the program will be considered as inconsistent.
        startup_count, shutdown_count = 0, 0
        for t in extended_time_frame[1:]:
            t_prev = t - self.parameters.time_step
            if states_sequence.get_value(t) - states_sequence.get_value(t_prev) == 1:
                startup_count += 1
            elif states_sequence.get_value(t_prev) - states_sequence.get_value(t) == 1:
                shutdown_count += 1

        # If there is more than one start up or one shutdown, the sequence is considered as inconsistent.
        if startup_count > 1 or shutdown_count > 1:
            inconsistent = True
            return states_sequence, inconsistent

        # Reconstruction of the start ups and the shutdown phases
        if T_start > 0 or T_stop > 0:  # Do this only if relevant
            # Reconstruction of the start ups
            for t in extended_time_frame[1:]:
                t_prev = t - self.parameters.time_step
                if states_sequence.get_value(t) - states_sequence.get_value(t_prev) == 1:
                    # Reconstruction of the start up phase which begins at t
                    started_at_t = t
                    # Determine the end of the start up phase
                    end_of_start_up = started_at_t + T_start * self.parameters.time_step
                    # Instanciate the startup time Frame
                    # En end is shifted of une time step because the unit ends its start-up and the beginning of the time step
                    # end_of_start_up.
                    startup_time_frame = generate_datetimes(
                        started_at_t, end_of_start_up - self.parameters.time_step, self.parameters.time_step
                    )
                    break  # Interrupt when the first startup is found.
                else:
                    startup_time_frame = []  # Create an empty startup_time_frame if no start ups are found.

            # Reconstruction of the shutdowns
            for t in extended_time_frame[1:]:
                t_prev = t - self.parameters.time_step
                if states_sequence.get_value(t_prev) - states_sequence.get_value(t) == 1:
                    # Reconstruction of the shutdown phase which ends at t-1
                    end_of_shutdown = t
                    # Determine the beginning of the shutdown
                    stopped_at_t = end_of_shutdown - T_stop * self.parameters.time_step
                    # Instanciate the shutdown time frame
                    # The beginning is shifted by one time step because the unit formally end its shutdown at the end of the
                    # time step end_of_shutdown
                    shutdown_time_frame = generate_datetimes(
                        stopped_at_t, end_of_shutdown - self.parameters.time_step, self.parameters.time_step
                    )
                    break  # Interrupt when the first startup is found.
                else:
                    shutdown_time_frame = []  # Create an empty shutdown_time_frame if no shutdowns are found.

            # Sanity checks
            if startup_time_frame and shutdown_time_frame:
                # See if the startup and shutdowns are overlapping
                overlapping_time_steps = set(startup_time_frame) & set(shutdown_time_frame)
                if overlapping_time_steps:
                    inconsistent = True
                    return states_sequence, inconsistent

                # See if the spell between the end of the start up and the beginning of the shutdown is greater than T_on
                if (end_of_shutdown - started_at_t).total_minutes() >= 0 and int(
                    math.floor((stopped_at_t - end_of_start_up) / self.parameters.time_step)
                ) < T_on:
                    inconsistent = True
                    return states_sequence, inconsistent
                # See if the spell between the end of the shutdown and the beginning of the shutdown is greater than T_off
                elif (end_of_shutdown - started_at_t).total_minutes() < 0 and int(
                    math.floor((started_at_t - end_of_shutdown) / self.parameters.time_step)
                ) < T_off:
                    inconsistent = True
                    return states_sequence, inconsistent

            # Update the values in the time series, if those values are not inconsistent
            if not inconsistent:
                if startup_time_frame:
                    for t in startup_time_frame:
                        states_sequence.set_or_add_value(t, 2)
                if shutdown_time_frame:
                    for t in shutdown_time_frame:
                        states_sequence.set_or_add_value(t, 3)

        return states_sequence, inconsistent
