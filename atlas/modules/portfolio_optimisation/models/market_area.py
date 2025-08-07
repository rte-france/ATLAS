"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import model_validator

from atlas.enum import MarketType
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.models.market.market_area import MarketArea


class MarketAreaPO(MarketArea):
    price_forecast_medium: ForecastingMatrix | LazyForecastingMatrix

    @model_validator(mode="after")
    def validate_market_specific_prices(self, info):
        """Validate that required price fields are present based on market type and use_forecast.

        This validation requires external context (market type and use_forecast) to be provided
        during model instantiation via the model_validate method with context.
        """
        # Get market context from validation info context
        if info.context is None:
            # No validation if context not provided - allows flexible usage
            return self

        market_type = info.context.get("market_type")
        use_forecast = info.context.get("use_forecast", False)

        if market_type == MarketType.intraday:
            if use_forecast and self.id_price_forecast is None:
                raise ValueError("id_price_forecast is required when market=intraday and use_forecast=True")
            elif not use_forecast and self.id_price is None:
                raise ValueError("id_price is required when market=intraday and use_forecast=False")

        elif market_type == MarketType.rr_activation and self.rr_activation_price is None:
            raise ValueError("rr_activation_price is required when market=rr_activation")

        elif market_type == MarketType.mfrr_activation and self.mfrr_activation_price is None:
            raise ValueError("mfrr_activation_price is required when market=mfrr_activation")

        elif market_type == MarketType.dayahead and self.da_price is None:
            raise ValueError("da_price is required when market=day_ahead")
        return self

    def set_market_context(self, market_type: MarketType, use_forecast: bool = False):
        """Set market context for validation."""
        # Re-validate with market context
        return self.model_validate(
            self.model_dump(), context={"market_type": market_type, "use_forecast": use_forecast}
        )
