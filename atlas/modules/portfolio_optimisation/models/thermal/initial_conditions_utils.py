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

from atlas.math.timeseries import Timeseries
from atlas.solver.solver_interface import OptimisationModel


def initialize_day_zero_core(
    thermal_unit: ThermalPO,
    model: OptimisationModel,
    time: DateTime,
) -> None:
    """
    Initialize core day zero state variables common to ALL combinations.

    All thermal units start in OFF state with:
    - OFF state = 1
    - Turned on/off transitions = 0
    - Power level = 0

    Args:
        thermal_unit: The thermal unit to initialize
        model: The optimization model
        time: The current time step
    """
    power_level_var = model.get_variable(f"{thermal_unit.name}_power_level_{time}")
    # Fix core state variables
    thermal_unit.off_var.set_extended(time, 1)
    thermal_unit.turned_on.set_extended(time, 0)
    thermal_unit.turned_off.set_extended(time, 0)
    model.add_constraint(power_level_var == 0, f"init_power_{thermal_unit.name}_{time}")


def initialize_day_zero_on_states(
    thermal_unit: ThermalPO,
    time: DateTime,
) -> None:
    """
    Initialize ON_UP and ON_DOWN state variables for day zero.

    For T_stable = 0

    Args:
        thermal_unit: The thermal unit to initialize
        model: The optimization model
        time: The current time step
    """

    thermal_unit.on_up_var.set_extended(time, 0)
    thermal_unit.on_down_var.set_extended(time, 0)


def initialize_day_zero_stop_state(
    thermal_unit: ThermalPO,
    time: DateTime,
) -> None:
    """
    Initialize STOP state variable for day zero.

    For T_stop >= 1

    Args:
        thermal_unit: The thermal unit to initialize
        model: The optimization model
        time: The current time step
    """

    thermal_unit.stop_var.set_extended(time, 0)


def initialize_day_zero_start_state(
    thermal_unit: ThermalPO,
    time: DateTime,
) -> None:
    """
    Initialize START state variable for day zero.

    For T_start >= 1.

    Args:
        thermal_unit: The thermal unit to initialize
        model: The optimization model
        time: The current time step
    """
    thermal_unit.on_start_var.set_extended(time, 0)


def initialize_day_zero_down_to_stop(
    thermal_unit: ThermalPO,
    time: DateTime,
) -> None:
    """
    Initialize down_to_stop gradient variable for day zero.

    T_stop >= 1 and T_stable = 0.

    Args:
        thermal_unit: The thermal unit to initialize
        model: The optimization model
        time: The current time step
    """

    thermal_unit.down_to_stop_grad.set_extended(time, 0)


def initialize_day_zero_gradient_vars(
    thermal_unit: ThermalPO,
    model: OptimisationModel,
    time: DateTime,
) -> None:
    """
    Initialize gradient auxiliary variables for day zero.

    T_stable >= 1.

    Args:
        thermal_unit: The thermal unit to initialize
        model: The optimization model
        time: The current time step
    """
    u_var = model.get_variable(f"UP_grad_{time}_{thermal_unit.name}")
    d_var = model.get_variable(f"DOWN_grad_{time}_{thermal_unit.name}")
    tilde_u_var = model.get_variable(f"aux_up_grad_{time}_{thermal_unit.name}")
    tilde_d_var = model.get_variable(f"aux_down_grad_{time}_{thermal_unit.name}")

    model.add_constraint(u_var == 0, f"init_u_grad_{thermal_unit.name}_{time}")
    model.add_constraint(d_var == 0, f"init_d_grad_{thermal_unit.name}_{time}")
    model.add_constraint(tilde_u_var == 0, f"init_tilde_u_grad_{thermal_unit.name}_{time}")
    model.add_constraint(tilde_d_var == 0, f"init_tilde_d_grad_{thermal_unit.name}_{time}")


