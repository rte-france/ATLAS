"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import math

import atlas.config as cfg
from atlas.common.optimal_dispatch.marginal_pricing import InterpolatedMarginalValue
from atlas.enums import ComplementDirection, CouplingType, OrderType, Product
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.input_objects.hydro import HydroDAO
from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
from atlas.modules.day_ahead_orders.input_objects.order_coupling import OrderCouplingDAO
from atlas.modules.day_ahead_orders.steps.abstract_step import AbstractOrderStep, StepResult
from atlas.timing import generate_datetimes


class HydraulicStep(AbstractOrderStep):
    def formulate(self) -> StepResult:
        result = StepResult()

        hydraulic_units = [unit for unit in self.dataset.hydro if len(unit.storage_marginal_value.index) > 0]
        hydraulic_empty = [unit for unit in self.dataset.hydro if len(unit.storage_marginal_value.index) == 0]
        for equipment in hydraulic_empty:
            cfg.logger.warning(
                f"There are no water values for instance {equipment.name}. This instance will be ignored in the order formulation."
            )
        local_timewindow = generate_datetimes(
            self.parameters.temporal.start_date,
            self.parameters.penultimate_date,
            self.parameters.temporal.timestep,
        )

        for equipment in hydraulic_units:
            delta_wu: dict[float, tuple[float, float]] = {}
            for category in range(len(equipment.fragment_volumes)):
                delta_wu[category] = (equipment.fragment_volumes[category], equipment.fragment_prices[category])

            sell_submitted_volume = Timeseries.from_index(
                self.parameters.temporal.start_date,
                self.parameters.temporal.timestep,
                self.parameters.penultimate_date,
                0,
            )

            local_max_energy = equipment.maximum_energy.filter(item=local_timewindow, inplace=False).max()
            if local_max_energy <= 0:
                cfg.logger.debug(f"Equipment {str(equipment.name)} avoided, as its maximum_energy is 0")
                continue

            energy_level = self._get_current_energy_level(equipment)
            marginal_value = InterpolatedMarginalValue.at_level(equipment.storage_marginal_value, energy_level)
            minimum_energy = equipment.minimum_energy.slice(
                self.parameters.temporal.start_date, self.parameters.temporal.end_date, "both", False
            )

            if len(minimum_energy) > 1:
                complement_energy = -(energy_level - minimum_energy.min())
            else:
                complement_energy = -(
                    energy_level - equipment.minimum_energy.get_value(self.parameters.temporal.start_date)
                )

            coupling_orders = []
            for t in self.orders_time:
                capacity = equipment.maximum_power.get_value(t)
                volumes = {key: capacity * v[0] for key, v in delta_wu.items()}

                normal_volumes = {
                    key: v for key, v in volumes.items() if v >= self.parameters.hydraulic_minimal_fragment_size
                }
                minor_volumes = {
                    key: v for key, v in volumes.items() if v < self.parameters.hydraulic_minimal_fragment_size
                }
                if sum(minor_volumes.values()) > 0:
                    reduced_capacity = sum(normal_volumes.values())
                    if reduced_capacity != 0:
                        volumes = {key: capacity * v / reduced_capacity for (key, v) in normal_volumes.items()}
                    else:
                        volumes = {math.ceil(len(equipment.fragment_prices) / 2): capacity}

                for k, v in volumes.items():
                    if v != 0:
                        bid_output = OrderDAO(
                            name=f"hydraulic_order_fragment_{str(k)}_at_{t.format('DD_MM_YYYY_HH_mm_ss')}_for_unit_{equipment.name}",
                            market_area=equipment.portfolio.market_area,
                            portfolio=equipment.portfolio,
                            equipment=equipment,
                            qmax=v,
                            qmin=0,
                            product=Product.DayAhead,
                            order_type=OrderType.Sell,
                            is_agent_tso=False,
                            execution_date=self.parameters.temporal.execution_date,
                            start_date=t,  # type: ignore [arg-type]
                            end_date=t + self.parameters.temporal.timestep,  # type: ignore [arg-type]
                            price=delta_wu[k][1] + marginal_value.value_at(t),
                        )

                        result.orders.append(bid_output)
                        coupling_orders.append(bid_output)

                        if t in sell_submitted_volume:
                            sell_submitted_volume.set_value(t, sell_submitted_volume.get_value(t) + v)
                        else:
                            sell_submitted_volume.add_index(t, v)

            result.order_couplings.append(
                OrderCouplingDAO(
                    name=f"complement_{str(equipment.name)}_{self.parameters.temporal.execution_date.format('DD_MM_YYYY_HH_mm_ss')}",
                    coupling_type=CouplingType.COMPLEMENT,
                    complement_direction=ComplementDirection.GreaterThan,
                    complement_energy=complement_energy,
                    orders=coupling_orders,  # type: ignore [arg-type]
                )
            )
            if equipment.da_sell_submitted_volume is None:
                equipment.da_sell_submitted_volume = sell_submitted_volume
            else:
                equipment.da_sell_submitted_volume = equipment.da_sell_submitted_volume.add_on_union(
                    sell_submitted_volume, inplace=False
                )

        return result

    def _get_current_energy_level(self, equipment: HydroDAO) -> float:
        if equipment.stored_energy is not None:
            energy_forecast = equipment.stored_energy.get_forecast(
                self.parameters.temporal.execution_date,
                self.parameters.temporal.start_date.subtract(days=1),
                self.parameters.temporal.start_date - self.parameters.temporal.timestep,
            )
            if self.parameters.temporal.start_date - self.parameters.temporal.timestep in energy_forecast:
                return energy_forecast.get_value(
                    self.parameters.temporal.start_date - self.parameters.temporal.timestep
                )
        return equipment.initial_level.get_value(self.parameters.temporal.start_date)
