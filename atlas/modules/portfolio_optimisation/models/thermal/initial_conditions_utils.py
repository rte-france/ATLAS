"""
Utility functions for thermal unit initial conditions.

This module provides common day zero initialization logic shared across
all thermal model combinations to reduce code duplication.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pendulum import DateTime

from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.models.thermal.thermal import ThermalPO


def initialize_day_zero_core(
    obj: ThermalPO,
    time: DateTime,
) -> None:
    """
    Initialize core day zero state variables common to ALL combinations.

    All thermal units start in OFF state with:
    - OFF state = 1
    - Turned on/off transitions = 0
    - Power level = 0

    :param obj: The thermal unit to initialize
    :type obj: ThermalPO
    :param time: The current time step
    :type time: DateTime
    """

    obj.off_var.set_extended(time, 1)
    obj.turned_on.set_extended(time, 0)
    obj.turned_off.set_extended(time, 0)
    obj.power_level_var.set_extended(time, 0)


def initialize_day_zero_on_states(
    obj: ThermalPO,
    time: DateTime,
) -> None:
    """
    Initialize ON_up and ON_down state variables for day zero.

    For T_stable = 0

    :param obj: The thermal unit to initialize
    :type obj: ThermalPO
    :param time: The current time step
    :type time: DateTime
    """

    obj.on_up_var.set_extended(time, 0)
    obj.on_down_var.set_extended(time, 0)


def initialize_day_zero_gradient_vars(
    obj: ThermalPO,
    time: DateTime,
) -> None:
    """
    Initialize gradient auxiliary variables for day zero.

    T_stable >= 1.

    :param obj: The thermal unit to initialize
    :type obj: ThermalPO
    :param time: The current time step
    :type time: DateTime
    """
    obj.up_grad_var.set_extended(time, 0)
    obj.down_grad_var.set_extended(time, 0)
    obj.aux_up_grad_var.set_extended(time, 0)
    obj.aux_down_grad_var.set_extended(time, 0)


def initialize_day_zero_stable_vars(
    obj: ThermalPO,
    time: DateTime,
) -> None:
    """
    Initialize stable state variables for day zero.

    T_stable >= 1. For stable timeframe.

    :param obj: The thermal unit to initialize
    :type obj: ThermalPO
    :param time: The current time step
    :type time: DateTime
    """

    obj.on_flat_var.set_extended(time, 0)
    obj.on_up_var.set_extended(time, 0)
    obj.on_down_var.set_extended(time, 0)

    obj.stable_var.set_extended(time, 0)
    obj.entered_up_var.set_extended(time, 0)
    obj.entered_down_var.set_extended(time, 0)


def initialize_gradient_initial_conditions(
    obj: ThermalPO,
    parameters: PortfolioOptimisationParameters,
) -> None:
    """
    Initialize gradient variables based on historical power data.

    For T_stable >= 1.

    :param obj: The thermal unit to initialize
    :type obj: ThermalPO
    :param parameters: Portfolio optimization parameters
    :type parameters: PortfolioOptimisationParameters
    :return: None
    :rtype: None
    """
    start_date_minus_one = parameters.date.start_date - parameters.date.timestep
    start_date_minus_two = parameters.date.start_date - 2 * parameters.date.timestep

    power_minus_one = obj.power_level_var.get_value(start_date_minus_one)
    power_minus_two = obj.power_level_var.get_value(start_date_minus_two)

    power_diff = power_minus_one - power_minus_two

    obj.up_grad_var.set_extended(
        start_date_minus_one,
        power_diff * obj.on_up_var.get_value(start_date_minus_one) * obj.on_up_var.get_value(start_date_minus_two),
    )

    obj.down_grad_var.set_extended(
        start_date_minus_one,
        power_diff * obj.on_down_var.get_value(start_date_minus_one) * obj.on_down_var.get_value(start_date_minus_two),
    )


def initialize_flat_down_stop_initial_conditions(
    obj: ThermalPO,
    time: DateTime,
    time_minus_one: DateTime,
    time_minus_two: DateTime,
) -> None:
    """
    Initialize flat_down_stop variable based on historical power data.

    For T_stop >= 1 and T_stable >= 1.

    :param obj: The thermal unit to initialize
    :type obj: ThermalPO
    :param time: Current time
    :type time: DateTime
    :param time_minus_one: Time minus one timestep
    :type time_minus_one: DateTime
    :param time_minus_two: Time minus two timesteps
    :type time_minus_two: DateTime
    :return: None
    :rtype: None
    """

    obj.flat_down_stop.set_extended(
        time,
        (
            obj.stop_var.get_extended_value(time)
            + obj.on_down_var.get_extended_value(time_minus_one)
            + obj.on_flat_var.get_extended_value(time_minus_two)
        )
        / 3,
    )
