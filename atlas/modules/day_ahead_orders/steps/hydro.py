"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import atlas.config as cfg
from atlas.common.optimal_dispatch.marginal_pricing import InterpolatedMarginalValue
from atlas.enums import ComplementDirection, CouplingType, OrderType, Product
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.input_objects.hydro import HydroDAO
from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
from atlas.modules.day_ahead_orders.input_objects.order_coupling import OrderCouplingDAO
from atlas.modules.day_ahead_orders.steps.abstract_step import AbstractBiddingStep
from atlas.modules.day_ahead_orders.steps.result import BiddingResult
from atlas.timing import generate_datetimes

if TYPE_CHECKING:
    from atlas.objects.equipment.hydro import FragmentData


class HydraulicBidding(AbstractBiddingStep):
    def formulate(self) -> BiddingResult:
        result = BiddingResult()

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
            fragments = equipment.fragment_data

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
                volumes = self._fragment_volumes(fragments, capacity)

                for category, volume in volumes.items():
                    if volume != 0:
                        bid_output = OrderDAO(
                            name=f"hydraulic_order_fragment_{str(category)}_at_{t.format('DD_MM_YYYY_HH_mm_ss')}_for_unit_{equipment.name}",
                            market_area=equipment.portfolio.market_area,
                            portfolio=equipment.portfolio,
                            equipment=equipment,
                            qmax=volume,
                            qmin=0,
                            product=Product.DayAhead,
                            order_type=OrderType.Sell,
                            is_agent_tso=False,
                            execution_date=self.parameters.temporal.execution_date,
                            start_date=t,  # type: ignore [arg-type]
                            end_date=t + self.parameters.temporal.timestep,  # type: ignore [arg-type]
                            price=fragments[category].price + marginal_value.value_at(t),
                        )

                        result.orders.append(bid_output)
                        coupling_orders.append(bid_output)

                        if t in submitted_volumes:
                            submitted_volumes.set_value(t, submitted_volumes.get_value(t) + volume)
                        else:
                            submitted_volumes.add_index(t, volume)

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

    def _fragment_volumes(self, fragments: dict[int, FragmentData], capacity: float) -> dict[int, float]:
        """Volume offered per fragment at *capacity*, dropping fragments too small to bid.

        Each fragment's nominal volume is its share of *capacity*. Fragments below
        ``hydraulic_minimal_fragment_size`` are discarded and their volume redistributed
        proportionally over the remaining fragments, so the offered total still equals
        *capacity*. If no fragment clears the threshold, the whole capacity is placed on
        the median fragment.
        """
        minimal_size = self.parameters.hydraulic_minimal_fragment_size
        volumes = {category: capacity * fragment.volume for category, fragment in fragments.items()}

        if sum(volume for volume in volumes.values() if volume < minimal_size) <= 0:
            return volumes

        normal_volumes = {category: volume for category, volume in volumes.items() if volume >= minimal_size}
        normal_capacity = sum(normal_volumes.values())
        if normal_capacity == 0:
            return {math.ceil(len(fragments) / 2): capacity}
        return {category: capacity * volume / normal_capacity for category, volume in normal_volumes.items()}

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
