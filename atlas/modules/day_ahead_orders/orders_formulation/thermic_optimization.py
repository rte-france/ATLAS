"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import atlas.config as cfg
from atlas.models.equipment.thermal import Thermal
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters


class ThermicOptimization:
    @staticmethod
    def solve_optimization_programs(equipments_list: Thermal, parameters: DayAheadOrdersParameters) -> dict:
        """
        Solves the optimization programs for a list of equipment given the three price curves.

        Arguments:
        equiment_list : a list of thermal equipments
        parameters : a signedTuple of parameters

        Returns:
        results : a two stage dictionary containing for each equipment the optimal quantities given a price curve.
        lp_files : a two stage dictionary containing for each equipment and each price curve the associated lp file
                    of the optimization program.
        """

        # create a dictionary that will store the program's outcomes.
        results = {}

        for unit, i in zip(equipments_list, range(len(equipments_list)), strict=False):
            # Initialize a key with the unit's name.
            results[unit.name] = {}

            # Retrieve the price forecasts types, extract the corresponding time series and store it in a list
            price_types = parameters.price_forecasts_types
            prices = []

            for price_type in price_types:
                if price_type == "Low":
                    prices_low = unit.portfolio.market_area.price_forecast_low.get_forecast(
                        parameters.execution_date, parameters.start_date, parameters.end_optimization_date
                    )
                    prices.append(prices_low)

                elif price_type == "Medium":
                    prices_medium = unit.portfolio.market_area.price_forecast_medium.get_forecast(
                        parameters.execution_date, parameters.start_date, parameters.end_optimization_date
                    )
                    prices.append(prices_medium)

                elif price_type == "High":
                    prices_high = unit.portfolio.market_area.price_forecast_high.get_forecast(
                        parameters.execution_date, parameters.start_date, parameters.end_optimization_date
                    )
                    prices.append(prices_high)

                else:
                    cfg.logger.error(
                        "WARNING: Wrong PriceForecastsType indicated as parameters. \n"
                        "Possible values are: 'Low', 'Medium', 'High'"
                    )

            # Initialize the output of the function

            # Solve three times the optimization program, one for each price curve
            # and store the optimal output quantities into the dictionaries
            for price, value in zip(prices, price_types, strict=False):
                res = solve_thermic_optimization_program(unit, price, value, parameters)  # TODO #####################
                results[unit.name][value] = res

                # TODO
                # # Store state sequences in the output marker
                # local_time_index = res["OFF"].index()
                # new_sequence_ts = API.TimeSeries.NewTimeSeries(
                #     f"State_sequence_of_{unit.Name}_{value}_price",
                #     API.TimeSeries.Constant,
                #     "Integer",
                #     local_time_index,
                #     0,
                # )
                #
                # for time in local_time_index:
                #     if res["ON_UP"].GetValue(time) == 1:
                #         new_sequence_ts.SetValue(time, 1)
                #         continue
                #
                #     if res["ON_DOWN"].GetValue(time) == 1:
                #         new_sequence_ts.SetValue(time, 2)
                #         continue
                #
                #     if res["OFF"].GetValue(time) == 1:
                #         new_sequence_ts.SetValue(time, 3)
                #         continue
                #
                #     if "START" in res.keys():
                #         if res["START"].GetValue(time) == 1:
                #             new_sequence_ts.SetValue(time, 4)
                #             continue
                #
                #     if "STOP" in res.keys():
                #         if res["STOP"].GetValue(time) == 1:
                #             new_sequence_ts.SetValue(time, 5)
                #             continue
                #
                #     if "ON_FLAT" in res.keys():
                #         if res["ON_FLAT"].GetValue(time) == 1:
                #             new_sequence_ts.SetValue(time, 6)
                #             continue
                #
                # unit.StateSequence.AddTimeSeries(
                #     f"{functions.get_date_to_clean_string(parameters.execution_date)}-{value.upper()}_DAO",
                #     new_sequence_ts,
                # )

        return results
