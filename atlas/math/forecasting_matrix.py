"""Copyright (c) 2016-2022, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements ForecastingMatrix
"""

from datetime import datetime

from .timeseries import TimeSeries
from .timeseries_interpolation import CONSTANT


class ForecastingMatrix:
    """A class that stores TimeSeries by datetimes and allows to access
    and delete them by their datetimes.
    """

    def __init__(self, name, forecasting_dates=None, timeseries=None):
        """Create a ForecastingMatrix from a list of datetimes and timeseries.

        :param name: str. Name of the matrix
        :param forecasting_dates: list of str. Name of each scenario of the matrix
        :param timeseries: list of Timeseries. Timeserie of each scenario of the matrix
        """
        if forecasting_dates is None:
            forecasting_dates = []
        if timeseries is None:
            timeseries = []

        if len(forecasting_dates) != len(timeseries):
            raise ValueError(
                "forecasting_dates and timeseries parameters must contain the same number of elements",
            )

        self.name = name
        self.forecasting_dates = sorted(forecasting_dates)
        self.forecasts = dict(zip(forecasting_dates, timeseries, strict=False))

    def __len__(self):
        return len(self.forecasts)

    def __eq__(self, other_matrix):
        """Test whether two ForecastingMatrix objects are equal.
        Objects are considered equal if they store the same name and forecasting dates/timeseries.

        :param other_matrix: ForecastingMatrix. The other forecasting matrix to compare to.
        :return: True if equal else False.
        """
        if self.name != other_matrix.name:
            return False
        if self.forecasting_dates != other_matrix.forecasting_dates:
            return False
        if self.forecasts.keys() != other_matrix.forecasts.keys():
            return False
        for date, timeserie in self.forecasts.items():
            if timeserie != other_matrix.forecasts[date]:
                return False
        return True

    def add_timeseries(self, index, timeserie):
        """Add a timeserie at the given index in the matrix.

        :param index: datetime. The index to set the timeseries in the matrix
        :param timeserie: TimeSeries. The timeserie to add in the matrix
        :return: TimeSeries
        """
        if not isinstance(index, datetime):
            raise TypeError(f"Expected index type datetime, got {type(index)}")

        if not isinstance(timeserie, TimeSeries):
            raise TypeError(f"Expected timeserie type TimeSeries, got {type(index)}")

        self.forecasting_dates.append(index)
        self.forecasting_dates.sort()
        self.forecasts[index] = timeserie

    def delete_timeseries(self, index):
        """Delete timeserie at the given index in the matrix.

        :param index: datetime. The index of the timeserie to delete in the matrix
        :return:
        """
        if not isinstance(index, datetime):
            raise TypeError(f"Expected index type datetime, got {type(index)}")

        if index not in self.forecasting_dates:
            raise ValueError(f"index argument {index} is not present in forecasting_dates")

        if index in self.forecasts:
            # Delete value in scenarios dict
            del self.forecasts[index]
            # Find its index in indexes list and delete it
            ind = self.forecasting_dates.index(index)
            del self.forecasting_dates[ind]

    def extract(self, index, start_date, end_date):
        """Extract a part of a timeseries contained in the matrix at the given index

        :param index: datetime. The index of the timeseries to get in the matrix
        :param start_date: datetime. Begining of the extraction interval
        :param end_date: datetime. End of the extraction interval
        :return: TimeSeries
        """
        if not isinstance(index, datetime):
            raise TypeError(f"Expected index type datetime, got {type(datetime)}")

        if index not in self.forecasting_dates:
            raise ValueError(f"index argument {index} is not present in forecasting_dates")

        timeserie = self.forecasts[index]
        return timeserie.slice(start_date, end_date)

    def get_forecast(self, ref_date, from_date, to_date):
        """Construct a forecasting timeseries with provided parameters. The reconstruction interval is built with the outer
        bounds of all the timeseries.

        :param ref_date: datetime. The reference date to use
        :param from_date: from_date. Begining of the reconstruction interval
        :param to_date: to_date. End of the reconstruction interval
        :return: TimeSeries
        """
        res_timeserie = TimeSeries("unknown", CONSTANT, "", [], [])
        # FIXME : Quick fix
        if self.forecasting_dates:
            index = self.forecasting_dates.index(ref_date)
            indexes_to_check = self.forecasting_dates[: index + 1]
            for i in range(1, len(indexes_to_check) + 1):
                date = indexes_to_check[-i]
                res_timeserie = res_timeserie.merge(self.forecasts[date].slice(from_date, to_date))
                if from_date in res_timeserie.series.index and to_date in res_timeserie.series.index:
                    return res_timeserie
        return res_timeserie

    def get_forecast_old(self, ref_date, from_date, to_date):
        """Construct a forecasting timeseries with provided parameters. The reconstruction interval is built with the outer
        bounds of all the timeseries.

        :param ref_date: datetime. The reference date to use
        :param from_date: from_date. Begining of the reconstruction interval
        :param to_date: to_date. End of the reconstruction interval
        :return: TimeSeries
        """
        res_timeserie = TimeSeries("unknown", CONSTANT, "", [], [])
        # self.forecasting_dates is sorted, so we iterate dates by order
        for date in self.forecasting_dates:
            if ref_date > date:
                continue

            res_timeserie = res_timeserie.merge(self.forecasts[date].slice(from_date, to_date))
        return res_timeserie
