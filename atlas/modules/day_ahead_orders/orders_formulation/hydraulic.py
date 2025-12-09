"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import math

import pendulum
from pydantic_extra_types.pendulum_dt import DateTime

import atlas.config as cfg
from atlas import Order, OrderCoupling, Timeseries
from atlas.enum import ComplementDirection, CouplingType, OrderType, Product
from atlas.modules.day_ahead_orders.dao_input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.dao_parameters import DayAheadOrdersParameters
from atlas.timing import generate_datetimes


class Hydraulic:
    @staticmethod
    def formulate_hydraulic_orders(
        dataset: DayAheadOrdersInputDataset, orders_time: list[DateTime], parameters: DayAheadOrdersParameters
    ) -> None:
        """
        This function formulates the hydraulic reservoir offers.

         Arguments:
        - `dataset`: a dataset
        - `orders_time`: a list of dates at which orders must be formulated.
        - `parameters` a named tuple of parameters, containing the common parameters.
        """

        # Keep only the hydraulic reservoir for which water values have been computed.
        hydraulic_units = [unit for unit in dataset.hydro if len(unit.storage_marginal_value) > 0]

        hydraulic_empty = [unit for unit in dataset.hydro if len(unit.storage_marginal_value) == 0]
        for equipment in hydraulic_empty:
            msg = f"There are no water values for instance {equipment.name}. This instance will be ignored in the calculation."
            cfg.logger.warning(msg)

        # Loop over the market players first.
        for equipment in hydraulic_units:
            # Retrieve volumes and prices of fragments
            delta_wu: dict[float, float] = {}
            for category in range(len(equipment.fragment_volumes)):
                delta_wu[category] = (equipment.fragment_volumes[category], equipment.fragment_prices[category])

            # Avoid equipments that have a MaximumEnergy of 0 (meaning that they are offline)
            end_date = parameters.penultimate_date
            local_index = generate_datetimes(
                parameters.start_date,
                end_date,
                parameters.time_step,
            )
            submitted_volumes = Timeseries.from_index(parameters.start_date, parameters.time_step, end_date, 0)

            local_max_energy = (
                equipment.maximum_energy.set_frequency(parameters.time_step, False)
                .filter(item=local_index, inplace=False)
                .max()
            )
            if local_max_energy <= 0:
                if parameters.verbose:
                    cfg.logger.debug(f"Equipment {str(equipment.name)} avoided, as its maximum_energy is 0")
                continue

            # FC: Assumption for the identification of the "initial" level, see the storage formulation for more details
            if equipment.stored_energy is not None:
                energy_forecast = equipment.stored_energy.get_forecast(
                    parameters.execution_date,
                    parameters.start_date.subtract(days=1),
                    parameters.start_date - parameters.time_step,
                )
                if len(energy_forecast) > 0:
                    energy_level = energy_forecast.get_value(parameters.start_date - parameters.time_step)
                else:
                    energy_level = equipment.initial_level.get_value(parameters.start_date)
            else:
                energy_level = equipment.initial_level.get_value(parameters.start_date)

            xmin = filter(lambda x: int(x) <= energy_level, equipment.storage_marginal_value.index)
            xmax = filter(lambda x: int(x) > energy_level, equipment.storage_marginal_value.index)

            if xmin:
                xpmin = max(xmin, key=lambda x: int(x))
                level_inf = equipment.storage_marginal_value.select(xpmin).upsample(
                    frequency=pendulum.Duration(hours=1)
                )
            if xmax:
                xpmax = min(xmax, key=lambda x: int(x))
                level_sup = equipment.storage_marginal_value.select(xpmax).upsample(
                    frequency=pendulum.Duration(hours=1)
                )
            if xmin and xmax:
                weight_inf = (int(xpmax) - energy_level) / (int(xpmax) - int(xpmin))
                weight_sup = (energy_level - int(xpmin)) / (int(xpmax) - int(xpmin))

            # Create a COMPLEMENT coupling between all orders of the day to comply with MinimumEnergy constraints
            coupling_instance = OrderCoupling(
                name=f"COMPLEMENT_{str(equipment.name)}_{parameters.execution_date}",
                orders=[],
                coupling_type=CouplingType.COMPLEMENT,
                complement_direction=ComplementDirection.GreaterThan,
            )

            if len(equipment.minimum_energy.slice(parameters.start_date, parameters.end_date, "both", False)) > 0:
                coupling_instance.complement_energy = -(
                    energy_level
                    - equipment.minimum_energy.slice(parameters.start_date, parameters.end_date, "both", False).min()
                )
            else:
                coupling_instance.complement_energy = -(
                    energy_level - equipment.minimum_energy.get_value(parameters.start_date)
                )

            # Now we loop over the time stamps for which we want an offer to be made.
            # We formulate as many offers as there are time stamps in orders_time.
            for t in orders_time:
                # Compute the actual volumes of fragments, according to MaximumPower
                # If the unit would be able to empty its entire reservoir within one day,
                # the sum of fragments volume is limited to avoid this situation.

                capacity = equipment.maximum_power.get_value(t)
                volumes = {key: capacity * v[0] for key, v in delta_wu.items()}

                normal_volumes = {
                    key: v for key, v in volumes.items() if v >= parameters.hydraulic_minimal_fragment_size
                }
                minor_volumes = {key: v for key, v in volumes.items() if v < parameters.hydraulic_minimal_fragment_size}
                if sum(minor_volumes.values()) > 0:
                    reduced_capacity = sum(normal_volumes.values())
                    if reduced_capacity != 0:
                        volumes = {key: capacity * v / reduced_capacity for (key, v) in normal_volumes.items()}
                    # Specific case occuring when the total capacity is small
                    # If no previous fragments is greater than vuThreshold, formulate a single order,
                    # associated with the price spread of the middle fragment
                    else:
                        volumes = {math.ceil(len(equipment.fragment_prices) / 2): capacity}

                # create an offer for each element in volumes
                for k, v in volumes.items():
                    # Do not formulate empty orders
                    if v != 0:
                        # Assign a unique name.
                        bid_name = f"hydraulic_order_fragment_{str(k)}_at_{t}_for_unit_{equipment.name}"

                        # Initialize the order object
                        bid_output = Order(
                            name=bid_name,
                            market_area=equipment.portfolio.market_area,
                            portfolio=equipment.portfolio,
                            equipment=equipment,
                            qmax=v,
                            qmin=0,
                            product=Product.DayAhead,
                            order_type=OrderType.Sell,
                            is_agent_tso=False,
                            execution_date=str(parameters.execution_date),
                            start_date=str(t),
                            end_date=str(t + parameters.time_step),
                        )
                        if not xmin:
                            bid_output.price = level_sup.get_value(t) + delta_wu[k][1]
                        elif not xmax:
                            bid_output.price = level_inf.get_value(t) + delta_wu[k][1]
                        else:
                            pmin = level_inf.get_value(t)
                            pmax = level_sup.get_value(t)
                            bid_output.price = weight_inf * pmin + weight_sup * pmax + delta_wu[k][1]

                        coupling_instance.orders.append(bid_output)

                        submitted_volumes.add_value_at(t, bid_output.qmax)

            dataset.order_coupling.append(coupling_instance)
            if equipment.da_sell_submitted_volume is None:
                equipment.da_sell_submitted_volume = submitted_volumes
            else:
                equipment.da_sell_submitted_volume += submitted_volumes
