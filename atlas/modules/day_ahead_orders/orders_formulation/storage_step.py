"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from concurrent.futures import ProcessPoolExecutor, as_completed

from pendulum import DateTime

import atlas.config as cfg
from atlas.enums import ComplementDirection, CouplingType, OrderType, Product, StorageType
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.dao_timeseries import DAOTimeseries
from atlas.modules.day_ahead_orders.models.order import OrderDAO
from atlas.modules.day_ahead_orders.models.order_coupling import OrderCouplingDAO
from atlas.modules.day_ahead_orders.models.storage import StorageDAO
from atlas.modules.day_ahead_orders.orders_formulation.storage_worker import (
    _initiate_stock,
    _optimize_battery,
    _optimize_ev,
    _price_calculation,
    optimize_single_storage,
)
from atlas.modules.day_ahead_orders.output_dataset import DayAheadOrdersOutput
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.solver.models import SolverOptions
from atlas.timing import bmo_name_datetime_to_str, generate_datetimes


class StorageStep:
    def __init__(self, dataset: DayAheadOrdersOutput, parameters: DayAheadOrdersParameters) -> None:
        """
        :param dataset: the dataset
        :type dataset: DayAheadOrdersOutput
        :param parameters: the parameters
        :type parameters: DayAheadOrdersParameters
        :return: None
        """
        self.dataset = dataset
        self.parameters = parameters

    def formulate_storage_orders(self) -> None:
        """
        Formulates storage bids on the spot market.
        Uses the parameters specified by the user and the dataset to create bids based on the forecast
        stored in the Power forecasting matrix of a "Storage" equipment.

        Supports both sequential and parallel processing based on use_multiprocessing parameter.
        :return: None
        """
        if self.parameters.use_multiprocessing:
            self._formulate_storage_orders_parallel()
        else:
            self._formulate_storage_orders_sequential()

    def _formulate_storage_orders_parallel(self) -> None:
        """
        Formulate storage orders using multiprocessing for parallel execution.
        """
        cfg.logger.info(f"Starting parallel storage optimization for {len(self.dataset.storage)} units")

        with ProcessPoolExecutor(max_workers=self.parameters.max_workers) as executor:
            future_to_storage = {
                executor.submit(optimize_single_storage, storage, self.parameters): storage.name
                for storage in self.dataset.storage
            }

            for future in as_completed(future_to_storage):
                storage_name = future_to_storage[future]
                try:
                    result = future.result()

                    if result.success:
                        # Add orders and couplings to the dataset
                        self.dataset.order.extend(result.orders)
                        self.dataset.order_coupling.extend(result.order_couplings)

                        # Update the storage unit in the dataset with submitted volumes and variable cost
                        for storage in self.dataset.storage:
                            if storage.name == result.storage_name:
                                if storage.da_buy_submitted_volume is None:
                                    storage.da_buy_submitted_volume = result.buy_submitted_volumes
                                else:
                                    storage.da_buy_submitted_volume += result.buy_submitted_volumes

                                if storage.da_sell_submitted_volume is None:
                                    storage.da_sell_submitted_volume = result.sell_submitted_volumes
                                else:
                                    storage.da_sell_submitted_volume += result.sell_submitted_volumes

                                if result.variable_cost is not None:
                                    storage.variable_cost = result.variable_cost
                                break

                        cfg.logger.info(f"Completed optimization for storage: {storage_name}")
                    else:
                        cfg.logger.warning(f"Optimization skipped or failed for storage: {storage_name}")

                except Exception as e:
                    cfg.logger.error(f"Error processing storage {storage_name}: {e}")

    def _formulate_storage_orders_sequential(self) -> None:
        """
        Formulate storage orders using sequential processing (original implementation).
        """
        cfg.logger.info(f"Starting sequential storage optimization for {len(self.dataset.storage)} units")

        # Loop on all the actors that have EV storage capacity
        for storage in self.dataset.storage:
            # Avoid equipments that have a MaximumEnergy of 0 (meaning that they are offline)
            end_date = self.parameters.penultimate_date
            local_index = generate_datetimes(
                self.parameters.start_date,
                end_date,
                self.parameters.timestep,
            )

            local_max_energy = (
                storage.maximum_energy.set_frequency(self.parameters.timestep, False)
                .filter(item=local_index, inplace=False)
                .max()
            )
            if local_max_energy <= 0:
                cfg.logger.debug(f"Equipment {str(storage.name)} avoided, as its maximum_energy is 0")
                continue

            cfg.logger.debug(f"Equipment {str(storage.name)}")

            buy_submitted_volumes = DAOTimeseries(
                Timeseries.from_index(self.parameters.start_date, self.parameters.timestep, end_date, 0)
            )
            sell_submitted_volumes = DAOTimeseries(
                Timeseries.from_index(self.parameters.start_date, self.parameters.timestep, end_date, 0)
            )

            # if the stock of the equipment at start date is not defined, initiate it
            initial_stock = _initiate_stock(storage, self.parameters)

            # Determine offers times and quantities through an optimisation algorithm under a price forecast
            solver_options = SolverOptions(
                presolve=self.parameters.use_presolve,
                duality_gap=self.parameters.solver_duality_gap,
                time_limit=self.parameters.solver_timeout,
            )
            if storage.storage_type == StorageType.ELECTRIC_VEHICLE:
                Qv, Qa = _optimize_ev(storage, initial_stock, solver_options, self.parameters)
            else:
                Qv, Qa = _optimize_battery(storage, initial_stock, solver_options, self.parameters)

            # Determine sale and purchase prices
            Psale, Ppurchase = _price_calculation(storage, Qv, Qa, self.parameters)

            # Store Ppurchase as price reference in variable_cost, in the dataset.
            # Psale can then be deduced from Ppurchase, Charge and and Discharge efficiency
            if storage.variable_cost is None:
                storage.variable_cost = Timeseries.from_index(
                    self.parameters.start_date, self.parameters.timestep, end_date, 0
                )
            if Ppurchase != 0:
                for t in generate_datetimes(self.parameters.start_date, end_date, self.parameters.timestep):
                    storage.variable_cost.set_value(t, round(Ppurchase, 2))
            elif storage.discharge_efficiency != 0 and storage.charge_efficiency != 0:
                for t in generate_datetimes(self.parameters.start_date, end_date, self.parameters.timestep):
                    storage.variable_cost.set_value(
                        t, round(Psale * storage.discharge_efficiency * storage.charge_efficiency, 2)
                    )
            else:
                for t in generate_datetimes(self.parameters.start_date, end_date, self.parameters.timestep):
                    storage.variable_cost.set_value(t, round(Psale, 2))
                cfg.logger.warning(
                    f"ChargeEfficiency or DischargeEfficiency is null for equipment {storage.name}. "
                    "This is not supposed to be the case, as the default value for these is 1 and not 0"
                )

            # --- Formulate orders, possibly with associated coupling instances
            # First, orders that are included in a COMPLEMENT coupling
            daily_buy_volume = sum(buy_volume * self.parameters.timestep.total_hours() for buy_volume in Qa.values())
            if storage.storage_type == StorageType.ELECTRIC_VEHICLE and daily_buy_volume > 0:
                # Create the order coupling instance
                coupling_instance = OrderCouplingDAO(
                    name=f"COMPLEMENT_DA_{storage.name}_{bmo_name_datetime_to_str(self.parameters.execution_date)}",
                    coupling_type=CouplingType.COMPLEMENT,
                    complement_direction=ComplementDirection.EqualTo,
                )

                # Compute the ComplementEnergy according to the evolution DisplacementEnergy over the day,
                # if it is feasible given all orders generated for this equipment.
                # If not, the energy requirement is capped to the feasible limit
                energy_requirement = storage.displacement_energy.get_value(
                    self.parameters.penultimate_date
                ) - storage.displacement_energy.get_value(self.parameters.start_date - self.parameters.timestep)

                if energy_requirement > daily_buy_volume:
                    coupling_instance.complement_energy = daily_buy_volume
                else:
                    coupling_instance.complement_energy = energy_requirement

                for t in [i for i, e in Qa.items()]:
                    self.add_spot_order_with_coupling(OrderType.Buy, storage, t, Qa[t], Ppurchase, coupling_instance)
                    buy_submitted_volumes.set_or_add_value(t, Qa[t])
                for t in [i for i, e in Qv.items()]:
                    self.add_spot_order_with_coupling(OrderType.Sell, storage, t, Qv[t], Psale, coupling_instance)
                    sell_submitted_volumes.set_or_add_value(t, Qv[t])

                self.dataset.order_coupling.append(coupling_instance)

            # All other orders
            else:
                # Create a COMPLEMENT order coupling
                coupling_instance = OrderCouplingDAO(
                    name=f"COMPLEMENT_DA_{storage.name}_{bmo_name_datetime_to_str(self.parameters.execution_date)}",
                    coupling_type=CouplingType.COMPLEMENT,
                )

                for t in [i for i, e in Qa.items()]:
                    self.add_spot_order_with_coupling(OrderType.Buy, storage, t, Qa[t], Ppurchase, coupling_instance)
                    buy_submitted_volumes.set_or_add_value(t, Qa[t])
                for t in [i for i, e in Qv.items()]:
                    self.add_spot_order_with_coupling(OrderType.Sell, storage, t, Qv[t], Psale, coupling_instance)
                    sell_submitted_volumes.set_or_add_value(t, Qv[t])

                # Fill the COMPLEMENT order coupling
                coupling_instance.coupling_type = CouplingType.COMPLEMENT
                coupling_instance.complement_direction = ComplementDirection.EqualTo
                coupling_instance.complement_energy = buy_submitted_volumes.sum() - sell_submitted_volumes.sum()
                self.dataset.order_coupling.append(coupling_instance)

            if storage.da_buy_submitted_volume is None:
                storage.da_buy_submitted_volume = buy_submitted_volumes
            else:
                storage.da_buy_submitted_volume += buy_submitted_volumes

            if storage.da_sell_submitted_volume is None:
                storage.da_sell_submitted_volume = sell_submitted_volumes
            else:
                storage.da_sell_submitted_volume += sell_submitted_volumes

    def add_spot_order_with_coupling(
        self,
        order_type: OrderType,
        storage: StorageDAO,
        start_date: DateTime,
        qmax: float,
        price: float,
        coupling_instance: OrderCouplingDAO,
    ) -> None:
        """
        Add a spot order with a coupling instance to the model
        :param order_type: the order type
        :type order_type: OrderType
        :param storage: the storage object
        :type storage: StorageDAO
        :param start_date: the start date
        :type start_date: DateTime
        :param qmax: the maximum power
        :type qmax: float
        :param price: the price
        :type price: float
        :param coupling_instance: the coupling instance
        :type coupling_instance: OrderCouplingDAO
        :return: None
        """
        order = OrderDAO(
            name=f"storage_order_type_{order_type}_at_{bmo_name_datetime_to_str(start_date)}_for_unit_{storage.name}",
            equipment=storage,
            portfolio=storage.portfolio,
            market_area=storage.portfolio.market_area,
            execution_date=self.parameters.execution_date,
            start_date=start_date,
            end_date=start_date + self.parameters.timestep,
            order_type=order_type,
            product=Product.DayAhead,
            qmax=qmax,
            qmin=0.0,
            price=price,
        )
        self.dataset.order.append(order)
        coupling_instance.orders.append(order)
