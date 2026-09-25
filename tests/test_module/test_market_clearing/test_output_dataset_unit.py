"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Unit test for ATLAS-296 B6: `MarketClearingOutputDataset.add_timeseries_to_forecast` checked
`isinstance(forecast_obj, LazyTimeseries)` on a parameter typed `ForecastingMatrix |
LazyForecastingMatrix | None` — a real `LazyForecastingMatrix` never matched that check and was
never `collect()`-ed. Neither test dataset triggers this path (the LP-comparison/output-snapshot
fixtures are byte-for-byte unchanged by every fix in this PR), so this is exercised directly.
"""

import pendulum

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.market_clearing.output_dataset import MarketClearingOutputDataset
from atlas.modules.market_clearing.parameters import MarketClearingParameters


class _FakeOutputDataset:
    def __init__(self, execution_date):
        self.input_dataset = type("_FakeInputDataset", (), {"parameters": type("_FakeParams", (), {})()})()
        self.input_dataset.parameters.temporal = type("_FakeTemporal", (), {"execution_date": execution_date})()

    def add_timeseries_to_forecast(self, forecast_obj, other):
        return MarketClearingOutputDataset.add_timeseries_to_forecast(self, forecast_obj, other)  # type: ignore[arg-type]


class TestAddTimeseriesToForecast:
    def test_a_lazy_forecasting_matrix_is_collected_before_use(self, parameters: MarketClearingParameters) -> None:
        existing_time = parameters.temporal.start_date
        new_time = parameters.temporal.start_date + pendulum.duration(hours=1)
        existing_ts = Timeseries.from_index(existing_time, pendulum.duration(hours=1), existing_time, 5.0)
        new_ts = Timeseries.from_index(new_time, pendulum.duration(hours=1), new_time, 7.0)

        forecast = ForecastingMatrix()
        forecast.add(existing_ts, existing_time)
        lazy_forecast = LazyForecastingMatrix(forecast)

        fake_output_dataset = _FakeOutputDataset(execution_date=new_time)
        result = fake_output_dataset.add_timeseries_to_forecast(lazy_forecast, new_ts)

        assert isinstance(result, ForecastingMatrix)
        assert new_time in result
