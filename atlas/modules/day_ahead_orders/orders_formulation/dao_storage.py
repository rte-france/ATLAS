"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Any

from pydantic_extra_types.pendulum_dt import DateTime

import atlas.config as cfg
from atlas import Equipment, Order, OrderCoupling, Timeseries
from atlas.enum import ComplementDirection, CouplingType, OrderType, Product, StorageType
from atlas.modules.day_ahead_orders.day_ahead_orders_input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.optim_models.battery_model import BatteryModel
from atlas.modules.day_ahead_orders.optim_models.electric_vehicle_model import ElectricVehicleModel
from atlas.timing import generate_datetimes


class DAOStorage:
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
            parameters, parameters.solver.upper(), "Optimization of the storage unit " + equipment.name, equipment
        )
        model.create_decision_variables(parameters.ev_nb_fragments)
        model.create_objective_function(parameters.ev_nb_fragments, parameters.ev_smoothing_factor)
        model.create_constraints(initial_stock)
        model.set_solver_specific_parameters_as_string(
            f"MIPRELSTOP {parameters.solver_duality_gap} PRESOLVE {int(parameters.use_presolve)} MAXTIME {parameters.solver_time_out.total_minutes()}"
        )

        # Solving the problem
        model.solve_with_xpress()

        # Assign the values to the output variables
        # Note that the time domain of the output variables is [StartDate, EndDate]
        Qvv = {}
        Qaa = {}
        for t in model.time_frame:
            if t >= parameters.end_date:
                break
            Qvv[t] = round(model.Qv[t].solution_value(), 2)
            Qaa[t] = round(model.Qa[t].solution_value(), 2)

        return Qvv, Qaa

    @staticmethod
    def optimize_battery(
        equipment: Equipment, initial_stock: float | None, parameters: DayAheadOrdersParameters
    ) -> tuple[dict[Any, Any], dict[Any, Any]]:
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
        else:
            cfg.logger.error(
                f"equipment {equipment.name} isn't {StorageType.BATTERY} nor {StorageType.PUMPED_HYDRAULIC_STORAGE}"
            )

        # Creation of optimization problem
        model = BatteryModel(
            parameters,
            parameters.solver.upper(),
            "Optimization of the storage unit " + equipment.name,
            equipment,
            optimization_period,
        )
        model.create_decision_variables(power_fragments)
        model.create_objective_function(power_fragments, smoothing_factor)
        model.create_constraints(initial_stock, power_fragments)
        model.set_solver_specific_parameters_as_string(
            f"MIPRELSTOP {parameters.solver_duality_gap} PRESOLVE {int(parameters.use_presolve)} MAXTIME {parameters.solver_time_out.total_minutes()}"
        )

        # Solving the problem
        model.solve_with_xpress()

        # Assign the values to the output variables
        # Note that the time domain of the output variables is [StartDate, EndDate]
        Qvv = {}
        Qaa = {}
        for t in model.time_frame:
            if t >= parameters.end_date:
                break
            Qvv[t] = round(model.Qv[t].solution_value(), 2)
            Qaa[t] = round(model.Qa[t].solution_value(), 2)

        return Qvv, Qaa

    @staticmethod
    def price_calculation(
        equipment: Equipment, Qv: dict, Qa: dict, parameters: DayAheadOrdersParameters
    ) -> tuple[Any, Any]:
        """------ Price computation ------"""
        P_a_max = 0
        P_v_min = 0
        # Get the price forecast from the input marker: estimations are at ActionHour, from StartDate to EndDate
        # The price forecast is relative to the equipment's market area
        # it is the estimation the actor has of the energy prices at the given date
        price_forecast = equipment.portfolio.market_area.price_forecast_medium.get_forecast(
            parameters.execution_date,
            parameters.start_date,
            parameters.end_date,
            parameters.time_step,
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
            P_v_min = min([price_forecast.get_value(t) for t in [i for i, e in Qv.items() if e != 0]])
        # Evaluate the maximum of purchase prices
        if [i for i, e in Qa.items() if e != 0]:
            P_a_max = max([price_forecast.get_value(t) for t in [i for i, e in Qa.items() if e != 0]])

        if (equipment.storage_type in [StorageType.BATTERY, StorageType.PUMPED_HYDRAULIC_STORAGE]) or (
            equipment.is_v2g
        ):
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
                a = (equipment.discharge_efficiency * equipment.charge_efficiency * P_v_min - P_a_max) / (
                    equipment.discharge_efficiency * equipment.charge_efficiency * P_v_min + P_a_max
                )
                Psale = P_v_min * (1 - a)
                Ppurchase = P_a_max * (1 + a)

        else:
            Psale = 0
            Ppurchase = P_a_max

        return Psale, Ppurchase

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
            end_date = parameters.penultimate_date
            local_index = generate_datetimes(
                parameters.start_date,
                end_date,
                parameters.time_step,
            )

            local_max_energy = (
                equipment.maximum_energy.set_frequency(parameters.time_step, False)
                .filter(item=local_index, inplace=False)
                .max()
            )
            if local_max_energy <= 0:
                if parameters.verbose:
                    cfg.logger.debug(f"Equipment {str(equipment.name)} avoided, as its maximum_energy is 0")
                continue

            cfg.logger.debug(f"Equipment {str(equipment.name)}")

            buy_submitted_volumes = Timeseries.from_index(parameters.start_date, parameters.time_step, end_date, 0)
            sell_submitted_volumes = Timeseries.from_index(parameters.start_date, parameters.time_step, end_date, 0)

            # if the stock of the equipment at start date is not defined, initiate it
            initial_stock = DAOStorage.initiate_stock(equipment, parameters)

            # Determine offers times and quantities through an optimisation algorithm under a price forecast
            if equipment.storage_type == StorageType.ELECTRIC_VEHICLE:
                Qv, Qa = DAOStorage.optimize_ev(equipment, initial_stock, parameters)
            else:
                Qv, Qa = DAOStorage.optimize_battery(equipment, initial_stock, parameters)

            # Determine sale and purchase prices
            Psale, Ppurchase = DAOStorage.price_calculation(equipment, Qv, Qa, parameters)

            # Store Ppurchase as price reference in variable_cost, in the dataset.
            # Psale can then be deduced from Ppurchase, Charge and and Discharge efficiency
            if equipment.variable_cost is None:
                equipment.variable_cost = Timeseries(None)
            if Ppurchase != 0:
                equipment.variable_cost.set_value(parameters.start_date, round(Ppurchase, 2))
                equipment.variable_cost.set_value(parameters.penultimate_date, round(Ppurchase, 2))
            elif equipment.discharge_efficiency != 0 and equipment.charge_efficiency != 0:
                equipment.variable_cost.set_value(
                    parameters.start_date,
                    round(Psale * equipment.discharge_efficiency * equipment.charge_efficiency, 2),
                )
                equipment.variable_cost.set_value(
                    parameters.penultimate_date,
                    round(Psale * equipment.discharge_efficiency * equipment.charge_efficiency, 2),
                )
            else:
                equipment.variable_cost.set_value(parameters.start_date, round(Psale, 2))
                equipment.variable_cost.set_value(parameters.penultimate_date, round(Psale, 2))
                cfg.logger.warning(
                    f"WARNING: ChargeEfficiency or DischargeEfficiency is null for equipment {equipment.name}. "
                    "This is not supposed to be the case, as the default value for these is 1 and not 0"
                )

            # --- Formulate orders, possibly with associated coupling instances
            # First, orders that are included in a COMPLEMENT coupling
            daily_buy_volume = sum(buy_volume * parameters.time_step.total_hours() for buy_volume in Qa.values())
            if equipment.storage_type == StorageType.ELECTRIC_VEHICLE and daily_buy_volume > 0:
                # Create the order coupling instance
                coupling_instance = OrderCoupling(
                    name=f"COMPLEMENT_DA_{equipment.name}_{parameters.execution_date}",
                    orders=[],
                    coupling_type=CouplingType.COMPLEMENT,
                    complement_direction=ComplementDirection.EqualTo,
                )

                # Compute the ComplementEnergy according to the evolution DisplacementEnergy over the day,
                # if it is feasible given all orders generated for this equipment.
                # If not, the energy requirement is capped to the feasible limit
                energy_requirement = equipment.displacement_energy.get_value(
                    parameters.penultimate_date
                ) - equipment.displacement_energy.get_value(parameters.start_date - parameters.time_step)

                if energy_requirement > daily_buy_volume:
                    coupling_instance.complement_energy = daily_buy_volume
                else:
                    coupling_instance.complement_energy = energy_requirement

                for t in [i for i, e in Qa.items()]:
                    DAOStorage.add_spot_order_with_coupling(
                        OrderType.Buy, equipment, t, Qa[t], Ppurchase, parameters, dataset, coupling_instance
                    )
                    buy_submitted_volumes.add_value_at(t, Qa[t])
                for t in [i for i, e in Qv.items()]:
                    DAOStorage.add_spot_order_with_coupling(
                        OrderType.Sell, equipment, t, Qv[t], Psale, parameters, dataset, coupling_instance
                    )
                    sell_submitted_volumes.add_value_at(t, Qv[t])

                dataset.order_coupling.append(coupling_instance)

            # All other orders
            else:
                # Create a COMPLEMENT order coupling
                coupling_instance = OrderCoupling(
                    name=f"COMPLEMENT_DA_{equipment.name}_{parameters.execution_date}",
                    orders=[],
                )

                for t in [i for i, e in Qa.items()]:
                    DAOStorage.add_spot_order_with_coupling(
                        OrderType.Buy, equipment, t, Qa[t], Ppurchase, parameters, dataset, coupling_instance
                    )
                    buy_submitted_volumes.add_value_at(t, Qa[t])
                for t in [i for i, e in Qv.items()]:
                    DAOStorage.add_spot_order_with_coupling(
                        OrderType.Sell, equipment, t, Qv[t], Psale, parameters, dataset, coupling_instance
                    )
                    sell_submitted_volumes.add_value_at(t, Qv[t])

                # Fill the COMPLEMENT order coupling
                coupling_instance.coupling_type = CouplingType.COMPLEMENT
                coupling_instance.complement_direction = ComplementDirection.EqualTo
                coupling_instance.complement_energy = buy_submitted_volumes.sum() - sell_submitted_volumes.sum()
                dataset.order_coupling.append(coupling_instance)

            if equipment.da_buy_submitted_volume is None:
                equipment.da_buy_submitted_volume = buy_submitted_volumes
            else:
                equipment.da_buy_submitted_volume += buy_submitted_volumes

            if equipment.da_sell_submitted_volume is None:
                equipment.da_sell_submitted_volume = sell_submitted_volumes
            else:
                equipment.da_sell_submitted_volume += sell_submitted_volumes

    @staticmethod
    def add_spot_order_with_coupling(
        order_type: OrderType,
        equipment: Equipment,
        start_date: DateTime,
        qmax: float,
        price: float,
        parameters: DayAheadOrdersParameters,
        dataset,
        coupling_instance: OrderCoupling,
    ):
        order = Order(
            name=f"storage_order_type_{order_type}_at_{start_date}_for_unit_{equipment.name}",
            equipment=equipment,
            portfolio=equipment.portfolio,
            market_area=equipment.portfolio.market_area,
            execution_date=parameters.execution_date,
            start_date=start_date,
            end_date=start_date + parameters.time_step,
            order_type=order_type,
            product=Product.DayAhead,
            qmax=qmax,
            qmin=0.0,
            price=price,
        )
        dataset.order.append(order)
        coupling_instance.orders.append(order)

    @staticmethod
    def initiate_stock(equipment: Equipment, parameters: DayAheadOrdersParameters) -> float | None:
        # FC: The first step is to evaluate if the equipment is in an "Initial" situation or not
        # This is indicated by StoredEnergy, but one should be careful here
        # The idea is to verify that there is a value in StoredEnergy "not too long" before start_date,
        # and we arbitrarily choose to look as far as two days before to verify this. Assumption could be discussed.
        if equipment.stored_energy is None:
            initial_stock = equipment.storage_initial_level * equipment.maximum_energy.get_value(parameters.start_date)
        else:
            energy_forecast = equipment.stored_energy.get_forecast(
                parameters.execution_date,
                parameters.start_date.subtract(days=2),
                parameters.start_date - parameters.time_step,
                parameters.time_step,
            )
            if len(energy_forecast) == 0:
                initial_stock = equipment.storage_initial_level * equipment.maximum_energy.get_value(
                    parameters.start_date
                )
            else:
                initial_stock = energy_forecast.get_value(parameters.start_date - parameters.time_step)
        return initial_stock
