"""
Utility functions for thermal unit initial conditions.

This module provides common day zero initialization logic shared across
all thermal model combinations to reduce code duplication.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pendulum import DateTime

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.models.thermal.thermal import ThermalPO

from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.solver.solver_interface import OptimisationModel


def initialize_day_zero_core(
    thermal_unit: ThermalPO,
    model: OptimisationModel,
    current_time: DateTime,
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
        current_time: The current time step
    """
    # Get core state variables (present in ALL combinations)
    off_var = model.get_variable(f"OFF_var_{thermal_unit.name}_{current_time}")
    turned_on_var = model.get_variable(f"t_on_of_{thermal_unit.name}_{current_time}")
    turned_off_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{current_time}")
    power_level_var = model.get_variable(f"{thermal_unit.name}_power_level_{current_time}")

    # Fix core state variables
    model.add_constraint(off_var == 1, f"init_off_{thermal_unit.name}_{current_time}")
    model.add_constraint(turned_on_var == 0, f"init_turned_on_{thermal_unit.name}_{current_time}")
    model.add_constraint(turned_off_var == 0, f"init_turned_off_{thermal_unit.name}_{current_time}")
    model.add_constraint(power_level_var == 0, f"init_power_{thermal_unit.name}_{current_time}")


def initialize_day_zero_on_states(
    thermal_unit: ThermalPO,
    model: OptimisationModel,
    current_time: DateTime,
) -> None:
    """
    Initialize ON_UP and ON_DOWN state variables for day zero.

    Used by combinations 1, 2, 4, 8 (combinations without stable constraints).

    Args:
        thermal_unit: The thermal unit to initialize
        model: The optimization model
        current_time: The current time step
    """
    on_up_var = model.get_variable(f"ON_UP_var_{thermal_unit.name}_{current_time}")
    on_down_var = model.get_variable(f"ON_DOWN_var_{thermal_unit.name}_{current_time}")

    model.add_constraint(on_up_var == 0, f"init_on_up_{thermal_unit.name}_{current_time}")
    model.add_constraint(on_down_var == 0, f"init_on_down_{thermal_unit.name}_{current_time}")


def initialize_day_zero_stop_state(
    thermal_unit: ThermalPO,
    model: OptimisationModel,
    current_time: DateTime,
) -> None:
    """
    Initialize STOP state variable for day zero.

    Used by combinations 2, 5, 6, 8 (T_stop >= 1).

    Args:
        thermal_unit: The thermal unit to initialize
        model: The optimization model
        current_time: The current time step
    """
    stop_var = model.get_variable(f"STOP_{thermal_unit.name}_{current_time}")
    model.add_constraint(stop_var == 0, f"init_stop_{thermal_unit.name}_{current_time}")


def initialize_day_zero_start_state(
    thermal_unit: ThermalPO,
    model: OptimisationModel,
    current_time: DateTime,
) -> None:
    """
    Initialize START state variable for day zero.

    Used by combinations 4, 6, 7, 8 (T_start >= 1).

    Args:
        thermal_unit: The thermal unit to initialize
        model: The optimization model
        current_time: The current time step
    """
    start_var = model.get_variable(f"ON_START_{thermal_unit.name}_{current_time}")
    model.add_constraint(start_var == 0, f"init_start_{thermal_unit.name}_{current_time}")


def initialize_day_zero_down_to_stop(
    thermal_unit: ThermalPO,
    model: OptimisationModel,
    current_time: DateTime,
) -> None:
    """
    Initialize down_to_stop gradient variable for day zero.

    Used by combinations 2, 8 (T_stop >= 1 without stable constraints).

    Args:
        thermal_unit: The thermal unit to initialize
        model: The optimization model
        current_time: The current time step
    """
    down_to_stop_var = model.get_variable(f"down_to_stop_grad_{current_time}_{thermal_unit.name}")
    model.add_constraint(down_to_stop_var == 0, f"init_down_to_stop_{thermal_unit.name}_{current_time}")