def initialize_day_zero_stable_vars(
    thermal_unit: ThermalPO,
    time: DateTime,
) -> None:
    """
    Initialize stable state variables for day zero.

    T_stable >= 1. For stable timeframe.

    Args:
        thermal_unit: The thermal unit to initialize
        model: The optimization model
        parameters: Portfolio optimization parameters
        time: The current time step
    """

    thermal_unit.on_flat_var.set_extended(time, 0)
    thermal_unit.on_up_var.set_extended(time, 0)
    thermal_unit.on_down_var.set_extended(time, 0)

    thermal_unit.stable_var.set_extended(time, 0)
    thermal_unit.entered_up_var.set_extended(time, 0)
    thermal_unit.entered_down_var.set_extended(time, 0)


def initialize_day_zero_flat_down_stop(
    thermal_unit: ThermalPO,
    time: DateTime,
) -> None:
    """
    Initialize flat_down_stop variable for day zero.

    T_stop >= 1, T_stable >= 1.

    Args:
        thermal_unit: The thermal unit to initialize
        model: The optimization model
        time: The current time step
    """

    thermal_unit.flat_down_stop.set_extended(time, 0)


def initialize_gradient_initial_conditions(
    thermal_unit: ThermalPO,
    model: OptimisationModel,
    power_timeseries: Timeseries,
    parameters: PortfolioOptimisationParameters,
) -> None:
    """
    Initialize gradient variables based on historical power data.
    For T_stable >= 1.
    """
    start_date_minus_one = parameters.start_date - parameters.timestep
    start_date_minus_two = parameters.start_date - 2 * parameters.timestep

    power_minus_one = power_timeseries.get_value(start_date_minus_one)
    power_minus_two = power_timeseries.get_value(start_date_minus_two)

    u_var = model.get_variable(f"UP_grad_{start_date_minus_one}_{thermal_unit.name}")
    d_var = model.get_variable(f"DOWN_grad_{start_date_minus_one}_{thermal_unit.name}")

    # Calculate gradient values based on power trend
    power_diff = power_minus_one - power_minus_two

    # U gradient: only non-zero if unit was in UP state at both time steps
    if model.get_constraint_bounds(f"init_on_up_{thermal_unit.name}_{start_date_minus_one}").lower_bound == 1 and (
        model.get_constraint_bounds(f"init_on_up_{thermal_unit.name}_{start_date_minus_two}").lower_bound == 1
    ):
        model.add_constraint(u_var == power_diff, f"init_u_grad_{thermal_unit.name}_{start_date_minus_one}")
    else:
        model.add_constraint(u_var == 0, f"init_u_grad_{thermal_unit.name}_{start_date_minus_one}")

    # D gradient: only non-zero if unit was in DOWN state at both time steps
    if model.get_constraint_bounds(f"init_on_down_{thermal_unit.name}_{start_date_minus_one}").lower_bound == 1 and (
        model.get_constraint_bounds(f"init_on_down_{thermal_unit.name}_{start_date_minus_two}").lower_bound == 1
    ):
        model.add_constraint(d_var == power_diff, f"init_d_grad_{thermal_unit.name}_{start_date_minus_one}")
    else:
        model.add_constraint(d_var == 0, f"init_d_grad_{thermal_unit.name}_{start_date_minus_one}")


def initialize_flat_down_stop_initial_conditions(
    thermal_unit: ThermalPO,
    start_date_minus_one: DateTime,
    start_date_minus_two: DateTime,
    start_date_minus_three: DateTime,
) -> None:
    """
    Initialize flat_down_stop variable based on historical power data.
    For T_stop >= 1 and T_stable >= 1.
    """

    thermal_unit.flat_down_stop.set_extended(
        (
            thermal_unit.stop_var.get_extended_value(start_date_minus_one)
            + thermal_unit.on_down_var.get_extended_value(start_date_minus_two)
            + thermal_unit.on_flat_var.get_extended_value(start_date_minus_three)
        )
        / 3
    )
