"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import math

from pendulum import DateTime

import atlas.config as cfg
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

            submitted_volumes = Timeseries.from_index(
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
            marginal_weights = self._calculate_marginal_weights(equipment, energy_level)
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
                            name=f"hydraulic_order_fragment_{str(k)}_at_{t.format('DD_MM_YYYY_HH_mm_ss')}_for_unit_{equipment.name}_exec_{self.parameters.temporal.execution_date.hour}",
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
                            price=self._calculate_fragment_price(delta_wu[k][1], marginal_weights, t),
                        )

                        result.orders.append(bid_output)
                        coupling_orders.append(bid_output)

                        if t in submitted_volumes:
                            submitted_volumes.set_value(t, submitted_volumes.get_value(t) + v)
                        else:
                            submitted_volumes.add_index(t, v)

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
                equipment.da_sell_submitted_volume = submitted_volumes
            else:
                equipment.da_sell_submitted_volume += submitted_volumes

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

    def _calculate_marginal_weights(self, equipment, energy_level: float) -> dict:
        storage_indices = equipment.storage_marginal_value.index

        x_min_candidates = [x for x in storage_indices if int(x) <= energy_level]
        x_max_candidates = [x for x in storage_indices if int(x) > energy_level]

        weights = {
            "has_min": bool(x_min_candidates),
            "has_max": bool(x_max_candidates),
            "weight_inf": 0.0,
            "weight_sup": 0.0,
            "level_inf": None,
            "level_sup": None,
        }

        if x_min_candidates:
            xp_min = max(x_min_candidates, key=lambda x: int(x))
            weights["level_inf"] = equipment.storage_marginal_value.select(xp_min)

        if x_max_candidates:
            xp_max = min(x_max_candidates, key=lambda x: int(x))
            weights["level_sup"] = equipment.storage_marginal_value.select(xp_max)

        if weights["has_min"] and weights["has_max"]:
            range_diff = int(xp_max) - int(xp_min)
            weights["weight_inf"] = (int(xp_max) - energy_level) / range_diff
            weights["weight_sup"] = (energy_level - int(xp_min)) / range_diff

        return weights

    def _calculate_fragment_price(self, fragment_price: float, marginal_weights: dict, time: DateTime) -> float:
        if not marginal_weights["has_min"] and marginal_weights["has_max"]:
            marginal_adjustment = marginal_weights["level_sup"].get_value(time)
        elif marginal_weights["has_min"] and not marginal_weights["has_max"]:
            marginal_adjustment = marginal_weights["level_inf"].get_value(time)
        elif marginal_weights["has_min"] and marginal_weights["has_max"]:
            p_min = marginal_weights["level_inf"].get_value(time)
            p_max = marginal_weights["level_sup"].get_value(time)
            marginal_adjustment = marginal_weights["weight_inf"] * p_min + marginal_weights["weight_sup"] * p_max
        else:
            marginal_adjustment = 0.0

        return fragment_price + marginal_adjustment
