import pendulum

import atlas.config as cfg
from atlas.modules.price_forcast.price_forcast_timeseries import PriceForcastTimeseries
from atlas.modules.price_forcast.price_forcast_input_dataset import PriceForcastInputDataset
from atlas.modules.price_forcast.price_forcast_output_dataset import PriceForcastOutputDataset
from atlas.modules.price_forcast.price_forcast_parameters import PriceForcastParameters
from atlas.timing import generate_datetimes
from atlas.math.timeseries import Timeseries


class PriceForcastOrchestrator:

    def __init__(self, parameters: PriceForcastParameters, input_dataset: PriceForcastInputDataset):
        """
        :param parameters: the parameters
        :type parameters: PriceForcastParameters
        :param input_dataset: the input dataset
        :type input_dataset: PriceForcastInputDataset
        """
        self.parameters = parameters
        self.input_dataset = input_dataset
        self.output_dataset = PriceForcastOutputDataset(parameters, input_dataset)

    def execute(self) -> PriceForcastOutputDataset:
        """
        FIXME ADD DESCRIPTION
        :return: the output dataset
        :rtype: PriceForcastOutputDataset
        """
        # ------ Markers and Parameters

        # FIXME - do we keep the name 'Output_PrevisionPrix_IJ'?
        # API.IO.SetOutputMarkerByIdentifier('Output_PrevisionPrix_IJ', input_marker)

        if self.parameters.verbose:
            cfg.logger.info(str(self.parameters))

        index = self.define_orders_time()
        next_to_end_date = self.parameters.end_date.add(-self.parameters.time_step)

        for market_area in self.input_dataset.market_area:

            if self.parameters.verbose:
                cfg.logger.info(f"Computing forecast for: {market_area.name}")

            load_list = [load for load in self.output_dataset.load if load.portfolio.market_area.name == market_area.name and load.load_type == "BaseLoad"]
            solar_list = [solar for solar in self.output_dataset.solar if solar.portfolio.market_area.name == market_area.name]
            wind_list = [wind for wind in self.output_dataset.solar if wind.portfolio.market_area.name == market_area.name]

            # ------ ID Price Forecast calculation ------
            # Create a time series that store the differences in price in two scenarios
            price_high = market_area.price_forecast_high.get_forecast(
                execution_date=self.parameters.execution_date_scenarios,
                start_date=self.parameters.start_date,
                end_date=next_to_end_date
            )
            price_low = market_area.price_forecast_low.get_forecast(
                execution_date=self.parameters.execution_date_scenarios,
                start_date=self.parameters.start_date,
                end_date=next_to_end_date
            )
            price_diff = price_high - price_low

            # Create a time series that store the differences in consumption in two scenarios
            # The load scenarios are in the Atlas model
            conso_diff = self.generate_empty_timeseries()
            for load in load_list:
                if load.power_forecast_high and load.power_forecast_low:
                    conso_diff += load.power_forecast_low - load.power_forecast_high
                else:
                    cfg.logger.error(f"Error, missing PowerForecast high or low for unit {load.Name}")

            # Create a time series that store the ratio between the series above
            ratio = self.generate_empty_timeseries()
            # Set the values for ratio time series within the range of the input parameters
            for time in index:
                try:
                    result_ti = price_diff.get_value(time) / conso_diff.get_value(time)
                except ZeroDivisionError:
                    result_ti = 0
                ratio.set_value(time, result_ti)

            # Calculation of residual consumption:
            conso_day_ahead = PriceForcastTimeseries(self.generate_empty_timeseries())
            conso_id = PriceForcastTimeseries(self.generate_empty_timeseries())
            for load in load_list:
                conso_day_ahead -= load.maximum_power_forecast.get_forecast(
                    execution_date=self.parameters.execution_date_day_ahead,
                    start_date=self.parameters.start_date,
                    end_date=next_to_end_date
                )
                conso_id -= load.maximum_power_forecast.get_forecast(
                    execution_date=self.parameters.execution_date,
                    start_date=self.parameters.start_date,
                    end_date=next_to_end_date
                )

            for photovoltaic in solar_list:
                conso_day_ahead -= photovoltaic.maximum_power_forecast.get_forecast(
                    execution_date=self.parameters.execution_date_day_ahead,
                    start_date=self.parameters.start_date,
                    end_date=next_to_end_date
                )
                conso_id -= photovoltaic.maximum_power_forecast.get_forecast(
                    execution_date=self.parameters.execution_date,
                    start_date=self.parameters.start_date,
                    end_date=next_to_end_date
                )

            for wind in wind_list:
                conso_day_ahead -= wind.maximum_power_forecast.get_forecast(
                    execution_date=self.parameters.execution_date_day_ahead,
                    start_date=self.parameters.start_date,
                    end_date=next_to_end_date
                )
                conso_id -= wind.maximum_power_forecast.get_forecast(
                    execution_date=self.parameters.execution_date,
                    start_date=self.parameters.start_date,
                    end_date=next_to_end_date
                )

            # The difference in consumption is stored in the following time series:
            # FIXME how do we transfer this unit value?? 'MW'
            delta_conso = self.generate_empty_timeseries()

            for time in index:
                err = conso_id.get_value_zero_if_empty(time) - conso_day_ahead.get_value_zero_if_empty(time)
                delta_conso.set_value(time, err)

            # We can make a price forecast by summing this deltaPrice with the last established price in the MarketClearing:
            id_prices = market_area.id_price
            if len(id_prices) == 0:
                last_price = market_area.da_price
                last_price_str = "DA price"
            else:
                last_id_price = id_prices[len(id_prices) - 1]
                if self.parameters.start_date not in last_id_price \
                        or next_to_end_date not in last_id_price:
                    last_price = market_area.da_price
                    last_price_str = "DA price"
                else:
                    last_price = last_id_price
                    last_price_str = "ID price"

            prev_ij = last_price + ratio * delta_conso

            for time in index:
                if prev_ij.get_value(time) < 0.:
                    prev_ij.set_value(time, 0.)

            # Cap the price forecast to the price caps of the intraday market
            # A margin is taken around the price caps, to ensure that the ratio
            # between buy and sell offers is still meaningful

            # Upper cap first
            if prev_ij.slice(self.parameters.start_date, self.parameters.end_date).max() \
                    > self.parameters.intraday_positive_price_cap:
                corrective_ratio = float(self.parameters.intraday_positive_price_cap
                                         / prev_ij.slice(self.parameters.start_date, self.parameters.end_date).max())

                if self.parameters.verbose:
                    cfg.logger.info(f"ID price forecasts upper capped in area {market_area.Name}")

                for t in index:
                    prev_ij.set_value(t, prev_ij.get_value(t) * corrective_ratio)

            # Lower cap
            if prev_ij.slice(self.parameters.start_date, self.parameters.end_date).min() \
                    < self.parameters.intraday_negative_price_cap:
                corrective_ratio = float(self.parameters.intraday_negative_price_cap
                                         / prev_ij.slice(self.parameters.start_date, self.parameters.end_date).min())

                if self.parameters.verbose:
                    cfg.logger.info(f"ID price forecasts lower capped in area {market_area.name}")

                for time in index:
                    prev_ij.set_value(time, prev_ij.get_value(time) * corrective_ratio)

            # Saving the result in the Price Forecast Matrix:
            market_area.id_price_forecast.add(prev_ij, self.parameters.execution_date)
            cfg.logger.info(f"The update of {market_area.Name} price has been done using {last_price_str}")
            return self.output_dataset

    # TODO - This function is also used by module Day-Ahead-Order and maybe used by other module
    #   Can we consider making this function on a more global scale
    def define_orders_time(self) -> list[pendulum.DateTime]:
        """
        This function creates a sequence of timestamps between a start_date and an end_date
        with frequency matching the time_step parameter.
        In particular, it makes sure that no time step crosses the end_date boundary.

        :return: a list of DateTime objects
        :rtype: list[DateTime]
        """
        orders_time = []
        if self.parameters.start_date < self.parameters.end_date:
            orders_time = generate_datetimes(
                self.parameters.start_date, self.parameters.penultimate_date, self.parameters.time_step
            )
        else:
            msg = "The end_date parameter must be posterior to the start_date parameter."
            cfg.logger.error(msg)
        return orders_time

    def generate_empty_timeseries(self) -> Timeseries:
        return Timeseries.from_index(
            start_date=self.parameters.start_date,
            frequency=self.parameters.time_step,
            end_date=self.parameters.end_date,
            default_value=0
        )