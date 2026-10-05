"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Unit test for ATLAS-296 B6: `MarketClearingResult.merge` into a
`LazyForecastingMatrix`. Neither test dataset triggers this path, so it is exercised directly.
"""

import pendulum

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.market_clearing.parameters import MarketClearingParameters
from atlas.modules.market_clearing.result import MarketClearingResult, Merge


class _FakeResult:
    def __init__(self, execution_date):
        self.input_dataset = type("_FakeInputDataset", (), {"parameters": type("_FakeParams", (), {})()})()
        self.input_dataset.parameters.temporal = type("_FakeTemporal", (), {"execution_date": execution_date})()

    def merge(self, history, window, how):
        return MarketClearingResult.merge(self, history, window, how)  # type: ignore[arg-type]


class TestMergeIntoForecast:
    def test_the_window_is_added_to_a_lazy_forecasting_matrix(self, parameters: MarketClearingParameters) -> None:
        existing_time = parameters.temporal.start_date
        new_time = parameters.temporal.start_date + pendulum.duration(hours=1)
        existing_ts = Timeseries.from_index(existing_time, pendulum.duration(hours=1), existing_time, 5.0)
        new_ts = Timeseries.from_index(new_time, pendulum.duration(hours=1), new_time, 7.0)

        forecast = ForecastingMatrix()
        forecast.add(existing_ts, existing_time)
        lazy_forecast = LazyForecastingMatrix(forecast)

        fake_result = _FakeResult(execution_date=new_time)
        result = fake_result.merge(lazy_forecast, new_ts, Merge.FORECAST)

        assert new_time in result
        assert existing_time in result


class TestCumulate:
    """`MarketClearingResult.merge` with `Merge.CUMULATE` — totals over the successive intraday sessions (issue #448)."""

    START = pendulum.datetime(2028, 1, 1)
    HOUR = pendulum.duration(hours=1)

    def cumulate(self, history, window):
        return _FakeResult(execution_date=self.START).merge(history, window, Merge.CUMULATE)

    def test_a_window_inside_the_history_is_summed(self) -> None:
        history = Timeseries.from_values(self.START, self.HOUR, [1.0, 2.0, 3.0])
        window = Timeseries.from_values(self.START + self.HOUR, self.HOUR, [10.0, 20.0])

        assert self.cumulate(history, window).values == [1.0, 12.0, 23.0]

    def test_a_window_after_the_history_extends_it_with_its_values(self) -> None:
        history = Timeseries.from_values(self.START, self.HOUR, [1.0, 2.0])
        window = Timeseries.from_values(self.START + 2 * self.HOUR, self.HOUR, [10.0, 20.0])

        assert self.cumulate(history, window).values == [1.0, 2.0, 10.0, 20.0]

    def test_a_window_overlapping_the_end_of_the_history_is_summed_then_extends_it(self) -> None:
        history = Timeseries.from_values(self.START, self.HOUR, [1.0, 2.0])
        window = Timeseries.from_values(self.START + self.HOUR, self.HOUR, [10.0, 20.0])

        assert self.cumulate(history, window).values == [1.0, 12.0, 20.0]

    def test_the_history_is_left_unchanged(self) -> None:
        history = Timeseries.from_values(self.START, self.HOUR, [1.0, 2.0])
        window = Timeseries.from_values(self.START, self.HOUR, [10.0, 20.0])

        self.cumulate(history, window)

        assert history.values == [1.0, 2.0]

    def test_a_missing_history_is_replaced_by_the_window(self) -> None:
        window = Timeseries.from_values(self.START, self.HOUR, [10.0, 20.0])

        assert self.cumulate(None, window) is window
