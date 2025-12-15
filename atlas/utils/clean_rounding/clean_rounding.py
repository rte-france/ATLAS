from datetime import datetime, timedelta
from typing import List, Tuple

import pandas as pd

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
from atlas.utils.clean_rounding.clean_rounding_parameters import CleanRoundingParameters


def clean_rounding(equipment: Equipment, parameters: CleanRoundingParameters):
    """
    TODO: docstring
    Modifies the equipment's timeseries in place.
    """
    indexes_list = _get_indexes_in_time_window(equipment.power, parameters.start_date, parameters.end_date)
    for local_index in indexes_list:
        new_timeseries = equipment.power.select(local_index)
        min_power, max_power = _get_minimum_and_maximum_powers(equipment, local_index, new_timeseries, parameters)
        new_timeseries.round(parameters.rounding_precision)
        _post_process_rounding(equipment, max_power, min_power, new_timeseries, parameters)
        equipment.power.replace(local_index, new_timeseries)


def _get_indexes_in_time_window(
    forecasting_matrix: ForecastingMatrix, start_date: datetime, end_date: datetime
) -> List[datetime]:
    return list(
        filter(
            lambda index: start_date <= index <= end_date,
            forecasting_matrix.indexes,
        )
    )


def _get_minimum_and_maximum_powers(
    equipment: Equipment,
    local_index: datetime,
    new_timeseries: Timeseries,
    parameters: CleanRoundingParameters,
) -> Tuple[Timeseries, Timeseries]:
    if isinstance(equipment, (Wind, Solar, OtherNonDispatchable)):
        maximum_power = equipment.maximum_power_forecast.get_forecast(
            local_index,
            parameters.start_date,
            parameters.end_date,
            new_timeseries.timestep,
        )
        minimum_power = Timeseries(pd.DataFrame(index=new_timeseries.index))  # TODO: fill with proper values
        return minimum_power, maximum_power
    elif isinstance(equipment, Load):
        maximum_power = equipment.maximum_power_forecast.get_forecast(
            local_index,
            parameters.start_date,
            parameters.end_date,
            new_timeseries.timestep,
        )
        minimum_power = Timeseries(pd.DataFrame(index=new_timeseries.index))  # TODO: fill with proper values
        return minimum_power, maximum_power
    else:
        return equipment.minimum_power, equipment.maximum_power


def _post_process_rounding(equipment, max_power, min_power, new_timeseries, parameters):
    _check_bounds(equipment, max_power, min_power, new_timeseries, parameters)
    _post_process_timestamps_in_ramps(equipment, new_timeseries)


def _check_bounds(
    equipment: Equipment,
    max_power: Timeseries,
    min_power: Timeseries,
    new_timeseries: Timeseries,
    parameters: CleanRoundingParameters,
):
    """
    Ensures that no value was rounded above the maximum admissible power or below the minimum.
    """
    for time in new_timeseries.index:
        # Ensure that no value was rounded above the maximum admissible value, for all types of equipments
        new_timeseries.set_value(
            time,
            min(new_timeseries.get_value(time), max_power.get_value(time)),
        )

        # Ensure that no value was rounded below the minimum admissible value
        if isinstance(equipment, Thermal):
            if abs(min_power.get_value(time) - new_timeseries.get_value(time)) < parameters.epsilon:
                new_timeseries.set_value(time, min_power.get_value(time))
        else:
            new_timeseries.set_value(
                time,
                max(new_timeseries.get_value(time), min_power.get_value(time)),
            )


def _post_process_timestamps_in_ramps(equipment: Equipment, new_timeseries: Timeseries):
    # Ramps (has to be performed after the entire max/min power correction)
    in_ramp = {}
    if isinstance(equipment, Thermal):
        if equipment.minimum_stable_power_duration.in_hours() > new_timeseries.timestep.in_minutes() / 60.0:
            for time in new_timeseries.index:
                if time != new_timeseries.index[-1]:
                    if new_timeseries.get_value(time) != new_timeseries.get_value(
                        time + timedelta(minutes=new_timeseries.timestep.in_minutes())
                    ):
                        in_ramp[time] = True
                    else:
                        in_ramp[time] = False
                else:
                    in_ramp[time] = False

    # Correct ramps if necessary
    corrected_ts = []
    for time in sorted(in_ramp.keys()):
        if time not in corrected_ts and in_ramp[time]:
            # Identify ramps over more than one time step
            total_ramp = [time]

            for time_step_added in range(1, len(new_timeseries.index)):
                local_time = time + timedelta(minutes=new_timeseries.timestep.in_minutes() * time_step_added)
                if local_time in in_ramp.keys() and in_ramp[local_time]:
                    total_ramp.append(local_time)

            # Correct the ramp
            if len(total_ramp) > 1:
                first_value = new_timeseries.get_value(total_ramp[0])
                last_value = new_timeseries.get_value(
                    total_ramp[-1] + timedelta(minutes=new_timeseries.timestep.in_minutes())
                )

                # Do not correct if there is a startup or a shutdown
                if first_value == 0 or last_value == 0:
                    for local_time in total_ramp:
                        corrected_ts.append(local_time)

                update_value = (last_value - first_value) / len(total_ramp)

                for local_enum, local_time in enumerate(total_ramp):
                    # following behavior is acceptable because time steps are always evenly spread
                    # and "in-ramp" values are always interpolated from extreme ramp values, so their actual rounding does not matter
                    if local_enum > 0:
                        new_timeseries.set_value(local_time, first_value + update_value * local_enum)
                    corrected_ts.append(local_time)
