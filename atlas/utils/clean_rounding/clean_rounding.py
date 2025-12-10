from datetime import datetime, timedelta
from typing import List

import pandas as pd
from pendulum._pendulum import Duration

from atlas import (
    Equipment,
    ForecastingMatrix,
    Load,
    OtherNonDispatchable,
    Solar,
    Thermal,
    Timeseries,
    Wind,
)
from atlas.utils.api.abc_prototype import ABCPrototype
from atlas.utils.clean_rounding.clean_rounding_parameters import CleanRoundingParameters


# QUESTION: do we want to use objects or are static functions enough?
# TODO: [General] Remove time step from parameters and always use timeseries'
class CleanRounding(ABCPrototype):
    def __init__(self, parameters: CleanRoundingParameters):
        super().__init__()
        self.__parameters = parameters

    def _get_indexes(self, forecasting_matrix: ForecastingMatrix) -> List[datetime]:
        return list(
            filter(
                lambda index: self.__parameters.start_date <= index <= self.__parameters.end_date,
                forecasting_matrix.indexes,
            )
        )

    def _update_equipment(self, equipment: Equipment):
        indexes_list = self._get_indexes(equipment.power)
        if not isinstance(equipment, (Wind, Solar, Load, OtherNonDispatchable)):
            max_power = equipment.maximum_power
            min_power = equipment.minimum_power
        for local_index in indexes_list:
            new_time_series = equipment.power.select(local_index)
            timestep = new_time_series.timestep

            if isinstance(equipment, (Wind, Solar, OtherNonDispatchable)):
                max_power = equipment.maximum_power_forecast.get_forecast(
                    local_index,
                    self.__parameters.start_date,
                    self.__parameters.end_date,
                    timestep,
                )
                min_power = Timeseries(pd.DataFrame(index=new_time_series.index))  # TODO: fill with proper values

            elif isinstance(equipment, Load):
                min_power = equipment.maximum_power_forecast.get_forecast(
                    local_index,
                    self.__parameters.start_date,
                    self.__parameters.end_date,
                    timestep,
                )
                max_power = Timeseries(pd.DataFrame(index=new_time_series.index))  # TODO: fill with proper values

            new_time_series.round(self.__parameters.rounding_precision)
            new_time_series.timestep.in_minutes()

            # -> Rounding process may have rounded some values above the maximum or below the minimum power
            # -> TODO: explain why ramps have to be dealt with separately if the minimum stable duration is > 1h

            # TODO: extract following block in a separate method
            for time in new_time_series.index:
                # Ensure that no value was rounded above the maximum admissible value, for all types of equipments
                new_time_series.set_value(
                    time,
                    min(new_time_series.get_value(time), max_power.get_value(time)),
                )

                # Ensure that no value was rounded below the minimum admissible value
                if isinstance(equipment, Thermal):
                    if abs(min_power.get_value(time) - new_time_series.get_value(time)) < self.__parameters.epsilon:
                        new_time_series.set_value(time, min_power.get_value(time))
                else:
                    new_time_series.set_value(
                        time,
                        max(new_time_series.get_value(time), min_power.get_value(time)),
                    )

            # TODO: extract following block in a separate method
            # Ramps (has to be performed after the entire max/min power correction)
            in_ramp = {}
            if isinstance(equipment, Thermal):
                if equipment.minimum_stable_power_duration.in_hours() > timestep.in_minutes() / 60.0:
                    for time in new_time_series.index:
                        if time != new_time_series.index[-1]:
                            # QUESTION: are we sure that the other timestamp will always be in the timeseries?
                            # ANSWER: same as other TS questions
                            if new_time_series.get_value(time) != new_time_series.get_value(
                                time + timedelta(minutes=timestep.in_minutes())
                            ):
                                in_ramp[time] = True
                            else:
                                in_ramp[time] = False
                        else:
                            in_ramp[time] = False

            # TODO: extract following block in a separate method
            # Correct ramps if necessary
            corrected_ts = []
            for time in sorted(in_ramp.keys()):
                if time not in corrected_ts and in_ramp[time]:
                    # Identify ramps over more than one time step
                    total_ramp = [time]

                    for time_step_added in range(1, len(new_time_series.index)):
                        local_time = time + timedelta(minutes=timestep.in_minutes() * time_step_added)
                        if local_time in in_ramp.keys() and in_ramp[local_time]:
                            total_ramp.append(local_time)

                    # Correct the ramp
                    if len(total_ramp) > 1:
                        first_value = new_time_series.get_value(total_ramp[0])
                        last_value = new_time_series.get_value(
                            total_ramp[-1] + timedelta(minutes=timestep.in_minutes())
                        )

                        # Do not correct if there is a startup or a shutdown
                        if first_value == 0 or last_value == 0:
                            for local_time in total_ramp:
                                corrected_ts.append(local_time)

                        update_value = (last_value - first_value) / len(total_ramp)

                        for local_enum, local_time in enumerate(total_ramp):
                            if local_enum == 0:
                                corrected_ts.append(local_time)
                                continue

                            # following behavior is acceptable because time steps are always evenly spread
                            # and "in-ramp" values are always interpolated from extreme ramp values, so their actual rounding does not matter
                            new_time_series.set_value(local_time, first_value + update_value * local_enum)
                            corrected_ts.append(local_time)

            equipment.power.delete(local_index)
            equipment.power.add(new_time_series, local_index)

            new_time_series.timeseries = None
