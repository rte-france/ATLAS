"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements StorageOrderFormulator.
"""

from pendulum import DateTime

from atlas.enums import OrderType, StorageType
from atlas.modules.balancing_market_bsp_orders.input_objects.storage import BalancingStorage
from atlas.modules.balancing_market_bsp_orders.order_formulators.base import AbstractOrderFormulator
from atlas.modules.balancing_market_bsp_orders.parameters import BSPBalancingOrdersParameters
from atlas.objects.market.market_area import MarketArea
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling

# Temporary parameter limiting excessive balancing market activations.
# Should probably be moved to parameters after validation.
ALPHA_PRICE = 3


def compute_average_clearing_prices(market_area: MarketArea, local_time: DateTime) -> float:
    """
    Compute the average of all previous clearing prices on a given market area.

    Averages the day-ahead price, all available intraday clearing prices, and the
    RR activation price (when relevant), at the given local_time. Assumes the
    day-ahead market has always been simulated.

    :param market_area: The market area to compute the average price for
    :type market_area: MarketArea
    :param local_time: The datetime to evaluate the price at
    :type local_time: DateTime
    :return: The average clearing price, rounded to 2 decimal places
    :rtype: float
    """
    number_of_reference_prices = 1
    total_price = market_area.da_price.get_value(local_time)

    # TODO : the original rounds local_time down to the hour before matching against id_price
    # timeseries indexes. Kept as-is here, but worth re-checking this rounding behavior later.
    wanted_date = local_time.start_of("hour")

    if market_area.id_price is not None:
        for execution_date in market_area.id_price.index:
            id_price_timeseries = market_area.id_price.select(execution_date)
            if wanted_date in id_price_timeseries:
                total_price += id_price_timeseries.get_value(wanted_date)
                number_of_reference_prices += 1

    if market_area.rr_activation_price is not None and local_time in market_area.rr_activation_price:
        total_price += market_area.rr_activation_price.get_value(local_time)
        number_of_reference_prices += 1

    return round(total_price / number_of_reference_prices, 2)


def compute_daily_balancing_energy(equipment: BalancingStorage, parameters: BSPBalancingOrdersParameters) -> float:
    """
    Compute the total energy activated for balancing processes over the current day.

    Sums RR, mFRR, aFRR, FCR activated power, and specific activated power over the
    current day, then integrates at the market timestep.

    # TODO : the original prometheus implementation integrates at a fixed 5-minute
    # timestep regardless of the market timestep. Here we integrate at the market
    # timestep directly for simplicity; unclear whether this distinction matters.

    :param equipment: The storage equipment to compute daily balancing energy for
    :type equipment: BalancingStorage
    :param parameters: Module parameters providing temporal context
    :type parameters: BSPBalancingOrdersParameters
    :return: Total energy activated for balancing processes over the day, in MWh
    :rtype: float
    """
    execution_date = parameters.temporal.execution_date
    start = parameters.temporal.start_date
    timestep = parameters.temporal.timestep

    current_day_start = start.start_of("day")
    current_day_end = current_day_start.end_of("day")

    energy_timeframe_power = (
        equipment.rr_activated.slice(current_day_start, current_day_end)
        + equipment.mfrr_activated.slice(current_day_start, current_day_end)
        + equipment.afrr_activated.slice(current_day_start, current_day_end)
        + equipment.fcr_activated.slice(current_day_start, current_day_end)
        + equipment.specific_activated_power.get_forecast(execution_date, current_day_start, current_day_end)
    )

    return energy_timeframe_power.sum() * (timestep.total_seconds() / 3600)


class StorageOrderFormulator(AbstractOrderFormulator):
    """Formulates balancing orders for storage equipment.

    Upward orders (Sell): the unit discharges, increasing its output toward maximum_power.
    Downward orders (Buy): the unit charges, decreasing its output toward minimum_power.

    Available power:
        - Upward:   maximum_power - forecasted_power - upward_procured
        - Downward: forecasted_power - minimum_power - downward_procured

    The maximum_gradient constraint, when set, limits the available power based on
    the forecasted power evolution between the studied timestep and its neighbors.

    Storage level constraints limit the available power so that the equipment's stored
    energy stays within bounds over the storage_constraint_end_date horizon: upward
    orders are limited by the minimum stored energy reached over the horizon, downward
    orders by the maximum stored energy reached over the horizon.

    For PumpedHydraulicStorage equipment with a non-negligible transition_duration,
    orders that would change the pumping/turbining state are limited or excluded:
    only orders consistent with the current forecasted power direction are formulated.

    Order prices are the average of all previous market clearing prices on the
    equipment's market area, adjusted when the daily activated balancing energy
    exceeds storage_price_threshold.

    # TODO : equipment.rr_activated / mfrr_activated / afrr_activated / fcr_activated /
    # specific_activated_power must be added as non-Optional fields on BalancingStorage
    # (input_objects/storage.py), mirroring the pattern used for other required fields.
    """

    def __init__(
        self,
        equipment: BalancingStorage,
        time_index: list[DateTime],
        parameters: BSPBalancingOrdersParameters,
    ) -> None:
        super().__init__(equipment, time_index, parameters)
        self.equipment: BalancingStorage = equipment

    def formulate(self) -> tuple[list[Order], list[OrderCoupling]]:
        """
        Formulate upward and downward orders for the storage equipment.

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

        storage_constraint_end_date = self._compute_storage_constraint_end_date()

        orders: list[Order] = []

        for time in self.time_index:
            if not self.is_after_setup_delay(time):
                continue

            next_time = time.add(minutes=timestep_minutes)

            qmax_up = max(0.0, upward_available.get_value(time))
            qmax_down = max(0.0, downward_available.get_value(time))

            if self.equipment.maximum_gradient != 0:
                qmax_up, qmax_down = self._apply_gradient_constraint(forecasted_power, time, qmax_up, qmax_down)

            qmax_up, upward_valid = self._apply_upward_storage_level_constraint(qmax_up, storage_constraint_end_date)
            qmax_down, downward_valid = self._apply_downward_storage_level_constraint(
                qmax_down, storage_constraint_end_date
            )

            if self.equipment.storage_type == StorageType.PumpedHydraulicStorage:
                qmax_up, upward_valid = self._apply_phs_transition_constraint(
                    forecasted_power, time, qmax_up, upward_valid, is_upward=True
                )
                qmax_down, downward_valid = self._apply_phs_transition_constraint(
                    forecasted_power, time, qmax_down, downward_valid, is_upward=False
                )

            if qmax_up >= 1.0 and upward_valid:
                order_price = self._compute_order_price(time)
                order = self.build_order(
                    order_type=OrderType.Sell,
                    start=time,
                    end=next_time,
                    price=order_price,
                    qmin=0.0,
                    qmax=qmax_up,
                )
                if order is not None:
                    orders.append(order)

            if qmax_down >= 1.0 and downward_valid:
                order_price = self._compute_order_price(time)
                order = self.build_order(
                    order_type=OrderType.Buy,
                    start=time,
                    end=next_time,
                    price=order_price,
                    qmin=0.0,
                    qmax=qmax_down,
                )
                if order is not None:
                    orders.append(order)

        return orders, []

    def _compute_storage_constraint_end_date(self) -> DateTime:
        """
        Compute the end date of the period over which the stored energy adequacy is considered.

        Ensures that orders within the balancing time frame respect the stored energy
        constraint until the end of the next fixed market period (Intraday market if
        with_fixed_id_markets is True, Day Ahead otherwise).

        :return: The end date of the storage constraint horizon
        :rtype: DateTime
        """
        execution_date = self.parameters.temporal.execution_date

        if not self.parameters.conservative_stored_energy:
            return self.parameters.temporal.end_date.subtract(
                minutes=int(self.parameters.temporal.timestep.total_seconds() // 60)
            )

        if self.parameters.with_fixed_id_markets:
            if execution_date.hour < 10:
                return execution_date.set(hour=12, minute=0, second=0)
            return execution_date.start_of("day").add(days=1)

        if execution_date.hour < 12:
            return execution_date.start_of("day").add(days=1)
        return execution_date.start_of("day").add(days=2)

    def _apply_upward_storage_level_constraint(
        self,
        upward_available: float,
        storage_constraint_end_date: DateTime,
    ) -> tuple[float, bool]:
        """
        Apply the storage level constraint to the upward available power.

        Limits upward orders so that the equipment's stored energy never falls below
        minimum_state_of_charge * maximum_energy over the storage constraint horizon.
        If the stored energy is already at or below this minimum at any point in the
        horizon, no upward order can be formulated.

        :param upward_available: Upward available power before the storage level constraint
        :type upward_available: float
        :param storage_constraint_end_date: End date of the storage constraint horizon
        :type storage_constraint_end_date: DateTime
        :return: Tuple of (upward_available, is_valid) after the storage level constraint
        :rtype: tuple[float, bool]
        """
        execution_date = self.parameters.temporal.execution_date
        start = self.parameters.temporal.start_date
        timestep_minutes = int(self.parameters.temporal.timestep.total_seconds() // 60)
        time = self.parameters.temporal.start_date

        stored_energy = self.equipment.stored_energy.get_forecast(
            execution_date, start.subtract(minutes=timestep_minutes), storage_constraint_end_date
        )
        stored_energy_min = stored_energy.min() if len(stored_energy) > 0 else 0.0

        local_minimum_energy = self.equipment.minimum_state_of_charge.get_value(
            time
        ) * self.equipment.maximum_energy.get_value(time)

        if stored_energy_min <= local_minimum_energy:
            return 0.0, False

        timeframe_hours = (self.parameters.temporal.end_date - start).total_seconds() / 3600
        upward_available = min(
            upward_available,
            self.equipment.discharge_efficiency * (stored_energy_min - local_minimum_energy) / timeframe_hours,
        )
        return upward_available, True

    def _apply_downward_storage_level_constraint(
        self,
        downward_available: float,
        storage_constraint_end_date: DateTime,
    ) -> tuple[float, bool]:
        """
        Apply the storage level constraint to the downward available power.

        Limits downward orders so that the equipment's stored energy never exceeds
        maximum_energy over the storage constraint horizon. If the maximum stored energy
        already reaches maximum_energy at any point in the horizon, no downward order
        can be formulated.

        :param downward_available: Downward available power before the storage level constraint
        :type downward_available: float
        :param storage_constraint_end_date: End date of the storage constraint horizon
        :type storage_constraint_end_date: DateTime
        :return: Tuple of (downward_available, is_valid) after the storage level constraint
        :rtype: tuple[float, bool]
        """
        execution_date = self.parameters.temporal.execution_date
        start = self.parameters.temporal.start_date
        time = self.parameters.temporal.start_date

        stored_energy = self.equipment.stored_energy.get_forecast(execution_date, start, storage_constraint_end_date)

        if len(stored_energy) > 0:
            max_stored_energy = stored_energy.max()
        else:
            # This case should not occur, as balancing markets are meant to occur after at least one previous market
            max_stored_energy = self.equipment.maximum_energy.get_value(time) / 2

        current_storage_capacity = self.equipment.maximum_energy.get_value(time)

        if current_storage_capacity <= max_stored_energy:
            return 0.0, False

        timeframe_hours = (self.parameters.temporal.end_date - start).total_seconds() / 3600
        downward_available = min(
            downward_available,
            (current_storage_capacity - max_stored_energy) / (self.equipment.charge_efficiency * timeframe_hours),
        )
        return downward_available, True

    def _apply_phs_transition_constraint(
        self,
        forecasted_power,
        time: DateTime,
        available: float,
        is_valid: bool,
        is_upward: bool,
    ) -> tuple[float, bool]:
        """
        Apply the PumpedHydraulicStorage transition duration constraint.

        A PumpedHydraulicStorage equipment needs time to switch from pumping to
        turbining, or the other way around. If the equipment is scheduled in one of
        these states, it can't go into the other if the transition_duration constraint
        is not respected. Only orders that do not change the pumping/turbining state
        are formulated here.

        :param forecasted_power: Forecasted power timeseries over the balancing time frame
        :type forecasted_power: Timeseries
        :param time: The timestep being evaluated
        :type time: DateTime
        :param available: Available power before the PHS transition constraint
        :type available: float
        :param is_valid: Whether the order is still valid before this constraint
        :type is_valid: bool
        :param is_upward: True for the upward (discharge) direction, False for downward (charge)
        :type is_upward: bool
        :return: Tuple of (available, is_valid) after the PHS transition constraint
        :rtype: tuple[float, bool]
        """
        if not is_valid:
            return available, is_valid

        timestep_minutes = self.parameters.temporal.timestep.total_seconds() / 60
        transition_duration_minutes = self.equipment.transition_duration.total_seconds() / 60
        if round(transition_duration_minutes / timestep_minutes) < 1:
            return available, is_valid

        forecasted_power_value = forecasted_power.get_value(time)
        opposing_sign = forecasted_power_value < 0 if is_upward else forecasted_power_value > 0

        if opposing_sign:
            available = min(available, abs(forecasted_power_value))
        elif forecasted_power_value == 0:
            is_valid = False

        return available, is_valid

    def _compute_order_price(self, time: DateTime) -> float:
        """
        Compute the order price as the average clearing price, adjusted for excessive activations.

        Adds an adjustment to the price to limit excessive activations on balancing
        markets when the volume of activated reserves during the current day exceeds
        storage_price_threshold * average_maximum_energy.

        :param time: The timestep being evaluated
        :type time: DateTime
        :return: The adjusted order price
        :rtype: float
        """
        market_area = self.equipment.portfolio.market_area
        order_price = compute_average_clearing_prices(market_area, time)

        average_maximum_energy = sum(self.equipment.maximum_energy.get_value(t) for t in self.time_index) / len(
            self.time_index
        )

        balancing_energy_activated = compute_daily_balancing_energy(self.equipment, self.parameters)

        if abs(balancing_energy_activated) > self.parameters.storage_price_threshold * average_maximum_energy:
            order_price = order_price * (1 + ALPHA_PRICE * balancing_energy_activated / average_maximum_energy)

        return order_price
