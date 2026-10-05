"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Unit test for ATLAS-296 B6: `MarketClearingResult.add_timeseries_to_forecast` on a
`LazyForecastingMatrix`. Neither test dataset triggers this path, so it is exercised directly.
"""

import pendulum

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.market_clearing.parameters import MarketClearingParameters
from atlas.modules.market_clearing.result import MarketClearingResult


class _FakeResult:
    def __init__(self, execution_date):
        self.input_dataset = type("_FakeInputDataset", (), {"parameters": type("_FakeParams", (), {})()})()
        self.input_dataset.parameters.temporal = type("_FakeTemporal", (), {"execution_date": execution_date})()

    def add_timeseries_to_forecast(self, forecast_obj, other):
        return MarketClearingResult.add_timeseries_to_forecast(self, forecast_obj, other)  # type: ignore[arg-type]


class TestAddTimeseriesToForecast:
    def test_the_window_is_added_to_a_lazy_forecasting_matrix(self, parameters: MarketClearingParameters) -> None:
        existing_time = parameters.temporal.start_date
        new_time = parameters.temporal.start_date + pendulum.duration(hours=1)
        existing_ts = Timeseries.from_index(existing_time, pendulum.duration(hours=1), existing_time, 5.0)
        new_ts = Timeseries.from_index(new_time, pendulum.duration(hours=1), new_time, 7.0)

        forecast = ForecastingMatrix()
        forecast.add(existing_ts, existing_time)
        lazy_forecast = LazyForecastingMatrix(forecast)

        fake_result = _FakeResult(execution_date=new_time)
        result = fake_result.add_timeseries_to_forecast(lazy_forecast, new_ts)

        assert new_time in result
        assert existing_time in result
