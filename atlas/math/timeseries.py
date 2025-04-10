"""Copyright (c) 2016-2022, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements Timeseries class
"""

import datetime
import logging
from copy import deepcopy

import numpy as np
import pandas as pd

import atlas.config as cfg


class UnloadedTimeSeries:
    def __init__(self, attribute):
        self.attribute = attribute

    def __eq__(self, other_timeserie):
        """Test whether two UnloadedTimeSeries objects are equals.
        Objects are considered equal if they store the same values in their 'attribute' attribute.

        :param other_timeserie: TimesSeries. The other timeserie to compare to.
        :return: bool. True if equal else False.
        """
        return self.attribute == other_timeserie.attribute

    def create_timeseries(self, data_manager):
        """Create a Timeseries by converting value given in this object

        :param data_manager: DataManager.
        :return: Timeseries. Newly created Timeseries
        """
        if self.attribute["timeserie"] is None:
            ts_value, ts_date = [], []
        else:
            ts_id = self.attribute["timeserie"]
            ts = data_manager.timeseries[ts_id]
            ts_value = ts[:, 1]
            # TODO The method pd.to_datetime takes most of the time for timeseries deserialization
            #  Idea: test using ts[:, 0].astype('datetime64[ns]') ?
            # Maybe don't create it yet
            ts_date = ts[:, 0].astype("datetime64[ns]")
        return Timeseries(
            self.attribute["Name"],
            self.attribute["Interpolation"],
            self.attribute["Unit"],
            ts_date,
            ts_value,
        )


