"""
Copyright (c) 2016-2022, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements ForecastingMatrix
"""

from datetime import datetime

from atlas.math.matrix import Matrix
from atlas.math.timeseries import Timeseries


class ForecastingMatrix(Matrix[datetime]):
    """
    Stores Timeseries objects indexed by datetime, with access and forecasting utilities.

    Inherits from `Matrix[datetime]` and provides additional methods for forecasting
    reconstruction from past or future available timeseries.
    """

    def __init__(
        self,
        name: str,
        forecasting_dates: list[datetime],
        timeseries: list[Timeseries],
    ):
        """
        Initialize a ForecastingMatrix.

        :param name: Name of the matrix.
        :type name: str
        :param forecasting_dates: List of forecasting dates used as indexes.
        :type forecasting_dates: list[datetime]
        :param timeseries: List of corresponding Timeseries objects.
        :type timeseries: list[Timeseries]
        """
        super().__init__(name, forecasting_dates, timeseries)
        self._sort_indexes()

    def _sort_indexes(self) -> None:
        """Sort the internal mapping of timeseries by datetime keys."""
        sorted_items = sorted(self.timeseries_map.items())
        self.timeseries_map = dict(sorted_items)

    def add_timeseries(self, index: datetime, timeseries: Timeseries) -> None:
        """
        Add a Timeseries to the matrix and keep indexes sorted.

        :param index: Forecasting datetime key.
        :type index: datetime
        :param timeseries: Timeseries object to insert.
        :type timeseries: Timeseries
        """
        super().add_timeseries(index, timeseries)
        self._sort_indexes()

    def extract(self, index: datetime, start_date: datetime, end_date: datetime) -> Timeseries:
        """
        Extract a portion of a Timeseries at a specific forecast date.

        :param index: Forecasting datetime from which to extract.
        :type index: datetime
        :param start_date: Start of the extraction window.
        :type start_date: datetime
        :param end_date: End of the extraction window.
        :type end_date: datetime
        :return: A sliced Timeseries from the specified index.
        :rtype: Timeseries
        """
        ts = self.get_timeseries(index)
        return ts.filter([start_date, end_date])

    # def get_forecast(
    #     self,
    #     ref_date: datetime,
    #     from_date: datetime,
    #     to_date: datetime,
    # ) -> Timeseries:
    #     """
    #     Construct a forecast by merging historical data up to a reference date.

    #     Builds a Timeseries by merging slices from all available forecasts
    #     that occurred **before or on** `ref_date`, in reverse order. Stops when the
    #     full range `[from_date, to_date]` is covered.

    #     :param ref_date: Reference datetime to stop looking backward.
    #     :type ref_date: datetime
    #     :param from_date: Start of the desired forecast window.
    #     :type from_date: datetime
    #     :param to_date: End of the desired forecast window.
    #     :type to_date: datetime
    #     :return: A reconstructed forecast as a Timeseries.
    #     :rtype: Timeseries
    #     """
    #     result = Timeseries("unknown", TimeSeriesInterpolation.CONSTANT, "", [], [])

    #     indexes_to_check = [d for d in self.indexes if d <= ref_date]
    #     for date in reversed(indexes_to_check):
    #         result = result.merge(self.timeseries_map[date].slice(from_date, to_date))
    #         if from_date in result.series.index and to_date in result.series.index:
    #             return result
    #     return result

    # def get_forecast_old(
    #     self,
    #     ref_date: datetime,
    #     from_date: datetime,
    #     to_date: datetime,
    # ) -> Timeseries:
    #     """
    #     Legacy forecast method: merge future forecasts starting from ref_date.

    #     Gathers all forecast slices where the forecast date is **on or after**
    #     `ref_date`, merging them in chronological order.

    #     :param ref_date: Date from which to begin merging forward.
    #     :type ref_date: datetime
    #     :param from_date: Start of the desired forecast window.
    #     :type from_date: datetime
    #     :param to_date: End of the desired forecast window.
    #     :type to_date: datetime
    #     :return: A forecasted Timeseries composed of future slices.
    #     :rtype: Timeseries
    #     """
    #     result = Timeseries("unknown", TimeSeriesInterpolation.CONSTANT, "", [], [])
    #     for date in self.indexes:
    #         if date >= ref_date:
    #             result = result.merge(self.timeseries_map[date].slice(from_date, to_date))
    #     return result
