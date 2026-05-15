from __future__ import annotations

from pydantic.functional_validators import model_validator

from atlas.enums import LoadType
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.objects.equipment.load import Load


class LoadIDPF(Load):
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix

    @model_validator(mode="after")
    def base_load_power_forecast(self) -> LoadIDPF:
        if self.load_type == LoadType.BASE_LOAD:
            if self.power_forecast_high is None and self.power_forecast_low is None:
                raise ValueError("Base load power forecast high and low are required")
        return self