class Timeseries:
    """A Timeseries stores a list of numerical numbers associated with a date."""

    def __init__(self, name, interpolation, unit, datetimes, values):
        """:param name: str. Name of the timeseries
        :param interpolation: TimeSeriesInterpolation. Interpolation method to use when
        trying to get the value of a missing datetime in the timeseries
        :param unit: str. Unit of the values
        :param datetimes: List of datetime. Indexes of the timeseries
        :param values: numerical or list of numerical. Values of the timeseries, if a list, its length must be equal to
        datetimes length
        """
        if isinstance(values, (int, float)):
            values = np.full(len(datetimes), values)
        if len(datetimes) != len(values):
            raise ValueError(
                "datetimes and values parameters must contain the same number of elements",
            )

        self.name = name
        self.interpolation = interpolation
        self.unit = unit
        self.series = pd.Series(values, datetimes, dtype=float)
        self.series = self.series.sort_index()
        # Convert index to datetime in case datetimes is empty list
        if len(datetimes) == 0:
            self.series.index = pd.to_datetime(self.series.index)

    @classmethod
    def from_pd_series(cls, name, interpolation, unit, pd_series):
        """Creates a Timeseries object from a pd.Series object
        :param name: str. Name of the timeseries.
        :param interpolation: TimeSeriesInterpolation. Interpolation method to use when trying to get the value of a
        missing datetime in the timeseries.
        :param unit: str. Unit of the values.
        :param pd_series: pd.Series. The series containing values and datetimes.
        :return: Timeseries
        """
        return cls(name, interpolation, unit, pd_series.index, pd_series.values.squeeze())

    @classmethod
    def series_range(
        cls,
        name,
        interpolation,
        unit,
        start_date=None,
        end_date=None,
        freq=None,
        length=None,
        value=0,
    ):
        """Method that creates a new Timeseries given a start date, a frequency, a length and a value to fill.
        :param name: str. Name of the timeseries.
        :param interpolation: TimeSeriesInterpolation. Interpolation method to use when trying to get the value of a
        missing datetime in the timeseries.
        :param unit: str. Unit of the values.
        :param start_date: datetime. The start date of the timeseries.
        :param end_date: datetime. The end date of the timeseries.
        :param freq: str. String representing the frequency of the timeseries.
        :param length: int. The length of the timeseries.
        :param value: float. The value to fill the timeseries with.
        :return: Timeseries.
        """
        datetimes = pd.date_range(start=start_date, end=end_date, periods=length, freq=freq)
        values = [value] * len(datetimes)
        return cls(name, interpolation, unit, datetimes, values)

    @classmethod
    def new_index(
        cls,
        start_date: datetime,
        end_date: datetime,
        interval: datetime.timedelta,
    ) -> list[datetime]:
        """Generate a list of datetime between `start` and `end` depending on the given interval.

        :param start_date: first datetime
        :param end_date: last datetime
        :param interval: time interval (timedelta)
        :return: datetime list
        """
        if start_date >= end_date:
            raise ValueError("start date must be before end date.")

        result = []
        current = start_date
        while current <= end_date:
            result.append(current)
            current = current + interval

        return result

    def __eq__(self, other_timeserie):
        """Test whether two Timeseries objects are equals.
        Objects are considered equal if they store the same name, interpolation, unit and date/values.

        :param other_timeserie: TimesSeries. The other timeserie to compare to.
        :return: bool. True if equal else False.
        """
        if self.name != other_timeserie.name:
            return False
        if self.interpolation != other_timeserie.interpolation:
            return False
        if self.unit != other_timeserie.unit:
            return False
        if not self.series.index.equals(other_timeserie.series.index):
            return False
        # Use np.allclose to avoid False negative due to round error on float
        return np.allclose(self.series.values, other_timeserie.series.values)

    def get_value(self, index, interpol=None):
        """Returns a value or list of values for the given index(es) using the interpolation method. If interpol is not
        given, the Timeseries interpolation attribute is used

        :param index: Datetime or list of datetime. Datetime(s) to get value(s) from the timeseries
        :param interpol: TimeSeriesInterpolation. Method to interpolate missing value(s) in the timeseries. Default
        value is the object interpolation attribute
        :return: double or list of double
        """
        if len(self.series) == 0:
            if isinstance(index, datetime.datetime):
                return None
            return np.zeros(len(index))

        scalar_input = False
        if isinstance(index, datetime.datetime):
            index = [index]
            scalar_input = True

        if interpol is None:
            interpol = self.interpolation

        new_series = self.series.add(pd.Series(np.nan, index), fill_value=0)

        if interpol is cfg.TimeSeriesInterpolation.LINEAR:
            res_values = new_series.interpolate(method="polynomial", order=1, limit_area="inside")[
                index
            ].values
        elif interpol is cfg.TimeSeriesInterpolation.LINEAR_AVERAGE:
            res_values = (
                new_series.ffill(limit_area="inside")[index].values
                + new_series.bfill(limit_area="inside")[index].values
            ) / 2
        elif interpol is cfg.TimeSeriesInterpolation.CONSTANT:
            res_values = new_series.ffill(limit_area="inside")[index].values
        else:
            raise NotImplementedError(
                f"Interpolation method {interpol} not implemented for Timeseries",
            )

        # Replace nan by 0
        res_values[np.isnan(res_values)] = 0

        if scalar_input:
            return res_values[0]
        return res_values

    def set_value(self, index: datetime, value: float):
        self.series.at[index] = value

    def __getitem__(self, index):
        """Returns a value or list of values for the given index(es) using the Timeseries interpolation method

        :param index: Datetime or list of datetime. Datetime(s) to get value(s) from the timeseries
        value is the object interpolation attribute
        :return: double or list of double
        """
        return self.get_value(index)

    def slice(self, start_date, end_date):
        """Returns a Timeseries extracted between the two date given as parameter

        :param start_date: datetime. Beginning of slice interval
        :param end_date: datetime. End of slice
        :return: Timeseries
        """
        timeserie = deepcopy(self)
        timeserie.series = timeserie.series[start_date:end_date]

        return timeserie

    def __len__(self):
        return len(self.series)

    def merge(self, timeserie, name=None):
        """Merge two timeseries together to create a new one. If they have indexes in
        common, values of the second timeserie will be kept. The interpolation type of the
        second timeserie will be also kept.

        :param timeserie: Timeseries. Timeserie to merge with the current one
        :param name: str. Name of the new timeseries
        :return: Timeseries
        """
        res_timeserie = deepcopy(timeserie)
        res_timeserie.series = res_timeserie.series.combine_first(self.series)
        if name is not None:
            res_timeserie.name = name

        return res_timeserie

    def extract(self, name, times, interpolation=None):
        """Returns a Timeseries extracted using the given list of dates and the interpolation method of the Timeseries

        :param name: str. Name of the extracted Timeseries
        :param times: list of datetime. Datetime(s) to get value(s) from the input TimesSeries
        :param interpolation: TimeSeriesInterpolation. Method to interpolate missing data. Default value is Timeseries
        object interpolation attribute
        :return: Timeseries
        """
        if interpolation is None:
            interpolation = self.interpolation

        values = self.get_value(times, interpolation)
        return Timeseries(name, interpolation, self.unit, times, values)

    def __add__(self, other):
        """Returns the sum between a Timeseries and another Timeseries or a number, if a Timeseries, their
        values are added and their values are interpolated to have a 1-1 match on indexes, if a number, each value of
        the Timeseries is increase by this value.

        :param other: Timeseries or number. The other Timeseries or value to add.
        :return: Timeseries
        """
        timeserie = deepcopy(self)
        if isinstance(other, (int, float)):
            timeserie.series += other
            return timeserie
        indexes = self.series.index.union(other.series.index)
        # Use interpolation to get value for each indexes
        values = timeserie[indexes] + other[indexes]
        name = f"{self.name} + {other.name}"
        unit = self.unit
        interpolation = self.interpolation
        return Timeseries(name, interpolation, unit, indexes, values)

    def __mul__(self, other):
        """Returns the multiplication between a Timeseries and another Timeseries or a number, if a Timeseries, their
        values are multiplied and their values are interpolated to have a 1-1 match on indexes, if a number, each value
        of the Timeseries is multiplied by this value.

        :param other: Timeseries or number. The other Timeseries or value to multiply.
        :return: Timeseries
        """
        timeserie = deepcopy(self)
        if isinstance(other, (int, float)):
            timeserie.series *= other
            return timeserie
        indexes = self.series.index.union(other.series.index)
        # Use interpolation to get value for each indexes
        values = timeserie[indexes] * other[indexes]
        name = f"{self.name} * {other.name}"
        unit = self.unit
        interpolation = self.interpolation
        return Timeseries(name, interpolation, unit, indexes, values)

    def __sub__(self, other):
        """Returns the subtraction between a Timeseries and another Timeseries or a number, if a Timeseries, their
        values are substracted and their values are interpolated to have a 1-1 match on indexes, if a number, each value
        of the Timeseries is reduced by this value.

        :param other: Timeseries or number. The other Timeseries or value to substract.
        :return: Timeseries
        """
        timeserie = deepcopy(self)
        if isinstance(other, (int, float)):
            timeserie.series += other
            return timeserie
        indexes = self.series.index.union(other.series.index)
        # Use interpolation to get value for each indexes
        values = timeserie[indexes] - other[indexes]
        name = f"{self.name} - {other.name}"
        unit = self.unit
        interpolation = self.interpolation
        return Timeseries(name, interpolation, unit, indexes, values)

    # Define right operations to make work operations float + Timeseries, float - Timeseries, float * Timeseries.
    __rmul__ = __mul__
    __radd__ = __add__
    __rsub__ = __sub__

    @staticmethod
    def safe_extract(time_series, name, times):
        """This function makes sure the time_series parameter is not None before extracting it. If so, a None value is
        returned, else the Timeseries is extracted normally.

        :param time_series: Timeseries. The Timeseries to safely extract
        :param name: str. The name to give to the extracted Timeseries
        :param times: list of datetime. Datetime(s) to get value(s) from the input TimesSeries
        :return: Timeseries
        """
        if time_series is not None and len(time_series) != 0:
            return time_series.extract(name, times)
        return None

    # Helper for extracting Timeseries with default values in case of failure:
    @staticmethod
    def safe_extract_with_default(time_series, name, times, default_value):
        """This function makes sure the time_series parameter is not None before extracting it. If so, a constant
        Timeseries is generated and returned instead, based on the set of simulation times as index and filled with the
        provided default_value.

        :param time_series: Timeseries. The Timeseries to safely extract
        :param name: str. The name to give to the extracted Timeseries
        :param times: list of datetime. Datetime(s) to get value(s) from the input TimesSeries
        :param default_value: float. Value to fill the returned Timeseries with if input time_series parameter is None
        :return: Timeseries
        """
        if time_series is not None and len(time_series) != 0:
            return time_series.extract(name, times)
        logging.warning(f"Taking default value {default_value} for {name}")
        return Timeseries(
            name,
            cfg.TimeSeriesInterpolation.CONSTANT,
            "MW",
            times,
            np.full(len(times), default_value),
        )