def initialize_day_zero_gradient_vars(
    thermal_unit: ThermalPO,
    model: OptimisationModel,
    current_time: DateTime,
) -> None:
    """
    Initialize gradient auxiliary variables for day zero.

    Used by combinations 3, 5, 6, 7, 8 (T_stable >= 1).

    Args:
        thermal_unit: The thermal unit to initialize
        model: The optimization model
        current_time: The current time step
    """
    u_var = model.get_variable(f"UP_grad_{current_time}_for_{thermal_unit.name}")
    d_var = model.get_variable(f"DOWN_grad_{current_time}_{thermal_unit.name}")
    tilde_u_var = model.get_variable(f"aux_up_grad_{current_time}_{thermal_unit.name}")
    tilde_d_var = model.get_variable(f"aux_down_grad_{current_time}_{thermal_unit.name}")

    model.add_constraint(u_var == 0, f"init_u_grad_{thermal_unit.name}_{current_time}")
    model.add_constraint(d_var == 0, f"init_d_grad_{thermal_unit.name}_{current_time}")
    model.add_constraint(tilde_u_var == 0, f"init_tilde_u_grad_{thermal_unit.name}_{current_time}")
    model.add_constraint(tilde_d_var == 0, f"init_tilde_d_grad_{thermal_unit.name}_{current_time}")


def initialize_day_zero_stable_vars(
    thermal_unit: ThermalPO,
    model: OptimisationModel,
    parameters: PortfolioOptimisationParameters,
    current_time: DateTime,
) -> None:
    """
    Initialize stable state variables for day zero.

    Used by combinations 3, 5, 6, 7, 8 (T_stable >= 1).
    Only initializes if not the last timestep.

    Args:
        thermal_unit: The thermal unit to initialize
        model: The optimization model
        parameters: Portfolio optimization parameters
        current_time: The current time step
    """
    next_time = current_time + parameters.timestep
    if next_time <= parameters.end_date:
        # Get stable state variables
        on_flat_var = model.get_variable(f"ON_FLAT_{thermal_unit.name}_{current_time}")
        on_up_var = model.get_variable(f"ON_UP_var_{thermal_unit.name}_{current_time}")
        on_down_var = model.get_variable(f"ON_DOWN_var_{thermal_unit.name}_{current_time}")
        stable_var = model.get_variable(f"stable_{current_time}_{thermal_unit.name}")
        entered_up_var = model.get_variable(f"entered_up_{current_time}_{thermal_unit.name}")
        entered_down_var = model.get_variable(f"entered_down_{current_time}_{thermal_unit.name}")

        # Fix stable state variables
        model.add_constraint(on_flat_var == 0, f"init_on_flat_{thermal_unit.name}_{current_time}")
        model.add_constraint(on_up_var == 0, f"init_on_up_{thermal_unit.name}_{current_time}")
        model.add_constraint(on_down_var == 0, f"init_on_down_{thermal_unit.name}_{current_time}")

        # Fix stable auxiliary variables
        model.add_constraint(stable_var == 0, f"init_stable_{thermal_unit.name}_{current_time}")
        model.add_constraint(entered_up_var == 0, f"init_entered_up_{thermal_unit.name}_{current_time}")
        model.add_constraint(entered_down_var == 0, f"init_entered_down_{thermal_unit.name}_{current_time}")


def initialize_day_zero_flat_down_stop(
    thermal_unit: ThermalPO,
    model: OptimisationModel,
    current_time: DateTime,
) -> None:
    """
    Initialize flat_down_stop variable for day zero.

    Used by combinations 5, 6, 8 (T_stop >= 1 with T_stable >= 1).

    Args:
        thermal_unit: The thermal unit to initialize
        model: The optimization model
        current_time: The current time step
    """
    flat_down_stop_var = model.get_variable(f"flat_down_stop_{current_time}_{thermal_unit.name}")
    model.add_constraint(flat_down_stop_var == 0, f"init_flat_down_stop_{thermal_unit.name}_{current_time}")


def initialize_day_zero_flat_down_stop_in_stable(
    thermal_unit: ThermalPO,
    model: OptimisationModel,
    parameters: PortfolioOptimisationParameters,
    current_time: DateTime,
) -> None:
    """
    Initialize flat_down_stop variable inside stable variables section for day zero.

    Used by combination 8 (T_stop >= 1, T_start >= 1, T_stable >= 1).
    This is added to the stable variables initialization section.

    Args:
        thermal_unit: The thermal unit to initialize
        model: The optimization model
        parameters: Portfolio optimization parameters
        current_time: The current time step
    """
    next_time = current_time + parameters.timestep
    if next_time <= parameters.end_date:
        flat_down_stop_var = model.get_variable(f"flat_down_stop_{current_time}_{thermal_unit.name}")
        model.add_constraint(flat_down_stop_var == 0, f"init_flat_down_stop_{thermal_unit.name}_{current_time}")
