"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements HydraulicOrderFormulator.
"""

from pendulum import DateTime

from atlas.enums import OrderType
from atlas.math.abstract_scenario_matrix import AbstractScenarioMatrix
from atlas.modules.balancing_market_bsp_orders.input_objects.hydro import BalancingHydro
from atlas.modules.balancing_market_bsp_orders.order_formulators.base import AbstractOrderFormulator
from atlas.modules.balancing_market_bsp_orders.parameters import BSPBalancingOrdersParameters
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling


def extract_mean_from_scenario(
    scenario_matrix: AbstractScenarioMatrix,
    index_input: float,
    time_input: DateTime,
) -> float:
    """
    Extract a linearly interpolated value from a ScenarioMatrix.

    Interpolates between the scenario index value preceding index_input and the one
    following it, at the given time_input. The scenario_matrix indexes are assumed to
    represent numeric values (e.g. storage levels) and are sorted by increasing value.
    If index_input falls outside the index range, it is clamped to the nearest bound.

    :param scenario_matrix: Matrix of timeseries indexed by numeric scenario values
    :type scenario_matrix: AbstractScenarioMatrix
    :param index_input: The numeric value to interpolate between scenario indexes
    :type index_input: float
    :param time_input: The datetime at which to read the interpolated value
    :type time_input: DateTime
    :return: The interpolated value, or 0.0 if the matrix has no indexes
    :rtype: float
    """
    # Map numeric value -> original column name, to avoid reformatting mismatches
    index_by_value = {float(index_name): index_name for index_name in scenario_matrix.index}
    scenario_values = sorted(index_by_value)

    if not scenario_values:
        return 0.0

    if index_input <= scenario_values[0]:
        preceding_value_key = following_value_key = scenario_values[0]
    elif index_input >= scenario_values[-1]:
        preceding_value_key = following_value_key = scenario_values[-1]
    else:
        preceding_value_key = scenario_values[0]
        following_value_key = scenario_values[-1]
        for scenario_value in scenario_values:
            if scenario_value == index_input:
                preceding_value_key = following_value_key = scenario_value
                break
            if scenario_value < index_input:
                preceding_value_key = scenario_value
            else:
                following_value_key = scenario_value
                break

    preceding_value = scenario_matrix.select(index_by_value[preceding_value_key]).get_value(time_input)

    if preceding_value_key == following_value_key:
        return preceding_value

    following_value = scenario_matrix.select(index_by_value[following_value_key]).get_value(time_input)

    return preceding_value + (following_value - preceding_value) * (index_input - preceding_value_key) / (
        following_value_key - preceding_value_key
    )


class HydraulicOrderFormulator(AbstractOrderFormulator):
    """Formulates balancing orders for hydraulic equipment.

    Upward orders (Sell): the unit increases its output toward maximum_power.
    Downward orders (Buy): the unit decreases its output toward minimum_power.

    Available power:
        - Upward:   maximum_power - forecasted_power - upward_procured
        - Downward: forecasted_power - minimum_power - downward_procured

    The maximum_gradient constraint, when set, limits the available power based on
    the forecasted power evolution between the studied timestep and its neighbors.
    """

    def __init__(
        self,
        equipment: BalancingHydro,
        time_index: list[DateTime],
        parameters: BSPBalancingOrdersParameters,
    ) -> None:
        super().__init__(equipment, time_index, parameters)
        self.equipment: BalancingHydro = equipment

    def formulate(self) -> tuple[list[Order], list[OrderCoupling]]:
        """
        Formulate upward and downward orders for the hydraulic equipment.

        :return: Tuple of formulated orders and an empty coupling list
        :rtype: tuple[list[Order], list[OrderCoupling]]
        """
        start = self.parameters.temporal.start_date
        end = self.parameters.temporal.end_date
        execution_date = self.parameters.temporal.execution_date
        timestep_minutes = int(self.parameters.temporal.timestep.total_seconds() // 60)

        forecasted_power = self.equipment.power.get_forecast(execution_date, start, end)
        max_power = self.equipment.maximum_power
        min_power = self.equipment.minimum_power

        upward_procured, downward_procured = self.compute_procured_power(
            execution_date, start, end, self.parameters.product_type
        )

        upward_available = max_power - forecasted_power - upward_procured
        downward_available = forecasted_power - min_power - downward_procured

        orders: list[Order] = []

        for time in self.time_index:
            if not self.is_after_setup_delay(time):
                continue

            next_time = time.add(minutes=timestep_minutes)

            qmax_up = max(0.0, upward_available.get_value(time))
            qmax_down = max(0.0, downward_available.get_value(time))

            if self.equipment.maximum_gradient != 0:
                qmax_up, qmax_down = self._apply_gradient_constraint(forecasted_power, time, qmax_up, qmax_down)

            if self.equipment.has_daily_energy_constraint:
                qmax_up = self._apply_maximum_daily_energy_constraint(qmax_up)
                qmax_down = self._apply_minimum_daily_energy_constraint(qmax_down)

            water_value = extract_mean_from_scenario(
                self.equipment.storage_marginal_value,
                self.equipment.stored_energy.get_forecast(
                    self.parameters.temporal.execution_date, time, time
                ).get_value(time),
                time,
            )

            if qmax_up >= 1.0:
                orders.extend(self._build_upward_fragment_orders(time, next_time, qmax_up, water_value))

            # TODO: Constraint not present in prometheus : Check with validation
            if qmax_down >= 1.0:
                orders.extend(self._build_downward_fragment_orders(time, next_time, qmax_down, water_value))

        return orders, []

    def _apply_gradient_constraint(
        self,
        forecasted_power,
        time: DateTime,
        upward_available: float,
        downward_available: float,
    ) -> tuple[float, float]:
        """
        Apply the maximum_gradient constraint to the available upward and downward power at a given timestep.

        Limits the available power based on the forecasted power evolution between the
        studied timestep and its previous/next neighbor, so that the equipment's power
        trajectory never exceeds maximum_gradient per timestep.

        :param forecasted_power: Forecasted power timeseries over the balancing time frame
        :type forecasted_power: Timeseries
        :param time: The timestep being evaluated
        :type time: DateTime
        :param upward_available: Upward available power before the gradient constraint
        :type upward_available: float
        :param downward_available: Downward available power before the gradient constraint
        :type downward_available: float
        :return: Tuple of (upward_available, downward_available) after the gradient constraint
        :rtype: tuple[float, float]
        """
        timestep = self.parameters.temporal.timestep
        execution_date = self.parameters.temporal.execution_date
        # TODO : 2 multiplication in prometheus : Check with validation
        max_grad = self.equipment.maximum_gradient * (timestep.total_seconds() / 60)

        previous_time = time.subtract(minutes=int(timestep.total_seconds() // 60))
        next_time = time.add(minutes=int(timestep.total_seconds() // 60))

        try:
            previous_forecasted_power = self.equipment.power.get_forecast(
                execution_date, previous_time, previous_time
            ).get_value(previous_time)
            if previous_forecasted_power is None:
                previous_forecasted_power = 0.0
        except (KeyError, ValueError):
            previous_forecasted_power = 0.0

        try:
            next_forecasted_power = self.equipment.power.get_forecast(execution_date, next_time, next_time).get_value(
                next_time
            )
            if next_forecasted_power is None:
                next_forecasted_power = 0.0
        except (KeyError, ValueError):
            next_forecasted_power = 0.0

        if previous_forecasted_power > 0:
            previous_upward_evolution = max(forecasted_power.get_value(time) - previous_forecasted_power, 0)
            previous_downward_evolution = max(previous_forecasted_power - forecasted_power.get_value(time), 0)
        else:
            previous_upward_evolution = 0.0
            previous_downward_evolution = 0.0

        if next_forecasted_power > 0:
            next_upward_evolution = max(next_forecasted_power - forecasted_power.get_value(time), 0)
            next_downward_evolution = max(forecasted_power.get_value(time) - next_forecasted_power, 0)
        else:
            next_upward_evolution = 0.0
            next_downward_evolution = 0.0

        upward_available = min(
            upward_available,
            max_grad - previous_upward_evolution,
            max_grad - next_downward_evolution,
        )
        downward_available = min(
            downward_available,
            max_grad - previous_downward_evolution,
            max_grad - next_upward_evolution,
        )

        return max(0.0, upward_available), max(0.0, downward_available)

    def _apply_maximum_daily_energy_constraint(self, upward_available: float) -> float:
        """
        Apply the maximum_daily_energy constraint to the upward available power.

        Reduces the upward order volume so that the equipment's total energy produced
        over the day does not exceed maximum_daily_energy. If the daily energy is
        already at or above the maximum, no upward order can be formulated.

        :param upward_available: Upward available power before the daily energy constraint
        :type upward_available: float
        :return: upward_available after the daily energy constraint
        :rtype: float
        """
        start = self.parameters.temporal.start_date
        local_maximum_daily_energy = self.equipment.maximum_daily_energy.get_value(start)
        total_daily_energy_produced = self._compute_daily_energy()
        remaining_margin = local_maximum_daily_energy - total_daily_energy_produced

        if remaining_margin <= 0:
            return 0.0

        timeframe_hours = (self.parameters.temporal.end_date - start).total_seconds() / 3600
        upward_available = min(upward_available, remaining_margin / timeframe_hours)
        return upward_available

    def _apply_minimum_daily_energy_constraint(self, downward_available: float) -> float:
        """
        Apply the minimum_daily_energy constraint to the downward available power.

        Reduces the downward order volume so that the equipment's total energy produced
        over the day does not fall below minimum_daily_energy. If the daily energy is
        already at or below the minimum, no downward order can be formulated.

        :param downward_available: Downward available power before the daily energy constraint
        :type downward_available: float
        :return: downward_available after the daily energy constraint
        :rtype: float
        """
        start = self.parameters.temporal.start_date
        local_minimum_daily_energy = self.equipment.minimum_daily_energy.get_value(start)
        total_daily_energy_produced = self._compute_daily_energy()
        remaining_margin = total_daily_energy_produced - local_minimum_daily_energy

        if remaining_margin <= 0:
            return 0.0

        timeframe_hours = (self.parameters.temporal.end_date - start).total_seconds() / 3600
        downward_available = min(downward_available, remaining_margin / timeframe_hours)
        return downward_available

    def _compute_daily_energy(self) -> float:
        """
        Compute the total energy produced by the equipment over the current day.

        # TODO : the original prometheus implementation integrates at a fixed 5-minute

        :return: Total energy produced over the day, in MWh
        :rtype: float
        """
        execution_date = self.parameters.temporal.execution_date
        start = self.parameters.temporal.start_date
        timestep = self.parameters.temporal.timestep

        current_day_start = start.start_of("day")
        current_day_end = current_day_start.end_of("day")

        daily_power = self.equipment.power.get_forecast(execution_date, current_day_start, current_day_end)
        # timestep may not be needed : use frequency of matrix if 15 -> divide by 4, if 30 divide by 2
        return daily_power.sum() * (timestep.total_seconds() / 3600)

    def _build_upward_fragment_orders(
        self,
        time: DateTime,
        next_time: DateTime,
        order_qmax: float,
        water_value: float,
    ) -> list[Order]:
        """
        Build upward Sell orders split into price/volume fragments.

        :param time: Order start datetime
        :type time: DateTime
        :param next_time: Order end datetime
        :type next_time: DateTime
        :param order_qmax: Total upward available power, after all constraints
        :type order_qmax: float
        :param water_value: Marginal water value extracted from the storage scenario matrix
        :type water_value: float
        :return: List of formulated Sell orders, one per relevant fragment
        :rtype: list[Order]
        """
        max_power_value = self.equipment.maximum_power.get_value(time)

        hydro_volumes = []
        hydro_sum = 0.0
        for local_volume in self.equipment.fragment_volumes:
            hydro_volumes.append(local_volume * max_power_value + hydro_sum)
            hydro_sum += local_volume * max_power_value

        local_power = self.equipment.power.get_forecast(self.parameters.temporal.execution_date, time, next_time)
        max_power_output = local_power.max() if len(local_power) > 0 else 0.0

        fragment_qmax: dict[int, float] = {}
        qmax_sum = 0.0
        for fragment_index, local_volume in enumerate(hydro_volumes):
            if local_volume < max_power_output:
                continue

            fragment_qmax[fragment_index] = local_volume - (max_power_output + qmax_sum)
            qmax_sum += fragment_qmax[fragment_index]

            if qmax_sum > round(order_qmax):
                fragment_qmax[fragment_index] -= qmax_sum - round(order_qmax)
                break

        orders: list[Order] = []
        for fragment_index, fragment_qmax_value in fragment_qmax.items():
            order = self.build_order(
                order_type=OrderType.Sell,
                start=time,
                end=next_time,
                price=water_value + self.equipment.fragment_prices[fragment_index],
                qmin=0.0,
                qmax=fragment_qmax_value,
                suffix=f"_frag_{fragment_index}",
            )
            if order is not None:
                orders.append(order)

        return orders

    def _build_downward_fragment_orders(
        self,
        time: DateTime,
        next_time: DateTime,
        order_qmax: float,
        water_value: float,
    ) -> list[Order]:
        """
        Build downward Buy orders split into price/volume fragments.

        :param time: Order start datetime
        :type time: DateTime
        :param next_time: Order end datetime
        :type next_time: DateTime
        :param order_qmax: Total downward available power, after all constraints
        :type order_qmax: float
        :param water_value: Marginal water value extracted from the storage scenario matrix
        :type water_value: float
        :return: List of formulated Buy orders, one per relevant fragment
        :rtype: list[Order]
        """
        max_power_value = self.equipment.maximum_power.get_value(time)

        down_fragment_prices = list(self.equipment.fragment_prices)
        down_fragment_prices.append(down_fragment_prices[-1])

        down_fragment_volumes = list(self.equipment.fragment_volumes)
        down_fragment_volumes.insert(0, 0.0)

        hydro_volumes = []
        hydro_sum = 0.0
        for local_volume in down_fragment_volumes:
            hydro_volumes.append(local_volume * max_power_value + hydro_sum)
            hydro_sum += local_volume * max_power_value

        local_power = self.equipment.power.get_forecast(self.parameters.temporal.execution_date, time, next_time)
        min_power_output = local_power.min() if len(local_power) > 0 else 0.0

        fragment_qmax: dict[int, float] = {}
        qmax_sum = 0.0
        for reversed_index, local_volume in enumerate(reversed(hydro_volumes)):
            # TODO: will there be issue with '- reversed_index' ?
            fragment_index = len(self.equipment.fragment_volumes) - reversed_index
            if local_volume > min_power_output:
                continue

            fragment_qmax[fragment_index] = min_power_output - local_volume - qmax_sum
            qmax_sum += fragment_qmax[fragment_index]

            if qmax_sum > round(order_qmax):
                fragment_qmax[fragment_index] -= qmax_sum - round(order_qmax)
                break

        orders: list[Order] = []
        for fragment_index, fragment_qmax_value in fragment_qmax.items():
            order = self.build_order(
                order_type=OrderType.Buy,
                start=time,
                end=next_time,
                price=water_value + down_fragment_prices[fragment_index],
                qmin=0.0,
                qmax=fragment_qmax_value,
                suffix=f"_frag_{fragment_index}",
            )
            if order is not None:
                orders.append(order)

        return orders
