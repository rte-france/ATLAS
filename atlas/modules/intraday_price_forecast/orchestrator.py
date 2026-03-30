import atlas.config as cfg
from atlas.enums import LoadType
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.intraday_price_forecast.input_dataset import IntradayPriceForecastInputDataset
from atlas.modules.intraday_price_forecast.output_dataset import IntradayPriceForecastOutputDataset
from atlas.modules.intraday_price_forecast.parameters import IntradayPriceForecastParameters
from atlas.timing import generate_datetimes


class IntradayPriceForecastOrchestrator:
    def __init__(self, parameters: IntradayPriceForecastParameters, input_dataset: IntradayPriceForecastInputDataset):
        """
        :param parameters: the parameters
        :type parameters: IntradayPriceForecastParameters
        :param input_dataset: the input dataset
        :type input_dataset: IntradayPriceForecastInputDataset
        """
        self.parameters = parameters
        self.input_dataset = input_dataset
        self.output_dataset = IntradayPriceForecastOutputDataset(parameters, input_dataset)

    def execute(self) -> IntradayPriceForecastOutputDataset:
        """
        FIXME ADD DESCRIPTION
        :return: the output dataset
        :rtype: IntradayPriceForecastOutputDataset
        """

        time_window = generate_datetimes(
            self.parameters.temporal.start_date, self.parameters.penultimate_date, self.parameters.temporal.timestep
        )

        for market_area in self.output_dataset.market_area:
            cfg.logger.info(f"Computing intraday price forecast for market area: {market_area.name}")

            loads = [
                load
                for load in self.input_dataset.load
                if load.portfolio.market_area.name == market_area.name and load.load_type == LoadType.BASE_LOAD
            ]
            solars = [
                solar for solar in self.input_dataset.solar if solar.portfolio.market_area.name == market_area.name
            ]
            winds = [wind for wind in self.input_dataset.wind if wind.portfolio.market_area.name == market_area.name]

            # ------ ID Price Forecast calculation ------
            # Create a time series that store the differences in price in two scenarios
            price_high = market_area.price_forecast_high.get_forecast(
                execution_date=self.parameters.execution_date_scenarios,
                start_date=self.parameters.temporal.start_date,
                end_date=self.parameters.penultimate_date,
            )
            price_low = market_area.price_forecast_low.get_forecast(
                execution_date=self.parameters.execution_date_scenarios,
                start_date=self.parameters.temporal.start_date,
                end_date=self.parameters.penultimate_date,
            )
            price_diff = price_high - price_low

            # Create a time series that store the differences in consumption in two scenarios
            # The load scenarios are in the Atlas model
            conso_diff = loads[0].power_forecast_low - loads[0].power_forecast_high
            for load in loads[1:]:
                if load.power_forecast_high and load.power_forecast_low:
                    conso_diff += load.power_forecast_low - load.power_forecast_high
                else:
                    cfg.logger.error(f"Error, missing PowerForecast high or low for unit {load.name}")

            # Create a time series that store the ratio between the series above
            ratio = Timeseries.from_index(
                start_date=self.parameters.temporal.start_date,
                frequency=self.parameters.temporal.timestep,
                end_date=self.parameters.penultimate_date,
                default_value=0,
            )
            # Set the values for ratio time series within the range of the input parameters
            for time in time_window:
                result_ti = (
                    price_diff.get_value(time) / conso_diff.get_value(time)
                    if time in price_diff and time in conso_diff and conso_diff.get_value(time) != 0
                    else 0.0
                )

                ratio.set_value(time, result_ti)

            # Calculation of residual consumption:
            conso_day_ahead = Timeseries.from_index(
                start_date=self.parameters.temporal.start_date,
                frequency=self.parameters.temporal.timestep,
                end_date=self.parameters.penultimate_date,
                default_value=0,
            )
            conso_id = Timeseries.from_index(
                start_date=self.parameters.temporal.start_date,
                frequency=self.parameters.temporal.timestep,
                end_date=self.parameters.penultimate_date,
                default_value=0,
            )
            # Combine all assets (loads, solars, winds) and subtract their forecasts
            for asset in loads + solars + winds:
                conso_day_ahead -= asset.maximum_power_forecast.get_forecast(
                    execution_date=self.parameters.execution_date_day_ahead,
                    start_date=self.parameters.temporal.start_date,
                    end_date=self.parameters.penultimate_date,
                )
                conso_id -= asset.maximum_power_forecast.get_forecast(
                    execution_date=self.parameters.temporal.execution_date,
                    start_date=self.parameters.temporal.start_date,
                    end_date=self.parameters.penultimate_date,
                )

            # The difference in consumption is stored in the following time series:
            delta_conso = Timeseries.from_index(
                start_date=self.parameters.temporal.start_date,
                frequency=self.parameters.temporal.timestep,
                end_date=self.parameters.penultimate_date,
                default_value=0,
            )

            for time in time_window:
                err = (conso_id.get_value(time) if time in conso_id else 0.0) - (
                    conso_day_ahead.get_value(time) if time in conso_day_ahead else 0.0
                )
                delta_conso.set_value(time, err)

            # We can make a price forecast by summing this deltaPrice with the last established price in the MarketClearing:
            id_prices = market_area.id_price
            if id_prices is None or len(id_prices) == 0:
                last_price = market_area.da_price
                last_price_str = "DA price"
            else:
                last_id_price = id_prices[id_prices.index[len(id_prices) - 1]]
                if (
                    self.parameters.temporal.start_date not in last_id_price
                    or self.parameters.penultimate_date not in last_id_price
                ):
                    last_price = market_area.da_price
                    last_price_str = "Day Ahead price"
                else:
                    last_price = last_id_price
                    last_price_str = "Intraday price"

            prev_ij = last_price + ratio * delta_conso

            for time in time_window:
                if prev_ij.get_value(time) < 0.0:
                    prev_ij.set_value(time, 0.0)

            # Cap the price forecast to the price caps of the intraday market
            # A margin is taken around the price caps, to ensure that the ratio
            # between buy and sell offers is still meaningful

            # Upper cap first
            if (
                prev_ij.slice(self.parameters.temporal.start_date, self.parameters.temporal.end_date).max()
                > self.parameters.intraday_positive_price_cap
            ):
                corrective_ratio = float(
                    self.parameters.intraday_positive_price_cap
                    / prev_ij.slice(self.parameters.temporal.start_date, self.parameters.temporal.end_date).max()
                )

                cfg.logger.info(f"ID price forecasts upper capped in area {market_area.name}")

                for t in time_window:
                    prev_ij.set_value(t, prev_ij.get_value(t) * corrective_ratio)

            # Lower cap
            if (
                prev_ij.slice(self.parameters.temporal.start_date, self.parameters.temporal.end_date).min()
                < self.parameters.intraday_negative_price_cap
            ):
                corrective_ratio = float(
                    self.parameters.intraday_negative_price_cap
                    / prev_ij.slice(self.parameters.temporal.start_date, self.parameters.temporal.end_date).min()
                )

                cfg.logger.info(f"ID price forecasts lower capped in area {market_area.name}")

                for time in time_window:
                    prev_ij.set_value(time, prev_ij.get_value(time) * corrective_ratio)

            # Saving the result in the Price Forecast Matrix:
            if market_area.id_price_forecast is None:
                market_area.id_price_forecast = ForecastingMatrix(
                    prev_ij.dataframe.rename(columns={"value": self.parameters.temporal.execution_date})
                )
            else:
                market_area.id_price_forecast.add(prev_ij, self.parameters.temporal.execution_date)
            cfg.logger.info(f"The update of {market_area.name} price has been done using {last_price_str}")
        return self.output_dataset
