"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import os
from datetime import timedelta
from typing import Any

import pendulum

import atlas.config as cfg
from atlas import Timeseries, Equipment, Order
from atlas.enum import StorageType, Product
from atlas.modules.day_ahead_orders.day_ahead_orders_input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.optim_models.battery_model import BatteryModel
from atlas.modules.day_ahead_orders.optim_models.dao_base_model import DAOBaseModel
from atlas.modules.day_ahead_orders.optim_models.electric_vehicle_model import ElectricVehicleModel
from atlas.modules.day_ahead_orders.tools.Utilities import Utilities
from atlas.timing import generate_datetimes


class DayAheadStorage:
    """------ Main optimization functions ------"""

    @staticmethod
    def optimize_ev(
        equipment: Equipment, initial_stock: float | None, parameters: DayAheadOrdersParameters
    ) -> tuple[dict[Any, Any], dict[Any, Any]]:
        """
        Optimization function for ElectricVehicle units
        :param equipment: equipment
        :param initial_stock: InitialStock
        :param parameters: parameters
        :return: output variables
        """
        # Creation of optimization problem
        model = ElectricVehicleModel(
            parameters.solver.upper(),
            "Optimization of the storage unit " + equipment.name,
            parameters,
            equipment,
            parameters.ev_additional_hours,
        )
        model.create_decision_variables(parameters.ev_nb_fragments)
        model.create_objective_function(parameters.ev_nb_fragments, parameters.ev_smoothing_factor)
        model.create_constraints(initial_stock)

        ##  PROBLEM SOLVING  ##
        if parameters.solver.upper() == "XPRESS":
            DayAheadStorage.solve_with_xpress(model, parameters, equipment.name)
        else:
            # If another solver is being used, consider setting the NoOverlap parameter to False as it previously raised errors otherwise with GLPK
            raise ValueError(
                "Please use XPRESS, as other solvers either are deprecated or provide non-optimal solutions"
            )

        # Assign the values to the output variables
        # Note that the time domain of the output variables is [StartDate, EndDate]
        Qvv = {}
        Qaa = {}
        for t in model.time_frame:
            if t >= parameters.end_date:
                break
            Qvv[t] = round(model.Qv[t].VarValue, 2)
            Qaa[t] = round(model.Qa[t].VarValue, 2)

        return Qvv, Qaa

    @staticmethod
    def optimize_battery(equipment: Equipment, initial_stock: float | None, parameters: DayAheadOrdersParameters):
        """
        Optimization function for Battery and PHS units
        :param equipment: equipment
        :param initial_stock: initial_stock
        :param parameters: parameters
        :return:
        """
        if equipment.storage_type == StorageType.BATTERY:
            optimization_period = parameters.battery_additional_hours
            smoothing_factor = parameters.battery_smoothing_factor
            power_fragments = parameters.battery_nb_fragments
        elif equipment.storage_type == StorageType.PUMPED_HYDRAULIC_STORAGE:
            optimization_period = parameters.phs_additional_hours
            smoothing_factor = parameters.phs_smoothing_factor
            power_fragments = parameters.phs_nb_fragments

        # ##  CREATION OF PROBLEM  ##
        # Creation of optimization problem
        # --------------------------------
        model = BatteryModel(
            parameters.solver.upper(),
            "Optimization of the storage unit " + equipment.name,
            parameters,
            equipment,
            optimization_period,
        )
        model.create_decision_variables(power_fragments)
        model.create_objective_function(power_fragments, smoothing_factor)
        model.create_constraints(initial_stock, power_fragments)

        # Solving the problem
        if parameters.solver.upper() == "XPRESS":
            DayAheadStorage.solve_with_xpress(model, parameters, equipment.name)
        else:
            # If another solver is being used, consider setting the NoOverlap parameter to False as it previsously raised errors otherwise with GLPK
            raise ValueError(
                "Please use XPRESS, as other solvers either are deprecated or provide non-optimal solutions"
            )

        # Assign the values to the output variables
        # Note that the time domain of the output variables is [StartDate, EndDate]
        Qvv = {}
        Qaa = {}
        for t in model.time_frame:
            if t >= parameters.end_date:
                break
            Qvv[t] = round(model.Qv[t].VarValue, 2)
            Qaa[t] = round(model.Qa[t].VarValue, 2)

        return Qvv, Qaa

    @staticmethod
    def solve_with_xpress(model: DAOBaseModel, parameters: DayAheadOrdersParameters, equipment_name: str) -> None:
        model.set_solver_specific_parameters_as_string(
            "MIPRELSTOP {} PRESOLVE {} MAXTIME {}".format(
                parameters.solver_duality_gap, int(parameters.use_presolve), parameters.solver_time_out
            )
        )

        if parameters.debug:
            lp_file_name = os.path.join(parameters.output_folder, "storage_{}.lp".format(equipment_name))
            model.export_model(lp_file_name)

        model.solve(float(parameters.solver_time_out))

        if parameters.verbose:
            cfg.logger.info("Solver status: {}".format(model.solution_info.status))
            cfg.logger.info("Objective function value: {}".format(model.objective))

    # ------ Price computation ------
    def priceCalculation(Equipment, Qv, Qa, p):
        P_a_max = 0
        P_v_min = 0
        # Get the price forecast from the input marker: estimations are at ActionHour, from StartDate to EndDate
        # The price forecast is relative to the equipment's market area
        # it is the estimation the actor has of the energy prices at the given date
        PriceForecast = Equipment.Portfolio.MarketArea.PriceForecastMedium.GetForecast(
            p.execution_date, p.start_date, p.end_date
        )

        # Check if either Qv or Qa is empty (i.e. contains only 0)
        Qv_empty = True
        for qv_key, qv_value in Qv.items():
            if qv_value != 0:
                Qv_empty = False

        Qa_empty = True
        for qa_key, qa_value in Qa.items():
            if qa_value != 0:
                Qa_empty = False

        # Evaluate the minimum of sale prices
        if [i for i, e in Qv.items() if e != 0]:
            P_v_min = min([PriceForecast.GetValue(t) for t in [i for i, e in Qv.items() if e != 0]])
        # Evaluate the maximum of purchase prices
        if [i for i, e in Qa.items() if e != 0]:
            P_a_max = max([PriceForecast.GetValue(t) for t in [i for i, e in Qa.items() if e != 0]])

        if (Equipment.StorageType in ["Battery", "PumpedHydraulicStorage"]) or (Equipment.isV2G):
            # if negative prices, Psale and Ppurchase are set to zero
            # Else they are evaluated in a manner that makes profit =  0

            if P_a_max <= 0:
                P_a_max = 0
            if P_v_min <= 0:
                P_v_min = 0

            if Qa_empty:
                Psale = P_v_min
                Ppurchase = 0
            elif Qv_empty:
                Psale = 0
                Ppurchase = P_a_max
            elif P_a_max == 0 and P_v_min == 0:
                Psale = 0
                Ppurchase = 0
            else:
                a = (Equipment.DischargeEfficiency * Equipment.ChargeEfficiency * P_v_min - P_a_max) / (
                    Equipment.DischargeEfficiency * Equipment.ChargeEfficiency * P_v_min + P_a_max
                )
                Psale = P_v_min * (1 - a)
                Ppurchase = P_a_max * (1 + a)

        else:
            Psale = 0
            Ppurchase = P_a_max

        return Psale, Ppurchase

    # ------ Order formulation functions ------
    @staticmethod
    def formulate_storage_orders(dataset: DayAheadOrdersInputDataset, parameters: DayAheadOrdersParameters) -> None:
        """
         Formulates storage bids on the spot market.
         Uses the parameters specified by the user and the input marker to create bids based on the forecast
         stored in the Power forecasting matrix of a "Storage" equipement.

         The function takes the following arguments:

        - `dataset`: a DayAheadOrdersInputDataset.
        - `parameters` a named tuple of parameters, containing the common parameters.
        """

        # Loop on all the actors that have EV storage capacity
        for equipment in dataset.storage:
            # Avoid equipments that have a MaximumEnergy of 0 (meaning that they are offline)
            local_index = generate_datetimes(
                parameters.start_date,
                parameters.end_date.subtract(minutes=parameters.time_step),
                pendulum.duration(minutes=parameters.time_step),
            )

            local_max_energy = (
                equipment.maximum_energy.set_frequency(pendulum.Duration(minutes=parameters.time_step), False)
                .filter(item=local_index, inplace=False)
                .max()
            )
            if local_max_energy <= 0:
                if parameters.verbose:
                    cfg.logger.debug("Equipment {} avoided, as its MaximumEnergy is 0".format(str(equipment.Name)))
                continue

            cfg.logger.debug("Equipment {}".format(str(equipment.name)))

            # TODO
            buy_submitted_volumes = Timeseries(None)
            sell_submitted_volumes = Timeseries(None)
            # buy_submitted_volumes = API.TimeSeries.NewTimeSeries("", API.TimeSeries.Constant, "MW", local_index, 0)
            # sell_submitted_volumes = API.TimeSeries.NewTimeSeries("", API.TimeSeries.Constant, "MW", local_index, 0)

            # if the stock of the equipment at start date is not defined, initiate it
            initial_stock = DayAheadStorage.initiate_stock(equipment, parameters)

            # Determine offers times and quantities through an optimisation algorithm under a price forecast
            if equipment.storage_type == StorageType.ELECTRIC_VEHICLE:
                Qv, Qa = DayAheadStorage.optimize_ev(equipment, initial_stock, parameters)
            else:
                Qv, Qa = DayAheadStorage.optimize_battery(equipment, initial_stock, parameters)

            # Determine sale and purchase prices
            Psale, Ppurchase = priceCalculation(equipment, Qv, Qa, parameters)

            # Store Ppurchase as price reference in VariableCost, in the outputMarker.
            # Psale can then be deduced from Ppurchase, Charge and and Discharge efficiency
            if Ppurchase != 0:
                equipment.VariableCost.SetValue(parameters.start_date, round(Ppurchase, 2))
                equipment.VariableCost.SetValue(
                    parameters.end_date.AddMinutes(-parameters.time_step), round(Ppurchase, 2)
                )
            elif equipment.DischargeEfficiency != 0 and equipment.ChargeEfficiency != 0:
                equipment.VariableCost.SetValue(
                    parameters.start_date, round(Psale * equipment.DischargeEfficiency * equipment.ChargeEfficiency, 2)
                )
                equipment.VariableCost.SetValue(
                    parameters.end_date.AddMinutes(-parameters.time_step),
                    round(Psale * equipment.DischargeEfficiency * equipment.ChargeEfficiency, 2),
                )
            else:
                equipment.VariableCost.SetValue(parameters.start_date, round(Psale, 2))
                equipment.VariableCost.SetValue(parameters.end_date.AddMinutes(-parameters.time_step), round(Psale, 2))
                API.IO.Trace.Log(
                    "WARNING: ChargeEfficiency or DischargeEfficiency is null for equipment {}. "
                    "This is not supposed to be the case, as the default value for these is 1 and not 0".format(
                        equipment.Name
                    ),
                    API.IO.LogTypeWarn,
                )

            # --- Formulate orders, possibly with associated coupling instances
            # First, orders that are included in a COMPLEMENT coupling
            daily_buy_volume = sum(buy_volume * parameters.time_step / 60.0 for buy_volume in Qa.values())
            if equipment.StorageType == "ElectricVehicle" and daily_buy_volume > 0:
                # Create the order coupling instance
                coupling_instance = dataset.Market.OrderCoupling.CreateInstance(
                    "COMPLEMENT_DA_{}_{}".format(
                        equipment.Name, functions.get_date_to_clean_string(parameters.execution_date)
                    )
                )
                coupling_instance.CouplingType = "COMPLEMENT"
                coupling_instance.ComplementDirection = "EqualTo"

                # Compute the ComplementEnergy according to the evolution DisplacementEnergy over the day,
                # if it is feasible given all orders generated for this equipment.
                # If not, the energy requirement is capped to the feasible limit
                energy_requirement = equipment.DisplacementEnergy.GetValue(
                    parameters.end_date.AddMinutes(-parameters.time_step)
                ) - equipment.DisplacementEnergy.GetValue(parameters.start_date.AddMinutes(-parameters.time_step))

                if energy_requirement > daily_buy_volume:
                    coupling_instance.ComplementEnergy = daily_buy_volume
                else:
                    coupling_instance.ComplementEnergy = energy_requirement

                for t in [i for i, e in Qa.items() if e != 0]:
                    AddSpotOrderWithCoupling(
                        "Buy", equipment, t, Qa[t], Ppurchase, parameters, dataset, coupling_instance
                    )
                    buy_submitted_volumes[t] += Qa[t]
                for t in [i for i, e in Qv.items() if e != 0]:
                    AddSpotOrderWithCoupling("Sell", equipment, t, Qv[t], Psale, parameters, dataset, coupling_instance)
                    sell_submitted_volumes[t] += Qv[t]

            # All other orders
            else:
                # Create a COMPLEMENT order coupling
                coupling_instance = dataset.Market.OrderCoupling.CreateInstance(
                    "COMPLEMENT_DA_{}_{}".format(
                        equipment.Name, functions.get_date_to_clean_string(parameters.execution_date)
                    )
                )

                for t in [i for i, e in Qa.items() if e != 0]:
                    AddSpotOrderWithCoupling(
                        "Buy", equipment, t, Qa[t], Ppurchase, parameters, dataset, coupling_instance
                    )
                    buy_submitted_volumes[t] += Qa[t]
                for t in [i for i, e in Qv.items() if e != 0]:
                    AddSpotOrderWithCoupling("Sell", equipment, t, Qv[t], Psale, parameters, dataset, coupling_instance)
                    sell_submitted_volumes[t] += Qv[t]

                # Fill the COMPLEMENT order coupling
                coupling_instance.CouplingType = "COMPLEMENT"
                coupling_instance.ComplementDirection = "EqualTo"
                coupling_instance.ComplementEnergy = buy_submitted_volumes.Sum() - sell_submitted_volumes.Sum()

            equipment.DABuySubmittedVolume += buy_submitted_volumes
            equipment.DASellSubmittedVolume += sell_submitted_volumes

    @staticmethod
    def create_spot_order(
        order_type, equipment, start_date, qmax, price, parameters: DayAheadOrdersParameters
    ) -> Order:
        order_name = "storage_order_type_{}_at_{}_for_unit_{}".format(
            order_type, Utilities.get_date_to_clean_string(start_date), equipment.name
        )
        order = Order(name=order_name)
        order.equipment = equipment
        order.portfolio = equipment.portfolio
        order.market_area = equipment.portfolio.market_area
        order.execution_date = parameters.execution_date
        order.start_date = start_date
        order.end_date = start_date + timedelta(minutes=parameters.time_step)
        order.order_type = order_type
        order.product = Product.DayAhead
        order.qmax = qmax
        order.qmin = 0.0
        order.price = price
        return order

    @staticmethod
    def AddSpotOrder(order_type, equipment, start_date, qmax, price, parameters: DayAheadOrdersParameters, dataset):
        order = DayAheadStorage.create_spot_order(order_type, equipment, start_date, qmax, price, parameters)
        dataset.order.append(order)

    @staticmethod
    def AddSpotOrderWithCoupling(
        order_type, equipment, start_date, qmax, price, parameters, dataset, coupling_instance
    ):
        order = DayAheadStorage.create_spot_order(order_type, equipment, start_date, qmax, price, parameters)
        dataset.order.append(order)
        coupling_instance.orders.append(Order)

    # ------ Other functions ------
    @staticmethod
    def initiate_stock(equipment: Equipment, parameters: DayAheadOrdersParameters) -> float | None:
        # FC: The first step is to evaluate if the equipment is in an "Initial" situation or not
        # This is indicated by StoredEnergy, but one should be careful here
        # The idea is to verify that there is a value in StoredEnergy "not too long" before start_date,
        # and we arbitrarily choose to look as far as two days before to verify this. Assumption could be discussed.
        energy_forecast = equipment.stored_energy.get_forecast(
            parameters.execution_date,
            parameters.start_date.subtract(days=2),
            parameters.start_date.subtract(minutes=parameters.time_step),
        )
        if len(energy_forecast) == 0:
            initial_stock = equipment.storage_initial_level * equipment.maximum_energy.get_value(parameters.start_date)
        else:
            initial_stock = energy_forecast.get_value(parameters.start_date.subtract(parameters.time_step))
        return initial_stock
