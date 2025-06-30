"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import os
from datetime import timedelta

import pendulum

import atlas.config as cfg
from atlas import Timeseries, Equipment, Order
from atlas.enum import StorageType, Product
from atlas.modules.day_ahead_orders.day_ahead_orders_input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.optim_models.electric_vehicle_model import ElectricVehicleModel
from atlas.modules.day_ahead_orders.tools.Utilities import Utilities
from atlas.timing import generate_datetimes


class DayAheadStorage:
    # ------ Main optimization functions ------
    # Optimization function for ElectricVehicle units
    @staticmethod
    def optimize_ev(equipment: Equipment, InitialStock: float | None, parameters: DayAheadOrdersParameters) -> [{}, {}]:
        # Creation of optimization problem
        # --------------------------------
        OPPROB = ElectricVehicleModel(
            "Optimization of the storage unit " + equipment.name, "CBC", parameters, equipment
        )
        OPPROB.create_decision_variables()
        OPPROB.create_objective_function()
        OPPROB.create_constraints(InitialStock)

        # --- TODO ---

        ##  PROBLEM SOLVING  ##
        if parameters.solver.upper() == "XPRESS":
            optim_solver = OPPROB.NewOpSolver("xpress")

            optim_solver.SetSolverSpecificParameters(
                "MIPRELSTOP {} PRESOLVE {} MAXTIME {}".format(
                    parameters.duality_gap, int(parameters.presolve), parameters.time_out
                )
            )

            if parameters.debug:
                lp_file_name = os.path.join(parameters.output_folder, "storage_{}.lp".format(equipment.Name))
                OPPROB.WriteLP(lp_file_name, True)

            OPPROB.SolveORTools(optim_solver)

            if parameters.verbose:
                API.IO.Trace.Log("Solver status: {}".format(OPPROB.Status), API.IO.LogTypeInfo)
                API.IO.Trace.Log(
                    "Objective function value: {}".format(API.Solver.Value(OPPROB.Objective)), API.IO.LogTypeInfo
                )
        else:
            # If another solver is being used, consider setting the NoOverlap parameter to False as it previsously raised errors otherwise with GLPK
            raise ValueError(
                "Please use XPRESS, as other solvers either are deprecated or provide non-optimal solutions"
            )

        # Assign the values to the output variables
        # Note that the time domain of the output variables is [StartDate, EndDate]
        Qvv = {}
        Qaa = {}
        for t in time_frame:
            if t >= parameters.end_date:
                break
            Qvv[t] = round(Qv[t].VarValue, 2)
            Qaa[t] = round(Qa[t].VarValue, 2)

        return Qvv, Qaa

    # Optimization function for Battery and PHS units
    def optimize_battery(Equipment, InitialStock, p):
        if Equipment.StorageType == "Battery":
            optimizationPeriod = p.battery_additional_hours
            smoothingFactor = p.battery_smoothing_factor
            powerFragments = p.battery_nb_fragments
        elif Equipment.StorageType == "PumpedHydraulicStorage":
            optimizationPeriod = p.phs_additional_hours
            smoothingFactor = p.phs_smoothing_factor
            powerFragments = p.phs_nb_fragments

        ##  CREATION OF PROBLEM  ##
        # Get the price forecast from the input marker: estimations are at ActionHour, over the optimisation period
        # The price forecast is relative to the equipment's market area
        PriceForecast = Equipment.Portfolio.MarketArea.PriceForecastMedium.GetForecast(
            p.execution_date, p.start_date, p.end_date.AddHours(optimizationPeriod)
        )

        # Set-up the time frames
        # Definition of the timeFrame time frame: the time frame on which
        # the optimization program will be solved.
        # Remark: we define the time series until end_date - time_step because
        # we want all time steps to lie in the [start_date, endOptimizationDate] range.
        timeFrame = API.DatetimeIndex.NewIndex(
            p.start_date, p.end_date.AddHours(optimizationPeriod).AddMinutes(-p.time_step), str(p.time_step) + "m"
        )
        # Creation of optimization problem
        # --------------------------------

        OPPROB = API.Solver.NewOpProblem(
            "Optimization of the storage unit " + Equipment.Name,
            API.Solver.OpCategoryBinary,
            API.Solver.OpSenseMaximize,
        )

        # Creation of decision variables
        # ------------------------------

        # Total quantities bought and purchased in the market at each time step
        Qv = {}
        Qa = {}
        # Quantities bought and purchased in each fragment of power i at each time step
        Qvf = {}
        Qaf = {}
        # Energy stored in battery at each time step
        # StoredEnergy[t] corresponds to the energy stord in battery at t + 1
        StoredEnergy = {}
        # Binary variable that represents the state of sale at each time step: 1 if selling, 0 if not
        isSell = {}
        for t in timeFrame:
            Qv[t] = API.Solver.NewOpVariable("Amount_sold_at_{}".format(t), 0, None)
            Qa[t] = API.Solver.NewOpVariable("Amount_purchased_at_{}".format(t), 0, None)
            isSell[t] = API.Solver.NewOpVariable("isSell_at_{}".format(t), API.Solver.OpCategoryBinary)
            StoredEnergy[t] = API.Solver.NewOpVariable("StoredEnergy_at_{}".format(t), 0, None)
            Qvf[t] = {}
            Qaf[t] = {}
            for i in range(powerFragments):
                Qvf[t][i] = API.Solver.NewOpVariable("Amount_sold_in_fragment_{}_at_{}".format(i, t), 0, None)
                Qaf[t][i] = API.Solver.NewOpVariable("Amount_purchased_in_fragment_{}_at_{}".format(i, t), 0, None)

        # Creation of objective function
        # ------------------------------

        # The objective function is the total profit over the optimisation period
        if powerFragments == 1:
            OPPROB += (
                sum(
                    PriceForecast.GetValue(t) * Qvf[t][0] * p.time_step / 60.0
                    - PriceForecast.GetValue(t) * Qaf[t][0] * p.time_step / 60.0
                    for t in timeFrame
                ),
                "Profit",
            )
        else:
            OPPROB += (
                sum(
                    sum(
                        PriceForecast.GetValue(t)
                        * (1 - i * smoothingFactor / (powerFragments - 1))
                        * Qvf[t][i]
                        * p.time_step
                        / 60.0
                        - PriceForecast.GetValue(t)
                        * (1 + i * smoothingFactor / (powerFragments - 1))
                        * Qaf[t][i]
                        * p.time_step
                        / 60.0
                        for i in range(powerFragments)
                    )
                    for t in timeFrame
                ),
                "Profit",
            )

        # Creation of constraints
        # -----------------------
        for t in timeFrame:
            for i in range(powerFragments):
                OPPROB += (
                    Qvf[t][i] * powerFragments <= Equipment.MaximumPower.GetValue(t),
                    "Respect_of_sale_power_fragment_{}_limit_at_{}".format(i, t),
                )
                OPPROB += (
                    Qaf[t][i] * powerFragments <= abs(Equipment.MinimumPower.GetValue(t)),
                    "Respect_of_purchase_power_fragment_{}_limit_at_{}".format(i, t),
                )

            # Total bought/sold energy at each time step is the sum of the fragments at time step
            OPPROB += (
                Qv[t] == sum(Qvf[t][i] for i in range(powerFragments)),
                "Evaluation_of_quantity_sold_at_{}".format(t),
            )
            OPPROB += (
                Qa[t] == sum(Qaf[t][i] for i in range(powerFragments)),
                "Evaluation_of_quantity_purchased_at_{}".format(t),
            )

            # StoredEnergy tracking constraint, evaluates the stock at each time step
            if t == p.start_date:
                OPPROB += (
                    StoredEnergy[t]
                    == (
                        InitialStock
                        + p.time_step
                        / 60.0
                        * (Qa[t] * Equipment.ChargeEfficiency - Qv[t] / Equipment.DischargeEfficiency)
                    ),
                    "Stock_tracking_at_{}".format(t.AddMinutes(p.time_step)),
                )
            else:
                OPPROB += (
                    (
                        StoredEnergy[t]
                        == StoredEnergy[t.AddMinutes(-p.time_step)]
                        + p.time_step
                        / 60.0
                        * (Qa[t] * Equipment.ChargeEfficiency - Qv[t] / Equipment.DischargeEfficiency)
                    ),
                    "Stock_tracking_at_{}".format(t.AddMinutes(p.time_step)),
                )

            # Respect of system states constraints (isSell and isV2G)
            OPPROB += Qv[t] <= isSell[t] * Equipment.MaximumPower.GetValue(t), "Respect_Pmax_sale_at_{}".format(t)
            OPPROB += (
                Qa[t] <= (1 - isSell[t]) * abs(Equipment.MinimumPower.GetValue(t)),
                "Respect_Pmax_purchase_at_{}".format(t),
            )
            OPPROB += Qv[t] >= 0, "Respect_Pmin_sale_at_{}".format(t)
            OPPROB += Qa[t] >= 0, "Respect_Pmin_purchase_at_{}".format(t)

            # Respect of minimum and maximum storage levels constraints
            OPPROB += (
                StoredEnergy[t] >= (Equipment.MinimumStateOfCharge.GetValue(t) * Equipment.MaximumEnergy.GetValue(t)),
                "Minimum_storage_level_constraint_at_{}".format(t),
            )
            OPPROB += (
                StoredEnergy[t] <= Equipment.MaximumEnergy.GetValue(t),
                "Maximum_storage_level_constraint_at_{}".format(t),
            )

        # Respect of the balance between sales and purchases
        OPPROB += (
            sum(Qa[t] for t in timeFrame) * Equipment.ChargeEfficiency
            == sum(Qv[t] for t in timeFrame) / Equipment.DischargeEfficiency,
            "Respect_of_cycle_balance",
        )

        # Solving the problem
        if p.solver.upper() == "XPRESS":
            optim_solver = OPPROB.NewOpSolver("xpress")

            optim_solver.SetSolverSpecificParameters(
                "MIPRELSTOP {} PRESOLVE {} MAXTIME {}".format(p.duality_gap, int(p.presolve), p.time_out)
            )

            if p.debug:
                lp_file_name = os.path.join(p.output_folder, "storage_{}.lp".format(Equipment.Name))
                OPPROB.WriteLP(lp_file_name, True)

            OPPROB.SolveORTools(optim_solver)

            if p.verbose:
                API.IO.Trace.Log("Solver status: {}".format(OPPROB.Status), API.IO.LogTypeInfo)
                API.IO.Trace.Log(
                    "Objective function value: {}".format(API.Solver.Value(OPPROB.Objective)), API.IO.LogTypeInfo
                )
        else:
            # If another solver is being used, consider setting the NoOverlap parameter to False as it previsously raised errors otherwise with GLPK
            raise ValueError(
                "Please use XPRESS, as other solvers either are deprecated or provide non-optimal solutions"
            )

        # Assign the values to the output variables
        # Note that the time domain of the output variables is [StartDate, EndDate]
        Qvv = {}
        Qaa = {}
        for t in timeFrame:
            if t >= p.end_date:
                break
            Qvv[t] = round(Qv[t].VarValue, 2)
            Qaa[t] = round(Qa[t].VarValue, 2)

        return Qvv, Qaa

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
            OPPROB = ElectricVehicleModel(
                "Optimization of the storage unit " + equipment.name, "CBC", parameters, equipment
            )
            initial_stock = DayAheadStorage.initiate_stock(equipment, parameters)

            # Determine offers times and quantities through an optimisation algorithm under a price forecast
            if equipment.storage_type == StorageType.ELECTRIC_VEHICLE:
                Qv, Qa = DayAheadStorage.optimize_ev(equipment, initial_stock, parameters)
            else:
                Qv, Qa = optimize_battery(equipment, initial_stock, parameters)

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
