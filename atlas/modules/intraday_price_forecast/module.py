from typing import cast

import polars as pl
from loguru import logger
from pendulum import DateTime

import atlas.config as cfg
from atlas.abstract_class.module import AbstractModule
from atlas.enums import LoadType
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.modules.intraday_price_forecast.input_dataset import IntradayPriceForecastInputDataset
from atlas.modules.intraday_price_forecast.models.load import LoadIDPF
from atlas.modules.intraday_price_forecast.models.market_area import MarketAreaIDPF
from atlas.modules.intraday_price_forecast.models.solar import SolarIDPF
from atlas.modules.intraday_price_forecast.models.wind import WindIDPF
from atlas.modules.intraday_price_forecast.output_dataset import IntradayPriceForecastOutputDataset
from atlas.modules.intraday_price_forecast.parameters import IntradayPriceForecastParameters
from atlas.timing import generate_datetimes


class IntradayPriceForecastModule(
    AbstractModule[
        IntradayPriceForecastParameters, IntradayPriceForecastInputDataset, IntradayPriceForecastOutputDataset
    ]
):
    def get_parameters_class(self):
        return IntradayPriceForecastParameters

    def import_data(
        self, input_data: AtlasDataset, parameters: IntradayPriceForecastParameters
    ) -> IntradayPriceForecastInputDataset:
        return IntradayPriceForecastInputDataset(input_data, parameters)

    def validate_data(
        self, parameters: IntradayPriceForecastParameters, input_dataset: IntradayPriceForecastInputDataset
    ) -> bool:
        return True

    def execute(
        self, parameters: IntradayPriceForecastParameters, input_dataset: IntradayPriceForecastInputDataset
    ) -> IntradayPriceForecastOutputDataset:
        """
        Execute the intraday price forecast computation for all market areas.

        The algorithm follows these steps for each market area:
        1. Calculate price sensitivity ratio from high/low scenarios
        2. Compute consumption differences between day-ahead and intraday forecasts
        3. Apply the ratio to consumption differences to estimate price impact
        4. Add the impact to the baseline price (latest intraday or day-ahead)
        5. Apply price caps and store results

        :return: Output dataset with updated price forecasts
        :rtype: IntradayPriceForecastOutputDataset
        """
        output_dataset = IntradayPriceForecastOutputDataset(parameters, input_dataset)

        time_window = generate_datetimes(
            parameters.temporal.start_date, parameters.penultimate_date, parameters.temporal.timestep
        )

        for market_area in output_dataset.market_area:
            cfg.logger.info(f"Computing intraday price forecast for market area: '{market_area.name}'")

            loads, solars, winds = self._filter_assets_by_market_area(market_area, input_dataset)

            price_sensitivity_ratio = self._compute_price_sensitivity_ratio(market_area, loads, time_window, parameters)
            consumption_delta = self._compute_consumption_delta(loads, solars, winds, parameters)
            baseline_price, price_source_label = self._get_baseline_price(market_area, parameters)

            intraday_price_forecast = baseline_price + price_sensitivity_ratio * consumption_delta
            intraday_price_forecast = self._apply_non_negativity_constraint(intraday_price_forecast, parameters)
            intraday_price_forecast = self._apply_price_caps(
                intraday_price_forecast, market_area, time_window, parameters
            )

            self._save_price_forecast(market_area, intraday_price_forecast, parameters)

            cfg.logger.info(
                f"Intraday price for market area '{market_area.name}' has been done using {price_source_label}"
            )

        return output_dataset

    def validates_results(
        self,
        parameters: IntradayPriceForecastParameters,
        input_dataset: IntradayPriceForecastInputDataset,
        output_dataset: IntradayPriceForecastOutputDataset,
    ) -> bool:
        for market_area in output_dataset.market_area:
            if market_area.id_price_forecast is None:
                logger.error(
                    f"intraday price forecast missing for Market area {market_area.name} doesn't have negative price cap isn't negative: {parameters.intraday_negative_price_cap}"
                )
                return False
            if parameters.temporal.execution_date not in market_area.id_price_forecast:
                logger.error(
                    f"Missing timestep {parameters.temporal.execution_date} in price forecast for Market area {market_area.name}"
                )
                return False
        return True

    def export_results(
        self,
        parameters: IntradayPriceForecastParameters,
        input_dataset: IntradayPriceForecastInputDataset,
        output_dataset: IntradayPriceForecastOutputDataset,
    ) -> None:
        return

    def _filter_assets_by_market_area(
        self, market_area: MarketAreaIDPF, input_dataset: IntradayPriceForecastInputDataset
    ) -> tuple[list, list, list]:
        """
        Filter loads, solar, and wind assets by market area.

        :param market_area: The market area to filter assets for
        :type market_area: MarketAreaIDPF
        :return: Tuple containing lists of (loads, solars, winds) for the specified market area
        :rtype: tuple[list, list, list]
        """
        loads = [
            load
            for load in input_dataset.load
            if load.portfolio.market_area.name == market_area.name and load.load_type == LoadType.BASE_LOAD
        ]
        solars = [solar for solar in input_dataset.solar if solar.portfolio.market_area.name == market_area.name]
        winds = [wind for wind in input_dataset.wind if wind.portfolio.market_area.name == market_area.name]
        return loads, solars, winds

    def _create_empty_timeseries(self, parameters: IntradayPriceForecastParameters) -> Timeseries:
        return Timeseries.from_index(
            start_date=parameters.temporal.start_date,
            frequency=parameters.temporal.timestep,
            end_date=parameters.penultimate_date,
            default_value=0,
        )

    def _compute_price_sensitivity_ratio(
        self,
        market_area: MarketAreaIDPF,
        loads: list[LoadIDPF],
        time_window,
        parameters: IntradayPriceForecastParameters,
    ) -> Timeseries:
        """
        Compute the price sensitivity ratio from high/low price and consumption scenarios.

        The ratio represents how much the price changes per unit of consumption change,
        calculated as: (price_high - price_low) / (consumption_low - consumption_high)

        :param market_area: Market area containing price forecast scenarios
        :type market_area: MarketAreaIDPF
        :param loads: List of load assets with power forecast scenarios
        :type loads: list
        :param time_window: Time window for computation
        :return: Price sensitivity ratio over time
        :rtype: Timeseries
        """
        price_forecast_high = market_area.price_forecast_high.get_forecast(
            execution_date=parameters.execution_date_scenarios,
            start_date=parameters.temporal.start_date,
            end_date=parameters.penultimate_date,
        )
        price_forecast_low = market_area.price_forecast_low.get_forecast(
            execution_date=parameters.execution_date_scenarios,
            start_date=parameters.temporal.start_date,
            end_date=parameters.penultimate_date,
        )
        price_difference = price_forecast_high - price_forecast_low

        consumption_difference = loads[0].power_forecast_low - loads[0].power_forecast_high
        for load in loads[1:]:
            if load.power_forecast_high and load.power_forecast_low:
                consumption_difference += load.power_forecast_low - load.power_forecast_high
            else:
                cfg.logger.error(f"Error, missing 'power_forecast' high or low for unit {load.name}")

        price_sensitivity_ratio = self._create_empty_timeseries(parameters)
        for time in time_window:
            consumption_diff_value = consumption_difference.get_value(time) if time in consumption_difference else 0.0

            if time in price_difference and consumption_diff_value != 0:
                ratio_value = price_difference.get_value(time) / consumption_diff_value
            else:
                ratio_value = 0.0

            price_sensitivity_ratio.set_value(time, ratio_value)

        return price_sensitivity_ratio

    def _compute_consumption_delta(
        self,
        loads: list[LoadIDPF],
        solars: list[SolarIDPF],
        winds: list[WindIDPF],
        parameters: IntradayPriceForecastParameters,
    ) -> Timeseries:
        """
        Compute the difference between intraday and day-ahead residual consumption forecasts.

        Residual consumption = load consumption - solar production - wind production

        :param loads: List of load assets
        :type loads: list[LoadIDPF]
        :param solars: List of solar assets
        :type solars: list[SolarIDPF]
        :param winds: List of wind assets
        :type winds: list[WindIDPF]
        :param parameters: Module Parameters
        :type parameters: IntradayPriceForecastParameters
        :return: Consumption delta between intraday and day-ahead forecasts
        :rtype: Timeseries
        """
        residual_consumption_day_ahead = self._create_empty_timeseries(parameters)
        for asset in loads + solars + winds:
            residual_consumption_day_ahead -= asset.maximum_power_forecast.get_forecast(
                execution_date=parameters.execution_date_day_ahead,
                start_date=parameters.temporal.start_date,
                end_date=parameters.penultimate_date,
                timestep=parameters.temporal.timestep,
            )

        residual_consumption_intraday = self._create_empty_timeseries(parameters)
        for asset in loads + solars + winds:
            residual_consumption_intraday -= asset.maximum_power_forecast.get_forecast(
                execution_date=parameters.temporal.execution_date,
                start_date=parameters.temporal.start_date,
                end_date=parameters.penultimate_date,
                timestep=parameters.temporal.timestep,
            )

        intraday_ts = residual_consumption_intraday.slice(
            parameters.temporal.start_date, parameters.penultimate_date, inplace=False
        )
        day_ahead_ts = residual_consumption_day_ahead.slice(
            parameters.temporal.start_date, parameters.penultimate_date, inplace=False
        )
        consumption_delta = intraday_ts - day_ahead_ts

        return consumption_delta

    def _get_baseline_price(
        self, market_area: MarketAreaIDPF, parameters: IntradayPriceForecastParameters
    ) -> tuple[Timeseries, str]:
        """
        Determine the baseline price to use for the forecast.

        Priority: latest intraday price > day-ahead price

        :param market_area: Market area containing price data
        :type market_area: MarketAreaIDPF
        :param parameters: Module Parameters
        :type parameters: IntradayPriceForecastParameters
        :return: Tuple of (baseline_price, description_label)
        :rtype: tuple[Timeseries, str]
        """
        intraday_prices = market_area.id_price

        if intraday_prices:
            if isinstance(intraday_prices, LazyForecastingMatrix):
                intraday_prices = intraday_prices.collect()
            latest_intraday_price = intraday_prices.select(intraday_prices.index[-1])
            if (
                parameters.temporal.start_date in latest_intraday_price
                and parameters.penultimate_date in latest_intraday_price
            ):
                return latest_intraday_price, "Intraday price"

        da_price = market_area.da_price
        return (
            da_price.collect() if isinstance(da_price, LazyTimeseries) else cast(Timeseries, da_price)
        ), "Day Ahead price"

    def _apply_non_negativity_constraint(
        self, price_forecast: Timeseries, parameters: IntradayPriceForecastParameters
    ) -> Timeseries:
        """
        Ensure all price values are non-negative.

        :param price_forecast: The price forecast timeseries
        :type price_forecast: Timeseries
        :param parameters: Module Parameters
        :type parameters: IntradayPriceForecastParameters
        :return: Price forecast with non-negative values
        :rtype: Timeseries
        """
        df = price_forecast.slice(
            parameters.temporal.start_date, parameters.penultimate_date, inplace=False
        ).dataframe.with_columns(pl.when(pl.col("value") < 0.0).then(0.0).otherwise(pl.col("value")).alias("value"))

        if isinstance(price_forecast, pl.LazyFrame):
            df = df.collect()
        price_forecast = Timeseries(cast(pl.DataFrame, df))

        return price_forecast

    def _apply_price_caps(
        self,
        price_forecast: Timeseries,
        market_area: MarketAreaIDPF,
        time_window: list[DateTime],
        parameters: IntradayPriceForecastParameters,
    ) -> Timeseries:
        """
        Apply upper and lower price caps to the forecast.

        If the forecast exceeds the caps, all values are scaled proportionally
        to bring the extreme value to the cap limit.

        :param price_forecast: The price forecast timeseries
        :type price_forecast: Timeseries
        :param market_area: Market area for logging purposes
        :param time_window: Time window for applying caps
        :type time_window: list[DateTime]
        :param parameters: Module Parameters
        :type parameters: IntradayPriceForecastParameters
        :return: Capped price forecast
        :rtype: Timeseries
        """
        price_slice = price_forecast.slice(parameters.temporal.start_date, parameters.temporal.end_date)

        price_forecast = self._apply_single_price_cap(
            price_forecast=price_forecast,
            extreme_value=price_slice.max(),
            cap_value=parameters.intraday_positive_price_cap,
            cap_type="upper",
            market_area_name=market_area.name,
            time_window=time_window,
            is_upper=True,
        )

        price_slice = price_forecast.slice(parameters.temporal.start_date, parameters.temporal.end_date)

        price_forecast = self._apply_single_price_cap(
            price_forecast=price_forecast,
            extreme_value=price_slice.min(),
            cap_value=parameters.intraday_negative_price_cap,
            cap_type="lower",
            market_area_name=market_area.name,
            time_window=time_window,
            is_upper=False,
        )

        return price_forecast

    def _apply_single_price_cap(
        self,
        price_forecast: Timeseries,
        extreme_value: float,
        cap_value: float,
        cap_type: str,
        market_area_name: str,
        time_window: list[DateTime],
        is_upper: bool,
    ) -> Timeseries:
        """
        Apply a single price cap (upper or lower) to the forecast.

        :param price_forecast: The price forecast timeseries
        :type price_forecast: Timeseries
        :param extreme_value: The current extreme value (max for upper, min for lower)
        :type extreme_value: float
        :param cap_value: The cap limit
        :type cap_value: float
        :param cap_type: Type of cap for logging ("upper" or "lower")
        :type cap_type: str
        :param market_area_name: Market area name for logging
        :type market_area_name: str
        :param time_window: Time window for applying the cap
        :type time_window: list[DateTime]
        :param is_upper: True for upper cap, False for lower cap
        :type is_upper: bool
        :return: Capped price forecast
        :rtype: Timeseries
        """
        condition_met = extreme_value > cap_value if is_upper else extreme_value < cap_value

        if condition_met:
            corrective_ratio = float(cap_value / extreme_value)
            cfg.logger.info(f"Intraday price forecasts {cap_type} capped in area {market_area_name}")

            for time in time_window:
                price_forecast.set_value(time, price_forecast.get_value(time) * corrective_ratio)

        return price_forecast

    def _save_price_forecast(
        self,
        market_area: MarketAreaIDPF,
        price_forecast: Timeseries,
        parameters: IntradayPriceForecastParameters,
    ) -> None:
        """
        Save the computed price forecast to the market area's forecasting matrix.

        :param market_area: Market area to update
        :type market_area: MarketAreaIDPF
        :param price_forecast: Computed intraday price forecast
        :type price_forecast: Timeseries
        """
        if market_area.id_price_forecast is None:
            market_area.id_price_forecast = ForecastingMatrix(
                price_forecast.dataframe.rename({"value": parameters.temporal.execution_date.to_datetime_string()})
            )
        else:
            market_area.id_price_forecast.add(price_forecast, parameters.temporal.execution_date)
