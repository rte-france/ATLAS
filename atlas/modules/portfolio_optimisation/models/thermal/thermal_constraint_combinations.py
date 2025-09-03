"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Thermal unit constraint combinations for different operational constraint scenarios.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pendulum import DateTime

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.models.thermal.thermal import ThermalPO

from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_automated
from atlas.solver.solver_interface import OptimisationModel


class ThermalConstraintCombinations:
    """Handles constraint combinations for thermal units across 8 different scenarios."""

    def __init__(self, thermal_unit: ThermalPO):
        """Initialize with reference to the thermal unit."""
        self.thermal_unit = thermal_unit

    def add_combination_1_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ) -> None:
        """Combination 1: T_stop = T_stable = T_start = 0"""
        prev_time = time - parameters.timestep

        # Get variables
        off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
        on_up_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{time}")
        on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{time}")
        turned_on_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{time}")
        turned_off_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{time}")
        power_level_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{time}")

        # Previous time variables
        off_prev_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{prev_time}")
        on_up_prev_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{prev_time}")
        on_down_prev_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{prev_time}")
        power_prev_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{prev_time}")

        # Reserve variables
        reserves_up_var = model.get_variable(f"reserves_up_{self.thermal_unit.name}_{time}")
        reserves_down_var = model.get_variable(f"reserves_down_{self.thermal_unit.name}_{time}")
        automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{self.thermal_unit.name}_{time}")
        automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{self.thermal_unit.name}_{time}")
        unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{self.thermal_unit.name}_{time}")
        unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{self.thermal_unit.name}_{time}")
        relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{self.thermal_unit.name}_{time}")

        # Power bounds
        q_upper = self.thermal_unit.maximum_power.get_value(time)
        q_lower = self.thermal_unit.minimum_power.get_value(time)
        maximum_automated = get_maximum_automated(self.thermal_unit)

        # A. CONSTRAINTS ON THE AUXILIARY VARIABLES

        # Constraints on turned_on (sec. 6.1.1)
        model.add_constraint(turned_on_var <= 1 - off_var)
        model.add_constraint(turned_on_var <= off_prev_var)
        model.add_constraint(turned_on_var >= off_prev_var - off_var)

        # Constraints on turned_off (sec. 6.1.2)
        model.add_constraint(turned_off_var <= 1 - off_prev_var)
        model.add_constraint(turned_off_var <= off_var)
        model.add_constraint(turned_off_var >= off_var - off_prev_var)

        # B. CONSTRAINTS ON THE STATE VARIABLES

        # Mutual exclusion constraint
        model.add_constraint(off_var + on_up_var + on_down_var == 1)

        # Minimum time on and off constraints
        if self.thermal_unit._T_on >= 2:
            for s in range(1, self.thermal_unit._T_on):
                local_time = time - s * parameters.timestep
                turned_on_local_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{local_time}")
                model.add_constraint(turned_on_local_var <= on_up_var + on_down_var)

        if self.thermal_unit._T_off >= 2:
            for s in range(1, self.thermal_unit._T_off):
                local_time = time - s * parameters.timestep
                turned_off_local_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{local_time}")
                model.add_constraint(turned_off_local_var <= off_var)

        # C. CONSTRAINTS ON THE CONTROL VARIABLE

        # Reserve "fill up" constraints

        # Upward constraint
        model.add_constraint(
            power_level_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
            <= q_upper + parameters.allowed_round_off_error
        )
        model.add_constraint(
            power_level_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
            >= q_upper - parameters.allowed_round_off_error
        )

        # Downward constraint
        model.add_constraint(
            power_level_var
            - reserves_down_var
            - automated_reserves_down_var
            - unprovided_reserves_down_var
            + relaxed_reserves_var
            <= q_lower + parameters.allowed_round_off_error
        )
        model.add_constraint(
            power_level_var
            - reserves_down_var
            - automated_reserves_down_var
            - unprovided_reserves_down_var
            + relaxed_reserves_var
            >= q_lower - parameters.allowed_round_off_error
        )

        # Relaxed reserve disabling condition
        model.add_constraint(relaxed_reserves_var <= q_lower * (1 - on_up_var - on_down_var))

        # Reserve availability constraints
        model.add_constraint(automated_reserves_up_var <= maximum_automated * (1 - off_var))
        model.add_constraint(automated_reserves_down_var <= maximum_automated * (1 - off_var))
        model.add_constraint(reserves_up_var <= q_upper * (1 - off_var))
        model.add_constraint(reserves_down_var <= q_upper * (1 - off_var))

        # Power output bounds
        model.add_constraint(power_level_var >= q_lower * (on_up_var + on_down_var))
        model.add_constraint(power_level_var <= q_upper * (on_up_var + on_down_var))

        # Power gradients (if not the last time step)
        if time in parameters.thermal_op_times[:-1]:  # Not the last time step
            if self.thermal_unit._Delta_Q > 0:  # Finite gradient
                # Upward gradient
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self.thermal_unit._Delta_Q * on_up_prev_var
                    + self.thermal_unit._Delta_Q_unconstrained * turned_on_var
                )
                # Downward gradient
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self.thermal_unit._Delta_Q * on_down_prev_var
                    - self.thermal_unit._Delta_Q_unconstrained * turned_off_var
                )
            elif self.thermal_unit._Delta_Q == 0:  # Infinite gradient
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self.thermal_unit._Delta_Q_unconstrained * on_up_prev_var
                    + self.thermal_unit._Delta_Q_unconstrained * turned_on_var
                )
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self.thermal_unit._Delta_Q_unconstrained * on_down_prev_var
                    - self.thermal_unit._Delta_Q_unconstrained * turned_off_var
                )

        # Daily energy constraints (if applicable)
        if self.thermal_unit.has_daily_energy_constraint:
            # This would need to be implemented at a higher level since it requires all time steps for a day
            pass

    def add_combination_2_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ) -> None:
        """Combination 2: T_stop >= 1, T_stable = T_start = 0"""
        prev_time = time - parameters.timestep

        # Get variables
        off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
        on_up_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{time}")
        on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{time}")
        stop_var = model.get_variable(f"STOP_e_{self.thermal_unit.name}_at_{time}")
        turned_on_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{time}")
        turned_off_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{time}")
        down_to_stop_var = model.get_variable(f"down_to_stop_grad_at_{time}_e_{self.thermal_unit.name}")
        power_level_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{time}")

        # Previous time variables
        off_prev_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{prev_time}")
        on_up_prev_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{prev_time}")
        on_down_prev_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{prev_time}")
        stop_prev_var = model.get_variable(f"STOP_e_{self.thermal_unit.name}_at_{prev_time}")
        power_prev_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{prev_time}")

        # Reserve variables
        reserves_up_var = model.get_variable(f"reserves_up_{self.thermal_unit.name}_{time}")
        reserves_down_var = model.get_variable(f"reserves_down_{self.thermal_unit.name}_{time}")
        automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{self.thermal_unit.name}_{time}")
        automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{self.thermal_unit.name}_{time}")
        unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{self.thermal_unit.name}_{time}")
        unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{self.thermal_unit.name}_{time}")
        relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{self.thermal_unit.name}_{time}")

        # Power bounds and parameters
        q_upper = self.maximum_power.get_value(time)
        q_lower = self.minimum_power.get_value(time)
        maximum_automated = get_maximum_automated(self)

        # Shutdown gradient parameters
        q_min = self.minimum_power.max()  # Get the minimum power without reserve requirements
        q_step = q_min / self._T_stop

        # A. CONSTRAINTS ON THE AUXILIARY VARIABLES

        # Constraints on turned_on (sec. 6.1.1)
        model.add_constraint(turned_on_var <= 1 - off_var)
        model.add_constraint(turned_on_var <= off_prev_var)
        model.add_constraint(turned_on_var >= off_prev_var - off_var)

        # Constraints on turned_off (sec. 6.1.2) - when entering STOP state
        model.add_constraint(turned_off_var <= 1 - stop_prev_var)
        model.add_constraint(turned_off_var <= stop_var)
        model.add_constraint(turned_off_var >= stop_var - stop_prev_var)

        # Constraints on down_to_stop (sec. 6.1.5)
        model.add_constraint(down_to_stop_var <= 1 - on_down_prev_var)
        model.add_constraint(down_to_stop_var <= on_down_var)
        model.add_constraint(down_to_stop_var >= on_down_var - on_down_prev_var)

        # B. CONSTRAINTS ON THE STATE VARIABLES

        # Mutual exclusion constraint - now includes STOP state
        model.add_constraint(off_var + on_up_var + on_down_var + stop_var == 1)

        # Transition constraints
        # Forbidden transitions: OFF->STOP, STOP->ON_UP/ON_DOWN, ON_UP/ON_DOWN->OFF
        model.add_constraint(stop_prev_var + on_up_var <= 1)
        model.add_constraint(stop_prev_var + on_down_var <= 1)
        model.add_constraint(off_prev_var + stop_var <= 1)
        model.add_constraint(on_up_prev_var + off_var <= 1)
        model.add_constraint(on_down_prev_var + off_var <= 1)

        # Eviction constraint (equation 19)
        if self._T_stop > 1:
            eviction_time = time - (self._T_stop - 1) * parameters.timestep
            turned_off_eviction_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{eviction_time}")
            model.add_constraint(turned_off_eviction_var + stop_var <= 1)

        # Minimum time constraints
        if self._T_on >= 2:
            for s in range(1, self._T_on):
                local_time = time - s * parameters.timestep
                turned_on_local_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{local_time}")
                model.add_constraint(turned_on_local_var <= on_up_var + on_down_var)

        if self._T_off >= 2:
            for s in range(1, self._T_off):
                local_time = time - (s + self._T_stop) * parameters.timestep
                turned_off_local_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{local_time}")
                model.add_constraint(turned_off_local_var <= off_var)

        # Shutdown ramp constraints
        if self._T_stop >= 2:
            for s in range(1, self._T_stop - 1):
                local_time = time - s * parameters.timestep
                turned_off_local_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{local_time}")
                model.add_constraint(turned_off_local_var <= stop_var)

        # C. CONSTRAINTS ON THE CONTROL VARIABLE

        # Reserve "fill up" constraints (same as Combination 1)
        model.add_constraint(
            power_level_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
            <= q_upper + parameters.allowed_round_off_error
        )
        model.add_constraint(
            power_level_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
            >= q_upper - parameters.allowed_round_off_error
        )

        model.add_constraint(
            power_level_var
            - reserves_down_var
            - automated_reserves_down_var
            - unprovided_reserves_down_var
            + relaxed_reserves_var
            <= q_lower + parameters.allowed_round_off_error
        )
        model.add_constraint(
            power_level_var
            - reserves_down_var
            - automated_reserves_down_var
            - unprovided_reserves_down_var
            + relaxed_reserves_var
            >= q_lower - parameters.allowed_round_off_error
        )

        # Relaxed reserve disabling condition
        model.add_constraint(relaxed_reserves_var <= q_lower * (1 - on_up_var - on_down_var))

        # Reserve availability constraints - now includes STOP state
        model.add_constraint(automated_reserves_up_var <= maximum_automated * (1 - off_var - stop_var))
        model.add_constraint(automated_reserves_down_var <= maximum_automated * (1 - off_var - stop_var))
        model.add_constraint(reserves_up_var <= q_upper * (1 - off_var - stop_var))
        model.add_constraint(reserves_down_var <= q_upper * (1 - off_var - stop_var))

        # Power output bounds with shutdown gradient
        model.add_constraint(power_level_var >= q_lower * (on_up_var + on_down_var) + turned_off_var * (q_min - q_step))
        model.add_constraint(
            power_level_var <= q_upper * (on_up_var + on_down_var) + stop_var * q_min - turned_off_var * q_step
        )

        # Power gradients with shutdown considerations
        if time in parameters.thermal_op_times[:-1]:  # Not the last time step
            if self._Delta_Q > 0:  # Finite gradient
                # Upward gradient
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q * on_up_prev_var
                    - turned_off_var * q_step
                    - stop_prev_var * q_step
                    + self._Delta_Q_unconstrained * turned_on_var
                )
                # Downward gradient
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q * on_down_prev_var
                    - turned_off_var * q_step
                    - stop_prev_var * q_step
                    + down_to_stop_var * self._Delta_Q
                )
            elif self._Delta_Q == 0:  # Infinite gradient
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q_unconstrained * on_up_prev_var
                    - turned_off_var * q_step
                    - stop_prev_var * q_step
                    + self._Delta_Q_unconstrained * turned_on_var
                )
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q_unconstrained * on_down_prev_var
                    - turned_off_var * q_step
                    - stop_prev_var * q_step
                    + self._Delta_Q_unconstrained * down_to_stop_var
                )

        # Daily energy constraints (if applicable)
        if self.has_daily_energy_constraint:
            # This would need to be implemented at a higher level since it requires all time steps for a day
            pass

    def add_combination_3_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ) -> None:
        """Combination 3: T_start >= 1, T_stop = T_stable = 0"""
        prev_time = time - parameters.timestep

        # Get variables
        off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
        on_up_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{time}")
        on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{time}")
        on_flat_var = model.get_variable(f"ON_FLAT_e_{self.thermal_unit.name}_at_{time}")
        turned_on_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{time}")
        turned_off_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{time}")
        stable_var = model.get_variable(f"stable_at_{time}_e_{self.thermal_unit.name}")
        entered_up_var = model.get_variable(f"entered_up_at_{time}_e_{self.thermal_unit.name}")
        entered_down_var = model.get_variable(f"entered_down_at_{time}_e_{self.thermal_unit.name}")
        power_level_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{time}")

        # Gradient auxiliary variables
        up_grad_var = model.get_variable(f"UP_grad_at_{time}_for_e_{self.thermal_unit.name}")
        aux_up_grad_var = model.get_variable(f"aux_up_grad_at_{time}_e_{self.thermal_unit.name}")
        down_grad_var = model.get_variable(f"DOWN_grad_at_{time}_e_{self.thermal_unit.name}")
        aux_down_grad_var = model.get_variable(f"aux_down_grad_at_{time}_e_{self.thermal_unit.name}")

        # Previous time variables
        off_prev_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{prev_time}")
        on_up_prev_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{prev_time}")
        on_down_prev_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{prev_time}")
        on_flat_prev_var = model.get_variable(f"ON_FLAT_e_{self.thermal_unit.name}_at_{prev_time}")
        power_prev_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{prev_time}")

        # Reserve variables
        reserves_up_var = model.get_variable(f"reserves_up_{self.thermal_unit.name}_{time}")
        reserves_down_var = model.get_variable(f"reserves_down_{self.thermal_unit.name}_{time}")
        automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{self.thermal_unit.name}_{time}")
        automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{self.thermal_unit.name}_{time}")
        unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{self.thermal_unit.name}_{time}")
        unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{self.thermal_unit.name}_{time}")
        relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{self.thermal_unit.name}_{time}")

        # Power bounds
        q_upper = self.maximum_power.get_value(time)
        q_lower = self.minimum_power.get_value(time)
        maximum_automated = get_maximum_automated(self)

        # A. CONSTRAINTS ON THE AUXILIARY VARIABLES

        # Constraints on turned_on (sec. 6.1.1)
        model.add_constraint(turned_on_var <= 1 - off_var)
        model.add_constraint(turned_on_var <= off_prev_var)
        model.add_constraint(turned_on_var >= off_prev_var - off_var)

        # Constraints on turned_off (sec. 6.1.2)
        model.add_constraint(turned_off_var <= 1 - off_prev_var)
        model.add_constraint(turned_off_var <= off_var)
        model.add_constraint(turned_off_var >= off_var - off_prev_var)

        # Constraints on stable (sec. 6.1.3)
        model.add_constraint(stable_var <= 1 - on_flat_prev_var)
        model.add_constraint(stable_var <= on_flat_var)
        model.add_constraint(stable_var >= on_flat_var - on_flat_prev_var)

        # Constraints on entered_up
        model.add_constraint(entered_up_var <= 1 - on_up_prev_var)
        model.add_constraint(entered_up_var <= on_up_var)
        model.add_constraint(entered_up_var >= on_up_var - on_up_prev_var)

        # Constraints on entered_down
        model.add_constraint(entered_down_var <= 1 - on_down_prev_var)
        model.add_constraint(entered_down_var <= on_down_var)
        model.add_constraint(entered_down_var >= on_down_var - on_down_prev_var)

        # UP and DOWN "semi-continuous" variables for the gradient
        # First stage: tilde_U and tilde_D (aux_up_grad and aux_down_grad)
        # tilde_U (aux_up_grad)
        model.add_constraint(aux_up_grad_var <= q_upper * on_up_prev_var)
        model.add_constraint(aux_up_grad_var >= q_lower * on_up_prev_var)
        model.add_constraint(aux_up_grad_var <= power_level_var - power_prev_var - q_lower * (1 - on_up_prev_var))
        model.add_constraint(aux_up_grad_var >= power_level_var - power_prev_var - q_upper * (1 - on_up_prev_var))

        # tilde_D (aux_down_grad)
        model.add_constraint(aux_down_grad_var <= q_upper * on_down_prev_var)
        model.add_constraint(aux_down_grad_var >= q_lower * on_down_prev_var)
        model.add_constraint(aux_down_grad_var <= power_level_var - power_prev_var - q_lower * (1 - on_down_prev_var))
        model.add_constraint(aux_down_grad_var >= power_level_var - power_prev_var - q_upper * (1 - on_down_prev_var))

        # Second stage: U and D (up_grad and down_grad)
        # U (up_grad)
        model.add_constraint(up_grad_var <= q_upper * on_up_var)
        model.add_constraint(up_grad_var >= q_lower * on_up_var)
        model.add_constraint(up_grad_var <= aux_up_grad_var - q_lower * (1 - on_up_var))
        model.add_constraint(up_grad_var >= aux_up_grad_var - q_upper * (1 - on_up_var))

        # D (down_grad)
        model.add_constraint(down_grad_var <= q_upper * on_down_var)
        model.add_constraint(down_grad_var >= q_lower * on_down_var)
        model.add_constraint(down_grad_var <= aux_down_grad_var - q_lower * (1 - on_down_var))
        model.add_constraint(down_grad_var >= aux_down_grad_var - q_upper * (1 - on_down_var))

        # B. CONSTRAINTS ON THE STATE VARIABLES

        # Mutual exclusion constraint - now includes ON_FLAT state
        model.add_constraint(off_var + on_up_var + on_down_var + on_flat_var == 1)

        # Transition constraints
        # UP-DOWN and DOWN-UP transitions are forbidden
        model.add_constraint(on_up_prev_var + on_down_var <= 1)
        model.add_constraint(on_down_prev_var + on_up_var <= 1)

        # Minimum time constraints
        if self._T_on >= 2:
            for s in range(1, self._T_on):
                local_time = time - s * parameters.timestep
                turned_on_local_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{local_time}")
                model.add_constraint(turned_on_local_var <= on_up_var + on_down_var + on_flat_var)

        if self._T_off >= 2:
            for s in range(1, self._T_off):
                local_time = time - s * parameters.timestep
                turned_off_local_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{local_time}")
                model.add_constraint(turned_off_local_var <= off_var)

        if self._T_stable >= 2:
            for s in range(1, self._T_stable - 1):
                local_time = time - s * parameters.timestep
                stable_local_var = model.get_variable(f"stable_at_{local_time}_e_{self.thermal_unit.name}")
                model.add_constraint(stable_local_var <= on_flat_var)

        # C. CONSTRAINTS ON THE CONTROL VARIABLE

        # Reserve "fill up" constraints
        model.add_constraint(
            power_level_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
            <= q_upper + parameters.allowed_round_off_error
        )
        model.add_constraint(
            power_level_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
            >= q_upper - parameters.allowed_round_off_error
        )

        model.add_constraint(
            power_level_var
            - reserves_down_var
            - automated_reserves_down_var
            - unprovided_reserves_down_var
            + relaxed_reserves_var
            <= q_lower + parameters.allowed_round_off_error
        )
        model.add_constraint(
            power_level_var
            - reserves_down_var
            - automated_reserves_down_var
            - unprovided_reserves_down_var
            + relaxed_reserves_var
            >= q_lower - parameters.allowed_round_off_error
        )

        # Relaxed reserve disabling condition - includes ON_FLAT state
        model.add_constraint(relaxed_reserves_var <= q_lower * (1 - on_up_var - on_flat_var - on_down_var))

        # Reserve availability constraints
        model.add_constraint(automated_reserves_up_var <= maximum_automated * (1 - off_var))
        model.add_constraint(automated_reserves_down_var <= maximum_automated * (1 - off_var))
        # Manual reserves only available in FLAT state (not during ramping)
        model.add_constraint(reserves_up_var <= q_upper * (1 - off_var - on_up_var - on_down_var))
        model.add_constraint(reserves_down_var <= q_upper * (1 - off_var - on_up_var - on_down_var))

        # Power output bounds - includes ON_FLAT state
        model.add_constraint(power_level_var >= q_lower * (on_up_var + on_down_var + on_flat_var))
        model.add_constraint(power_level_var <= q_upper * (on_up_var + on_down_var + on_flat_var))

        # Power gradients with gradient auxiliary variables
        if time in parameters.thermal_op_times[:-1]:  # Not the last time step
            if self._Delta_Q > 0:  # Finite gradient
                # Upward gradient
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q * entered_up_var
                    + up_grad_var
                    + down_grad_var
                    + self._Delta_Q_unconstrained * turned_on_var
                )
                # Downward gradient
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q * entered_down_var
                    + up_grad_var
                    + down_grad_var
                    - self._Delta_Q_unconstrained * turned_off_var
                )
            elif self._Delta_Q == 0:  # Infinite gradient
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q_unconstrained * entered_up_var
                    + up_grad_var
                    + down_grad_var
                    + self._Delta_Q_unconstrained * turned_on_var
                )
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q_unconstrained * entered_down_var
                    + up_grad_var
                    + down_grad_var
                    - self._Delta_Q_unconstrained * turned_off_var
                )

        # Daily energy constraints (if applicable)
        if self.has_daily_energy_constraint:
            # This would need to be implemented at a higher level since it requires all time steps for a day
            pass

    def add_combination_4_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ) -> None:
        """Combination 4: T_stop >= 1, T_start >= 1, T_stable = 0"""
        prev_time = time - parameters.timestep

        # Get variables
        off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
        on_up_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{time}")
        on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{time}")
        start_var = model.get_variable(f"ON_START_e_{self.thermal_unit.name}_at_{time}")
        turned_on_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{time}")
        turned_off_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{time}")
        power_level_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{time}")

        # Previous time variables
        off_prev_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{prev_time}")
        on_up_prev_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{prev_time}")
        on_down_prev_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{prev_time}")
        start_prev_var = model.get_variable(f"ON_START_e_{self.thermal_unit.name}_at_{prev_time}")
        power_prev_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{prev_time}")

        # Reserve variables
        reserves_up_var = model.get_variable(f"reserves_up_{self.thermal_unit.name}_{time}")
        reserves_down_var = model.get_variable(f"reserves_down_{self.thermal_unit.name}_{time}")
        automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{self.thermal_unit.name}_{time}")
        automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{self.thermal_unit.name}_{time}")
        unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{self.thermal_unit.name}_{time}")
        unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{self.thermal_unit.name}_{time}")
        relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{self.thermal_unit.name}_{time}")

        # Power bounds and startup parameters
        q_upper = self.maximum_power.get_value(time)
        q_lower = self.minimum_power.get_value(time)
        maximum_automated = get_maximum_automated(self)

        # Startup gradient parameters
        q_min = self.minimum_power.max()  # Get the minimum power without reserve requirements
        q_step = q_min / self._T_start

        # A. CONSTRAINTS ON THE AUXILIARY VARIABLES

        # Constraints on turned_on (entering START state) - eq. (3)
        model.add_constraint(turned_on_var <= 1 - off_var)
        model.add_constraint(turned_on_var <= off_prev_var)
        model.add_constraint(turned_on_var >= off_prev_var - off_var)

        # Constraints on turned_off (entering OFF state) - eq. (4)
        # Since T_stop = 0, turned_off is when entering OFF directly
        model.add_constraint(turned_off_var <= 1 - off_prev_var)
        model.add_constraint(turned_off_var <= off_var)
        model.add_constraint(turned_off_var >= off_var - off_prev_var)

        # B. CONSTRAINTS ON THE STATE VARIABLES

        # Mutual exclusion constraint - includes START state - eq. (11)
        model.add_constraint(off_var + on_up_var + on_down_var + start_var == 1)

        # Transition constraints
        # Transitions from ON_UP and ON_DOWN to START are forbidden - eq. (12)
        model.add_constraint(on_up_prev_var + start_var <= 1)
        model.add_constraint(on_down_prev_var + start_var <= 1)

        # Transition from START to OFF is forbidden - eq. (13)
        model.add_constraint(start_prev_var + off_var <= 1)

        # Direct transitions from OFF to ON_UP and ON_DOWN are forbidden - eq. (17)
        model.add_constraint(off_prev_var + on_up_var <= 1)
        model.add_constraint(off_prev_var + on_down_var <= 1)

        # Eviction constraint - forces unit to leave START state once startup is finished - eq. (16)
        if self._T_start >= 1:
            eviction_time = time - (self._T_start - 1) * parameters.timestep
            turned_on_eviction_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{eviction_time}")
            model.add_constraint(turned_on_eviction_var + start_var <= 1)

        # Minimum time constraints
        if self._T_on >= 2:
            for s in range(1, self._T_on):
                # eq. (27) with T_start > 0 - adjusted timing for startup
                local_time = time - (s + self._T_start) * parameters.timestep
                turned_on_local_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{local_time}")
                model.add_constraint(turned_on_local_var <= on_up_var + on_down_var)

        if self._T_off >= 2:
            for s in range(1, self._T_off):
                local_time = time - s * parameters.timestep
                turned_off_local_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{local_time}")
                model.add_constraint(turned_off_local_var <= off_var)

        # Startup ramp constraints - if T_start >= 2, enforce startup sequence
        if self._T_start >= 2:
            for s in range(1, self._T_start):
                local_time = time - s * parameters.timestep
                turned_on_local_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{local_time}")
                model.add_constraint(turned_on_local_var <= start_var)

        # C. CONSTRAINTS ON THE CONTROL VARIABLE

        # Reserve "fill up" constraints
        model.add_constraint(
            power_level_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
            <= q_upper + parameters.allowed_round_off_error
        )
        model.add_constraint(
            power_level_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
            >= q_upper - parameters.allowed_round_off_error
        )

        model.add_constraint(
            power_level_var
            - reserves_down_var
            - automated_reserves_down_var
            - unprovided_reserves_down_var
            + relaxed_reserves_var
            <= q_lower + parameters.allowed_round_off_error
        )
        model.add_constraint(
            power_level_var
            - reserves_down_var
            - automated_reserves_down_var
            - unprovided_reserves_down_var
            + relaxed_reserves_var
            >= q_lower - parameters.allowed_round_off_error
        )

        # Relaxed reserve disabling condition - only available when ON_UP or ON_DOWN
        model.add_constraint(relaxed_reserves_var <= q_lower * (1 - on_up_var - on_down_var))

        # Reserve availability constraints - no reserves during OFF or START states
        model.add_constraint(automated_reserves_up_var <= maximum_automated * (1 - off_var - start_var))
        model.add_constraint(automated_reserves_down_var <= maximum_automated * (1 - off_var - start_var))
        model.add_constraint(reserves_up_var <= q_upper * (1 - off_var - start_var))
        model.add_constraint(reserves_down_var <= q_upper * (1 - off_var - start_var))

        # Power output bounds
        # Lower bound - only for operational states (not START)
        model.add_constraint(power_level_var >= q_lower * (on_up_var + on_down_var))

        # Upper bound - includes startup ramping capability
        model.add_constraint(power_level_var <= q_upper * (on_up_var + on_down_var) + start_var * q_min)

        # Power gradients with startup considerations
        if time in parameters.thermal_op_times[:-1]:  # Not the last time step
            if self._Delta_Q > 0:  # Finite gradient
                # Upward gradient with startup ramping - eq. (33)
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q * on_up_prev_var + turned_on_var * q_step + start_prev_var * q_step
                )
                # Downward gradient with startup ramping - eq. (35)
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q * on_down_prev_var
                    + turned_on_var * q_step
                    + start_prev_var * q_step
                    - self._Delta_Q_unconstrained * turned_off_var
                )
            elif self._Delta_Q == 0:  # Infinite gradient
                # Upward unconstrained gradient with startup ramping - eq. (34)
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q_unconstrained * on_up_prev_var + turned_on_var * q_step + start_prev_var * q_step
                )
                # Downward unconstrained gradient with startup ramping - eq. (36)
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q_unconstrained * on_down_prev_var
                    + turned_on_var * q_step
                    + start_prev_var * q_step
                    - self._Delta_Q_unconstrained * turned_off_var
                )

        # Daily energy constraints (if applicable)
        if self.has_daily_energy_constraint:
            # This would need to be implemented at a higher level since it requires all time steps for a day
            pass

    def add_combination_5_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ) -> None:
        """Combination 5: T_stable >= 1, T_stop = T_start = 0"""
        # TODO: Move implementation from thermal.py
        """Combination 5: T_start = 0, T_stable >= 1, T_stop >= 1"""
        prev_time = time - parameters.timestep

        # Get variables
        off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
        on_up_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{time}")
        on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{time}")
        on_flat_var = model.get_variable(f"ON_FLAT_e_{self.thermal_unit.name}_at_{time}")
        stop_var = model.get_variable(f"STOP_e_{self.thermal_unit.name}_at_{time}")
        turned_on_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{time}")
        turned_off_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{time}")
        stable_var = model.get_variable(f"stable_at_{time}_e_{self.thermal_unit.name}")
        entered_up_var = model.get_variable(f"entered_up_at_{time}_e_{self.thermal_unit.name}")
        entered_down_var = model.get_variable(f"entered_down_at_{time}_e_{self.thermal_unit.name}")
        flat_down_stop_var = model.get_variable(f"flat_down_stop_at_{time}_e_{self.thermal_unit.name}")
        power_level_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{time}")

        # Gradient auxiliary variables
        up_grad_var = model.get_variable(f"UP_grad_at_{time}_for_e_{self.thermal_unit.name}")
        aux_up_grad_var = model.get_variable(f"aux_up_grad_at_{time}_e_{self.thermal_unit.name}")
        down_grad_var = model.get_variable(f"DOWN_grad_at_{time}_e_{self.thermal_unit.name}")
        aux_down_grad_var = model.get_variable(f"aux_down_grad_at_{time}_e_{self.thermal_unit.name}")
        dd_grad_var = model.get_variable(f"DD_grad_at_{time}_e_{self.thermal_unit.name}")

        # Previous time variables
        off_prev_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{prev_time}")
        on_up_prev_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{prev_time}")
        on_down_prev_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{prev_time}")
        on_flat_prev_var = model.get_variable(f"ON_FLAT_e_{self.thermal_unit.name}_at_{prev_time}")
        stop_prev_var = model.get_variable(f"STOP_e_{self.thermal_unit.name}_at_{prev_time}")
        power_prev_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{prev_time}")
        down_grad_prev_var = model.get_variable(f"DOWN_grad_at_{prev_time}_e_{self.thermal_unit.name}")

        # Reserve variables
        reserves_up_var = model.get_variable(f"reserves_up_{self.thermal_unit.name}_{time}")
        reserves_down_var = model.get_variable(f"reserves_down_{self.thermal_unit.name}_{time}")
        automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{self.thermal_unit.name}_{time}")
        automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{self.thermal_unit.name}_{time}")
        unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{self.thermal_unit.name}_{time}")
        unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{self.thermal_unit.name}_{time}")
        relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{self.thermal_unit.name}_{time}")

        # Power bounds and shutdown parameters
        q_upper = self.maximum_power.get_value(time)
        q_lower = self.minimum_power.get_value(time)
        maximum_automated = get_maximum_automated(self)

        # Shutdown gradient parameters
        q_min = self.minimum_power.max()
        q_step = q_min / self._T_stop

        # A. CONSTRAINTS ON THE AUXILIARY VARIABLES

        # Constraints on turned_on - eq. (3)
        model.add_constraint(turned_on_var <= 1 - off_var)
        model.add_constraint(turned_on_var <= off_prev_var)
        model.add_constraint(turned_on_var >= off_prev_var - off_var)

        # Constraints on turned_off (entering STOP state) - eq. (5)
        model.add_constraint(turned_off_var <= 1 - stop_prev_var)
        model.add_constraint(turned_off_var <= stop_var)
        model.add_constraint(turned_off_var >= stop_var - stop_prev_var)

        # Constraints on stable - eq. (6)
        model.add_constraint(stable_var <= 1 - on_flat_prev_var)
        model.add_constraint(stable_var <= on_flat_var)
        model.add_constraint(stable_var >= on_flat_var - on_flat_prev_var)

        # flat_down_stop auxiliary - eq. (22)
        # Detects FLAT(t-2) -> DOWN(t-1) -> STOP(t) path
        two_steps_ago = time - 2 * parameters.timestep
        on_flat_two_prev_var = model.get_variable(f"ON_FLAT_e_{self.thermal_unit.name}_at_{two_steps_ago}")
        model.add_constraint(flat_down_stop_var <= stop_var)
        model.add_constraint(flat_down_stop_var <= on_down_prev_var)
        model.add_constraint(flat_down_stop_var <= on_flat_two_prev_var)
        model.add_constraint(flat_down_stop_var >= stop_var + on_down_prev_var + on_flat_two_prev_var - 2)

        # Constraints on entered_up - eq. (7)
        model.add_constraint(entered_up_var <= 1 - on_up_prev_var)
        model.add_constraint(entered_up_var <= on_up_var)
        model.add_constraint(entered_up_var >= on_up_var - on_up_prev_var)

        # Constraints on entered_down - eq. (8)
        model.add_constraint(entered_down_var <= 1 - on_down_prev_var)
        model.add_constraint(entered_down_var <= on_down_var)
        model.add_constraint(entered_down_var >= on_down_var - on_down_prev_var)

        # UP and DOWN "semi-continuous" variables for the gradient
        # First stage: tilde_U and tilde_D (aux_up_grad and aux_down_grad) - eq. (28) and (30)
        # tilde_U (aux_up_grad)
        model.add_constraint(aux_up_grad_var <= q_upper * on_up_prev_var)
        model.add_constraint(aux_up_grad_var >= q_lower * on_up_prev_var)
        model.add_constraint(aux_up_grad_var <= power_level_var - power_prev_var - q_lower * (1 - on_up_prev_var))
        model.add_constraint(aux_up_grad_var >= power_level_var - power_prev_var - q_upper * (1 - on_up_prev_var))

        # tilde_D (aux_down_grad)
        model.add_constraint(aux_down_grad_var <= q_upper * on_down_prev_var)
        model.add_constraint(aux_down_grad_var >= q_lower * on_down_prev_var)
        model.add_constraint(aux_down_grad_var <= power_level_var - power_prev_var - q_lower * (1 - on_down_prev_var))
        model.add_constraint(aux_down_grad_var >= power_level_var - power_prev_var - q_upper * (1 - on_down_prev_var))

        # Second stage: U and D (up_grad and down_grad) - eq. (27) and (29)
        # U (up_grad)
        model.add_constraint(up_grad_var <= q_upper * on_up_var)
        model.add_constraint(up_grad_var >= q_lower * on_up_var)
        model.add_constraint(up_grad_var <= aux_up_grad_var - q_lower * (1 - on_up_var))
        model.add_constraint(up_grad_var >= aux_up_grad_var - q_upper * (1 - on_up_var))

        # D (down_grad)
        model.add_constraint(down_grad_var <= q_upper * on_down_var)
        model.add_constraint(down_grad_var >= q_lower * on_down_var)
        model.add_constraint(down_grad_var <= aux_down_grad_var - q_lower * (1 - on_down_var))
        model.add_constraint(down_grad_var >= aux_down_grad_var - q_upper * (1 - on_down_var))

        # DD Gradient auxiliary - eq. (23)
        # Detects if unit is to be stopped at t+1 after being in DOWN state at t and t-1
        if time in parameters.thermal_op_times[:-1]:  # Not the last time step
            model.add_constraint(dd_grad_var <= q_upper * stop_var)
            model.add_constraint(dd_grad_var >= q_lower * stop_var)
            model.add_constraint(dd_grad_var <= down_grad_prev_var - q_lower * (1 - stop_var))
            model.add_constraint(dd_grad_var >= down_grad_prev_var - q_upper * (1 - stop_var))

        # B. CONSTRAINTS ON THE STATE VARIABLES

        # Mutual exclusion constraint - 5 states - eq. (9)
        model.add_constraint(off_var + on_up_var + on_down_var + on_flat_var + stop_var == 1)

        # Transition constraints - eq. (25)
        # UP-DOWN and DOWN-UP transitions are forbidden
        model.add_constraint(on_up_prev_var + on_down_var <= 1)
        model.add_constraint(on_down_prev_var + on_up_var <= 1)
        # ON_XX to OFF transitions are forbidden
        model.add_constraint(on_up_prev_var + off_var <= 1)
        model.add_constraint(on_down_prev_var + off_var <= 1)

        # STOP to ON transitions are forbidden - eq. (13)
        model.add_constraint(stop_prev_var + on_flat_var <= 1)
        model.add_constraint(stop_prev_var + on_down_var <= 1)
        model.add_constraint(stop_prev_var + on_up_var <= 1)

        # ON_UP to STOP transition is forbidden - eq. (21)
        model.add_constraint(on_up_prev_var + stop_var <= 1)
        # OFF to STOP transition is forbidden - eq. (12)
        model.add_constraint(off_prev_var + stop_var <= 1)

        # Eviction constraint - unit must leave STOP state after T_stop time steps - eq. (19)
        if self._T_stop > 1:
            eviction_time = time - (self._T_stop - 1) * parameters.timestep
            turned_off_eviction_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{eviction_time}")
            model.add_constraint(turned_off_eviction_var + stop_var <= 1)

        # Minimum time constraints
        if self._T_on >= 2:
            for s in range(1, self._T_on):
                # eq. (31) with T_start = 0
                local_time = time - s * parameters.timestep
                turned_on_local_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{local_time}")
                model.add_constraint(turned_on_local_var <= on_up_var + on_down_var + on_flat_var)

        if self._T_off >= 2:
            for s in range(1, self._T_off):
                # eq. (32) with T_stop > 0 - adjusted timing for shutdown
                local_time = time - (s + self._T_stop) * parameters.timestep
                turned_off_local_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{local_time}")
                model.add_constraint(turned_off_local_var <= off_var)

        if self._T_stable >= 2:
            for s in range(1, self._T_stable - 1):
                # eq. (26)
                local_time = time - s * parameters.timestep
                stable_local_var = model.get_variable(f"stable_at_{local_time}_e_{self.thermal_unit.name}")
                model.add_constraint(stable_local_var <= on_flat_var)

        # Shutdown ramp constraints - eq. (24)
        if self._T_stop >= 2:
            for s in range(1, self._T_stop - 1):
                local_time = time - s * parameters.timestep
                turned_off_local_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{local_time}")
                model.add_constraint(turned_off_local_var <= stop_var)

        # C. CONSTRAINTS ON THE CONTROL VARIABLE

        # Reserve "fill up" constraints
        model.add_constraint(
            power_level_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
            <= q_upper + parameters.allowed_round_off_error
        )
        model.add_constraint(
            power_level_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
            >= q_upper - parameters.allowed_round_off_error
        )

        model.add_constraint(
            power_level_var
            - reserves_down_var
            - automated_reserves_down_var
            - unprovided_reserves_down_var
            + relaxed_reserves_var
            <= q_lower + parameters.allowed_round_off_error
        )
        model.add_constraint(
            power_level_var
            - reserves_down_var
            - automated_reserves_down_var
            - unprovided_reserves_down_var
            + relaxed_reserves_var
            >= q_lower - parameters.allowed_round_off_error
        )

        # Relaxed reserve disabling condition - eq. (43)
        model.add_constraint(relaxed_reserves_var <= q_lower * (1 - on_up_var - on_flat_var - on_down_var))

        # Reserve availability constraints - eq. (44)
        model.add_constraint(automated_reserves_up_var <= maximum_automated * (1 - off_var - stop_var))
        model.add_constraint(automated_reserves_down_var <= maximum_automated * (1 - off_var - stop_var))
        # Manual reserves only available in FLAT state
        model.add_constraint(reserves_up_var <= q_upper * (1 - on_up_var - on_down_var - off_var - stop_var))
        model.add_constraint(reserves_down_var <= q_upper * (1 - on_up_var - on_down_var - off_var - stop_var))

        # Power output bounds with shutdown gradient
        # Lower bound with shutdown ramping
        model.add_constraint(
            power_level_var >= q_lower * (on_up_var + on_down_var + on_flat_var) + turned_off_var * (q_min - q_step)
        )
        # Upper bound with shutdown ramping
        model.add_constraint(
            power_level_var
            <= q_upper * (on_up_var + on_down_var + on_flat_var) + stop_var * q_min - turned_off_var * q_step
        )

        # Power gradients with complex auxiliary variables
        if time in parameters.thermal_op_times[:-1]:  # Not the last time step
            if self._Delta_Q > 0:  # Finite gradient
                # Upward gradient - eq. (33)
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q * entered_up_var
                    + up_grad_var
                    + down_grad_var
                    - q_step * turned_off_var
                    - stop_prev_var * q_step
                    + self._Delta_Q_unconstrained * turned_on_var
                    - dd_grad_var
                )
                # Downward gradient - eq. (35)
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q * entered_down_var
                    + up_grad_var
                    + down_grad_var
                    - q_step * turned_off_var
                    - stop_prev_var * q_step
                    + flat_down_stop_var * self._Delta_Q
                    - dd_grad_var
                )
            elif self._Delta_Q == 0:  # Infinite gradient
                # Upward unconstrained gradient - eq. (34)
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q_unconstrained * entered_up_var
                    + up_grad_var
                    + down_grad_var
                    - q_step * turned_off_var
                    - stop_prev_var * q_step
                    + self._Delta_Q_unconstrained * turned_on_var
                )
                # Downward unconstrained gradient - eq. (36)
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q_unconstrained * entered_down_var
                    + up_grad_var
                    + down_grad_var
                    - q_step * turned_off_var
                    - stop_prev_var * q_step
                    + flat_down_stop_var * self._Delta_Q_unconstrained
                    - dd_grad_var
                )

        # Daily energy constraints (if applicable)
        if self.has_daily_energy_constraint:
            # This would need to be implemented at a higher level since it requires all time steps for a day
            pass

    def add_combination_6_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ) -> None:
        """Combination 6: T_stop >= 1, T_stable >= 1, T_start = 0"""
        prev_time = time - parameters.timestep

        # Get variables
        off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
        on_up_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{time}")
        on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{time}")
        on_flat_var = model.get_variable(f"ON_FLAT_e_{self.thermal_unit.name}_at_{time}")
        start_var = model.get_variable(f"ON_START_e_{self.thermal_unit.name}_at_{time}")
        turned_on_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{time}")
        turned_off_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{time}")
        stable_var = model.get_variable(f"stable_at_{time}_e_{self.thermal_unit.name}")
        entered_up_var = model.get_variable(f"entered_up_at_{time}_e_{self.thermal_unit.name}")
        entered_down_var = model.get_variable(f"entered_down_at_{time}_e_{self.thermal_unit.name}")
        power_level_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{time}")

        # Gradient auxiliary variables
        up_grad_var = model.get_variable(f"UP_grad_at_{time}_for_e_{self.thermal_unit.name}")
        aux_up_grad_var = model.get_variable(f"aux_up_grad_at_{time}_e_{self.thermal_unit.name}")
        down_grad_var = model.get_variable(f"DOWN_grad_at_{time}_e_{self.thermal_unit.name}")
        aux_down_grad_var = model.get_variable(f"aux_down_grad_at_{time}_e_{self.thermal_unit.name}")

        # Previous time variables
        off_prev_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{prev_time}")
        on_up_prev_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{prev_time}")
        on_down_prev_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{prev_time}")
        on_flat_prev_var = model.get_variable(f"ON_FLAT_e_{self.thermal_unit.name}_at_{prev_time}")
        start_prev_var = model.get_variable(f"ON_START_e_{self.thermal_unit.name}_at_{prev_time}")
        power_prev_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{prev_time}")
        up_grad_prev_var = model.get_variable(f"UP_grad_at_{prev_time}_for_e_{self.thermal_unit.name}")
        down_grad_prev_var = model.get_variable(f"DOWN_grad_at_{prev_time}_e_{self.thermal_unit.name}")

        # Reserve variables
        reserves_up_var = model.get_variable(f"reserves_up_{self.thermal_unit.name}_{time}")
        reserves_down_var = model.get_variable(f"reserves_down_{self.thermal_unit.name}_{time}")
        automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{self.thermal_unit.name}_{time}")
        automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{self.thermal_unit.name}_{time}")
        unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{self.thermal_unit.name}_{time}")
        unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{self.thermal_unit.name}_{time}")
        relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{self.thermal_unit.name}_{time}")

        # Power bounds and startup parameters
        q_upper = self.maximum_power.get_value(time)
        q_lower = self.minimum_power.get_value(time)
        maximum_automated = get_maximum_automated(self)

        # Startup gradient parameters
        q_min = self.minimum_power.max()
        q_step = q_min / self._T_start

        # A. CONSTRAINTS ON THE AUXILIARY VARIABLES

        # Constraints on turned_on - eq. (3)
        model.add_constraint(turned_on_var <= 1 - off_var)
        model.add_constraint(turned_on_var <= off_prev_var)
        model.add_constraint(turned_on_var >= off_prev_var - off_var)

        # Constraints on turned_off (entering OFF state directly) - eq. (4)
        # Since T_stop = 0, turned_off is when entering OFF directly
        model.add_constraint(turned_off_var <= 1 - off_prev_var)
        model.add_constraint(turned_off_var <= off_var)
        model.add_constraint(turned_off_var >= off_var - off_prev_var)

        # Constraints on stable - eq. (6)
        model.add_constraint(stable_var <= 1 - on_flat_prev_var)
        model.add_constraint(stable_var <= on_flat_var)
        model.add_constraint(stable_var >= on_flat_var - on_flat_prev_var)

        # Constraints on entered_up - eq. (7)
        model.add_constraint(entered_up_var <= 1 - on_up_prev_var)
        model.add_constraint(entered_up_var <= on_up_var)
        model.add_constraint(entered_up_var >= on_up_var - on_up_prev_var)

        # Constraints on entered_down - eq. (8)
        model.add_constraint(entered_down_var <= 1 - on_down_prev_var)
        model.add_constraint(entered_down_var <= on_down_var)
        model.add_constraint(entered_down_var >= on_down_var - on_down_prev_var)

        # UP and DOWN "semi-continuous" variables for the gradient
        # First stage: tilde_U and tilde_D (aux_up_grad and aux_down_grad) - eq. (28) and (30)
        # tilde_U (aux_up_grad)
        model.add_constraint(aux_up_grad_var <= q_upper * on_up_prev_var)
        model.add_constraint(aux_up_grad_var >= q_lower * on_up_prev_var)
        model.add_constraint(aux_up_grad_var <= power_level_var - power_prev_var - q_lower * (1 - on_up_prev_var))
        model.add_constraint(aux_up_grad_var >= power_level_var - power_prev_var - q_upper * (1 - on_up_prev_var))

        # tilde_D (aux_down_grad)
        model.add_constraint(aux_down_grad_var <= q_upper * on_down_prev_var)
        model.add_constraint(aux_down_grad_var >= q_lower * on_down_prev_var)
        model.add_constraint(aux_down_grad_var <= power_level_var - power_prev_var - q_lower * (1 - on_down_prev_var))
        model.add_constraint(aux_down_grad_var >= power_level_var - power_prev_var - q_upper * (1 - on_down_prev_var))

        # Second stage: U and D (up_grad and down_grad) - eq. (27) and (29)
        # U (up_grad)
        model.add_constraint(up_grad_var <= q_upper * on_up_var)
        model.add_constraint(up_grad_var >= q_lower * on_up_var)
        model.add_constraint(up_grad_var <= aux_up_grad_var - q_lower * (1 - on_up_var))
        model.add_constraint(up_grad_var >= aux_up_grad_var - q_upper * (1 - on_up_var))

        # D (down_grad)
        model.add_constraint(down_grad_var <= q_upper * on_down_var)
        model.add_constraint(down_grad_var >= q_lower * on_down_var)
        model.add_constraint(down_grad_var <= aux_down_grad_var - q_lower * (1 - on_down_var))
        model.add_constraint(down_grad_var >= aux_down_grad_var - q_upper * (1 - on_down_var))

        # B. CONSTRAINTS ON THE STATE VARIABLES

        # Mutual exclusion constraint - 5 states - eq. (9)
        model.add_constraint(off_var + on_up_var + on_down_var + on_flat_var + start_var == 1)

        # Transition constraints - eq. (25)
        # UP-DOWN and DOWN-UP transitions are forbidden
        model.add_constraint(on_up_prev_var + on_down_var <= 1)
        model.add_constraint(on_down_prev_var + on_up_var <= 1)

        # Constraints involving START and OFF - eq. (10)
        model.add_constraint(on_up_prev_var + start_var <= 1)
        model.add_constraint(on_down_prev_var + start_var <= 1)
        model.add_constraint(on_flat_prev_var + start_var <= 1)

        # START to OFF transition is forbidden - eq. (11)
        model.add_constraint(start_prev_var + off_var <= 1)

        # Direct transitions from OFF to operational states are forbidden - eq. (15)
        model.add_constraint(off_prev_var + on_up_var <= 1)
        model.add_constraint(off_prev_var + on_down_var <= 1)
        model.add_constraint(off_prev_var + on_flat_var <= 1)

        # Eviction constraint - forces unit to leave START state after T_start time steps - eq. (16)
        if self._T_start >= 1:
            eviction_time = time - (self._T_start - 1) * parameters.timestep
            turned_on_eviction_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{eviction_time}")
            model.add_constraint(turned_on_eviction_var + start_var <= 1)

        # Minimum time constraints
        if self._T_on >= 2:
            for s in range(1, self._T_on):
                # eq. (31) with T_start > 0 - adjusted timing for startup
                local_time = time - (s + self._T_start) * parameters.timestep
                turned_on_local_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{local_time}")
                model.add_constraint(turned_on_local_var <= on_up_var + on_down_var + on_flat_var)

        if self._T_off >= 2:
            for s in range(1, self._T_off):
                # eq. (32) with T_stop = 0
                local_time = time - s * parameters.timestep
                turned_off_local_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{local_time}")
                model.add_constraint(turned_off_local_var <= off_var)

        if self._T_stable >= 2:
            for s in range(1, self._T_stable - 1):
                # eq. (26)
                local_time = time - s * parameters.timestep
                stable_local_var = model.get_variable(f"stable_at_{local_time}_e_{self.thermal_unit.name}")
                model.add_constraint(stable_local_var <= on_flat_var)

        # Startup ramp constraints - eq. (17)
        if self._T_start >= 2:
            for s in range(1, self._T_start):
                local_time = time - s * parameters.timestep
                turned_on_local_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{local_time}")
                model.add_constraint(turned_on_local_var <= start_var)

        # C. CONSTRAINTS ON THE CONTROL VARIABLE

        # Reserve "fill up" constraints
        model.add_constraint(
            power_level_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
            <= q_upper + parameters.allowed_round_off_error
        )
        model.add_constraint(
            power_level_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
            >= q_upper - parameters.allowed_round_off_error
        )

        model.add_constraint(
            power_level_var
            - reserves_down_var
            - automated_reserves_down_var
            - unprovided_reserves_down_var
            + relaxed_reserves_var
            <= q_lower + parameters.allowed_round_off_error
        )
        model.add_constraint(
            power_level_var
            - reserves_down_var
            - automated_reserves_down_var
            - unprovided_reserves_down_var
            + relaxed_reserves_var
            >= q_lower - parameters.allowed_round_off_error
        )

        # Relaxed reserve disabling condition - eq. (43)
        model.add_constraint(relaxed_reserves_var <= q_lower * (1 - on_up_var - on_flat_var - on_down_var))

        # Reserve availability constraints - eq. (44)
        model.add_constraint(automated_reserves_up_var <= maximum_automated * (1 - off_var - start_var))
        model.add_constraint(automated_reserves_down_var <= maximum_automated * (1 - off_var - start_var))
        # Manual reserves only available in FLAT state (not during ramping or startup)
        model.add_constraint(reserves_up_var <= q_upper * (1 - on_up_var - on_down_var - off_var - start_var))
        model.add_constraint(reserves_down_var <= q_upper * (1 - on_up_var - on_down_var - off_var - start_var))

        # Power output bounds
        # Lower bound - only for operational states (not START)
        model.add_constraint(power_level_var >= q_lower * (on_up_var + on_down_var + on_flat_var))
        # Upper bound - includes startup ramping capability
        model.add_constraint(power_level_var <= q_upper * (on_up_var + on_down_var + on_flat_var) + start_var * q_min)

        # Power gradients with startup considerations and gradient auxiliary variables
        if time in parameters.thermal_op_times[:-1]:  # Not the last time step
            if self._Delta_Q > 0:  # Finite gradient
                # Upward gradient with startup ramping - eq. (33)
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q * entered_up_var
                    + up_grad_prev_var
                    + down_grad_prev_var
                    + q_step * turned_on_var
                    + start_prev_var * q_step
                )
                # Downward gradient with startup ramping - eq. (35)
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q * entered_down_var
                    + up_grad_prev_var
                    + down_grad_prev_var
                    - self._Delta_Q_unconstrained * turned_off_var
                    + q_step * turned_on_var
                    + start_prev_var * q_step
                )
            elif self._Delta_Q == 0:  # Infinite gradient
                # Upward unconstrained gradient with startup ramping - eq. (34)
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q_unconstrained * entered_up_var
                    + up_grad_prev_var
                    + down_grad_prev_var
                    + q_step * turned_on_var
                    + start_prev_var * q_step
                )
                # Downward unconstrained gradient with startup ramping - eq. (36)
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q_unconstrained * entered_down_var
                    + up_grad_prev_var
                    + down_grad_prev_var
                    - self._Delta_Q_unconstrained * turned_off_var
                    + q_step * turned_on_var
                    + start_prev_var * q_step
                )

        # Daily energy constraints (if applicable)
        if self.has_daily_energy_constraint:
            # This would need to be implemented at a higher level since it requires all time steps for a day
            pass

    def add_combination_7_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ) -> None:
        """Combination 7: T_start >= 1, T_stable >= 1, T_stop = 0"""
        prev_time = time - parameters.timestep

        # Get variables
        off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
        on_up_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{time}")
        on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{time}")
        start_var = model.get_variable(f"ON_START_e_{self.thermal_unit.name}_at_{time}")
        stop_var = model.get_variable(f"STOP_e_{self.thermal_unit.name}_at_{time}")
        turned_on_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{time}")
        turned_off_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{time}")
        down_to_stop_var = model.get_variable(f"down_to_stop_grad_at_{time}_e_{self.thermal_unit.name}")
        power_level_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{time}")

        # Previous time variables
        off_prev_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{prev_time}")
        on_up_prev_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{prev_time}")
        on_down_prev_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{prev_time}")
        start_prev_var = model.get_variable(f"ON_START_e_{self.thermal_unit.name}_at_{prev_time}")
        stop_prev_var = model.get_variable(f"STOP_e_{self.thermal_unit.name}_at_{prev_time}")
        power_prev_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{prev_time}")

        # Reserve variables
        reserves_up_var = model.get_variable(f"reserves_up_{self.thermal_unit.name}_{time}")
        reserves_down_var = model.get_variable(f"reserves_down_{self.thermal_unit.name}_{time}")
        automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{self.thermal_unit.name}_{time}")
        automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{self.thermal_unit.name}_{time}")
        unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{self.thermal_unit.name}_{time}")
        unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{self.thermal_unit.name}_{time}")
        relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{self.thermal_unit.name}_{time}")

        # Power bounds and gradient parameters
        q_upper = self.maximum_power.get_value(time)
        q_lower = self.minimum_power.get_value(time)
        maximum_automated = get_maximum_automated(self)

        # Dual gradient parameters for startup and shutdown
        q_min = self.minimum_power.max()
        q_step_up = q_min / self._T_start  # Startup gradient step
        q_step_down = q_min / self._T_stop  # Shutdown gradient step

        # A. CONSTRAINTS ON THE AUXILIARY VARIABLES

        # Constraints on turned_on - eq. (3)
        model.add_constraint(turned_on_var <= 1 - off_var)
        model.add_constraint(turned_on_var <= off_prev_var)
        model.add_constraint(turned_on_var >= off_prev_var - off_var)

        # Constraints on turned_off (entering STOP state) - eq. (5)
        model.add_constraint(turned_off_var <= 1 - stop_prev_var)
        model.add_constraint(turned_off_var <= stop_var)
        model.add_constraint(turned_off_var >= stop_var - stop_prev_var)

        # Constraints on down_to_stop - eq. (20)
        # Detects ON_DOWN(t-1) -> STOP(t) transition
        model.add_constraint(down_to_stop_var <= stop_var)
        model.add_constraint(down_to_stop_var <= on_down_prev_var)
        model.add_constraint(down_to_stop_var >= stop_var + on_down_prev_var - 1)

        # B. CONSTRAINTS ON THE STATE VARIABLES

        # Mutual exclusion constraint - 5 states - eq. (11)
        model.add_constraint(off_var + on_up_var + on_down_var + stop_var + start_var == 1)

        # Complex transition constraints
        # STOP to ON transitions are forbidden - eq. (15)
        model.add_constraint(stop_prev_var + on_up_var <= 1)
        model.add_constraint(stop_prev_var + on_down_var <= 1)

        # OFF to STOP transition is forbidden - eq. (14)
        model.add_constraint(off_prev_var + stop_var <= 1)

        # ON to OFF transitions are forbidden - eq. (19)
        model.add_constraint(on_up_prev_var + off_var <= 1)
        model.add_constraint(on_down_prev_var + off_var <= 1)

        # ON to START transitions are forbidden - eq. (12)
        model.add_constraint(on_up_prev_var + start_var <= 1)
        model.add_constraint(on_down_prev_var + start_var <= 1)

        # START to OFF transition is forbidden - eq. (13)
        model.add_constraint(start_prev_var + off_var <= 1)

        # START to STOP and STOP to START transitions are forbidden - eq. (16)
        model.add_constraint(start_prev_var + stop_var <= 1)
        model.add_constraint(stop_prev_var + start_var <= 1)

        # Direct OFF to ON transitions are forbidden - eq. (17)
        model.add_constraint(off_prev_var + on_up_var <= 1)
        model.add_constraint(off_prev_var + on_down_var <= 1)

        # Eviction constraints
        # START eviction - forces unit to leave START state after T_start time steps - eq. (16)
        if self._T_start >= 1:
            start_eviction_time = time - (self._T_start - 1) * parameters.timestep
            turned_on_start_eviction_var = model.get_variable(
                f"t_on_of_e_{self.thermal_unit.name}_at_{start_eviction_time}"
            )
            model.add_constraint(turned_on_start_eviction_var + start_var <= 1)

        # STOP eviction - forces unit to leave STOP state after T_stop time steps - eq. (19)
        if self._T_stop > 1:
            stop_eviction_time = time - (self._T_stop - 1) * parameters.timestep
            turned_off_stop_eviction_var = model.get_variable(
                f"t_off_of_e_{self.thermal_unit.name}_at_{stop_eviction_time}"
            )
            model.add_constraint(turned_off_stop_eviction_var + stop_var <= 1)

        # Minimum time constraints
        if self._T_on >= 2:
            for s in range(1, self._T_on):
                # eq. (27) with T_start > 0 - adjusted timing for startup
                local_time = time - (s + self._T_start) * parameters.timestep
                turned_on_local_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{local_time}")
                model.add_constraint(turned_on_local_var <= on_up_var + on_down_var)

        if self._T_off >= 2:
            for s in range(1, self._T_off):
                # eq. (28) with T_stop > 0 - adjusted timing for shutdown
                local_time = time - (s + self._T_stop) * parameters.timestep
                turned_off_local_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{local_time}")
                model.add_constraint(turned_off_local_var <= off_var)

        # Shutdown ramp constraints - eq. (19)
        if self._T_stop >= 2:
            for s in range(1, self._T_stop - 1):
                local_time = time - s * parameters.timestep
                turned_off_local_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{local_time}")
                model.add_constraint(turned_off_local_var <= stop_var)

        # Startup ramp constraints - eq. (18)
        if self._T_start >= 2:
            for s in range(1, self._T_start):
                local_time = time - s * parameters.timestep
                turned_on_local_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{local_time}")
                model.add_constraint(turned_on_local_var <= start_var)

        # C. CONSTRAINTS ON THE CONTROL VARIABLE

        # Reserve "fill up" constraints
        model.add_constraint(
            power_level_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
            <= q_upper + parameters.allowed_round_off_error
        )
        model.add_constraint(
            power_level_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
            >= q_upper - parameters.allowed_round_off_error
        )

        model.add_constraint(
            power_level_var
            - reserves_down_var
            - automated_reserves_down_var
            - unprovided_reserves_down_var
            + relaxed_reserves_var
            <= q_lower + parameters.allowed_round_off_error
        )
        model.add_constraint(
            power_level_var
            - reserves_down_var
            - automated_reserves_down_var
            - unprovided_reserves_down_var
            + relaxed_reserves_var
            >= q_lower - parameters.allowed_round_off_error
        )

        # Relaxed reserve disabling condition - eq. (43)
        model.add_constraint(relaxed_reserves_var <= q_lower * (1 - on_up_var - on_down_var))

        # Reserve availability constraints - eq. (44)
        # No reserves during OFF, START, or STOP states
        model.add_constraint(automated_reserves_up_var <= maximum_automated * (1 - off_var - start_var - stop_var))
        model.add_constraint(automated_reserves_down_var <= maximum_automated * (1 - off_var - start_var - stop_var))
        model.add_constraint(reserves_up_var <= q_upper * (1 - off_var - start_var - stop_var))
        model.add_constraint(reserves_down_var <= q_upper * (1 - off_var - start_var - stop_var))

        # Power output bounds with dual gradient ramping - eq. (29) and (30)
        # Lower bound with shutdown ramping
        model.add_constraint(
            power_level_var >= q_lower * (on_up_var + on_down_var) + turned_off_var * (q_min - q_step_down)
        )
        # Upper bound with both startup and shutdown ramping
        model.add_constraint(
            power_level_var
            <= q_upper * (on_up_var + on_down_var) + stop_var * q_min + start_var * q_min - turned_off_var * q_step_down
        )

        # Power gradients with dual gradient parameters
        if time in parameters.thermal_op_times[:-1]:  # Not the last time step
            if self._Delta_Q > 0:  # Finite gradient
                # Upward gradient - eq. (33)
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q * on_up_prev_var
                    - turned_off_var * q_step_down
                    - stop_prev_var * q_step_down
                    + turned_on_var * q_step_up
                    + start_prev_var * q_step_up
                )
                # Downward gradient - eq. (35)
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q * on_down_prev_var
                    - turned_off_var * q_step_down
                    - stop_prev_var * q_step_down
                    + down_to_stop_var * self._Delta_Q
                    + turned_on_var * q_step_up
                    + start_prev_var * q_step_up
                )
            elif self._Delta_Q == 0:  # Infinite gradient
                # Upward unconstrained gradient - eq. (34)
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q_unconstrained * on_up_prev_var
                    - turned_off_var * q_step_down
                    - stop_prev_var * q_step_down
                    + turned_on_var * q_step_up
                    + start_prev_var * q_step_up
                )
                # Downward unconstrained gradient - eq. (36)
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q_unconstrained * on_down_prev_var
                    - turned_off_var * q_step_down
                    - stop_prev_var * q_step_down
                    + down_to_stop_var * self._Delta_Q_unconstrained
                    + turned_on_var * q_step_up
                    + start_prev_var * q_step_up
                )

        # Daily energy constraints (if applicable)
        if self.has_daily_energy_constraint:
            # This would need to be implemented at a higher level since it requires all time steps for a day
            pass

    def add_combination_8_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ) -> None:
        """Combination 8: T_stop >= 1, T_start >= 1, T_stable >= 1 (ALL constraints)"""
        prev_time = time - parameters.timestep

        # Get variables
        off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
        on_up_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{time}")
        on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{time}")
        on_flat_var = model.get_variable(f"ON_FLAT_e_{self.thermal_unit.name}_at_{time}")
        start_var = model.get_variable(f"ON_START_e_{self.thermal_unit.name}_at_{time}")
        stop_var = model.get_variable(f"STOP_e_{self.thermal_unit.name}_at_{time}")
        turned_on_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{time}")
        turned_off_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{time}")
        stable_var = model.get_variable(f"stable_at_{time}_e_{self.thermal_unit.name}")
        entered_up_var = model.get_variable(f"entered_up_at_{time}_e_{self.thermal_unit.name}")
        entered_down_var = model.get_variable(f"entered_down_at_{time}_e_{self.thermal_unit.name}")
        flat_down_stop_var = model.get_variable(f"flat_down_stop_at_{time}_e_{self.thermal_unit.name}")
        power_level_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{time}")

        # Gradient auxiliary variables
        up_grad_var = model.get_variable(f"UP_grad_at_{time}_for_e_{self.thermal_unit.name}")
        aux_up_grad_var = model.get_variable(f"aux_up_grad_at_{time}_e_{self.thermal_unit.name}")
        down_grad_var = model.get_variable(f"DOWN_grad_at_{time}_e_{self.thermal_unit.name}")
        aux_down_grad_var = model.get_variable(f"aux_down_grad_at_{time}_e_{self.thermal_unit.name}")

        # Previous time variables
        off_prev_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{prev_time}")
        on_up_prev_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{prev_time}")
        on_down_prev_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{prev_time}")
        on_flat_prev_var = model.get_variable(f"ON_FLAT_e_{self.thermal_unit.name}_at_{prev_time}")
        start_prev_var = model.get_variable(f"ON_START_e_{self.thermal_unit.name}_at_{prev_time}")
        stop_prev_var = model.get_variable(f"STOP_e_{self.thermal_unit.name}_at_{prev_time}")
        power_prev_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{prev_time}")
        up_grad_prev_var = model.get_variable(f"UP_grad_at_{prev_time}_for_e_{self.thermal_unit.name}")
        down_grad_prev_var = model.get_variable(f"DOWN_grad_at_{prev_time}_e_{self.thermal_unit.name}")
        dd_grad_prev_var = model.get_variable(f"DD_grad_at_{prev_time}_e_{self.thermal_unit.name}")

        # Reserve variables
        reserves_up_var = model.get_variable(f"reserves_up_{self.thermal_unit.name}_{time}")
        reserves_down_var = model.get_variable(f"reserves_down_{self.thermal_unit.name}_{time}")
        automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{self.thermal_unit.name}_{time}")
        automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{self.thermal_unit.name}_{time}")
        unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{self.thermal_unit.name}_{time}")
        unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{self.thermal_unit.name}_{time}")
        relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{self.thermal_unit.name}_{time}")

        # Power bounds and gradient parameters
        q_upper = self.maximum_power.get_value(time)
        q_lower = self.minimum_power.get_value(time)
        maximum_automated = get_maximum_automated(self)

        # Dual gradient parameters for startup and shutdown
        q_min = self.minimum_power.max()
        q_step_up = q_min / self._T_start  # Startup gradient step
        q_step_down = q_min / self._T_stop  # Shutdown gradient step

        # A. CONSTRAINTS ON THE AUXILIARY VARIABLES

        # Constraints on turned_on - eq. (3)
        model.add_constraint(turned_on_var <= 1 - off_var)
        model.add_constraint(turned_on_var <= off_prev_var)
        model.add_constraint(turned_on_var >= off_prev_var - off_var)

        # Constraints on turned_off (entering STOP state) - eq. (5)
        model.add_constraint(turned_off_var <= 1 - stop_prev_var)
        model.add_constraint(turned_off_var <= stop_var)
        model.add_constraint(turned_off_var >= stop_var - stop_prev_var)

        # Constraints on stable - eq. (6)
        model.add_constraint(stable_var <= 1 - on_flat_prev_var)
        model.add_constraint(stable_var <= on_flat_var)
        model.add_constraint(stable_var >= on_flat_var - on_flat_prev_var)

        # flat_down_stop auxiliary - eq. (22)
        # Detects FLAT(t-2) -> DOWN(t-1) -> STOP(t) path
        two_steps_ago = time - 2 * parameters.timestep
        on_flat_two_prev_var = model.get_variable(f"ON_FLAT_e_{self.thermal_unit.name}_at_{two_steps_ago}")
        model.add_constraint(flat_down_stop_var <= stop_var)
        model.add_constraint(flat_down_stop_var <= on_down_prev_var)
        model.add_constraint(flat_down_stop_var <= on_flat_two_prev_var)
        model.add_constraint(flat_down_stop_var >= stop_var + on_down_prev_var + on_flat_two_prev_var - 2)

        # Constraints on entered_up - eq. (7)
        model.add_constraint(entered_up_var <= 1 - on_up_prev_var)
        model.add_constraint(entered_up_var <= on_up_var)
        model.add_constraint(entered_up_var >= on_up_var - on_up_prev_var)

        # Constraints on entered_down - eq. (8)
        model.add_constraint(entered_down_var <= 1 - on_down_prev_var)
        model.add_constraint(entered_down_var <= on_down_var)
        model.add_constraint(entered_down_var >= on_down_var - on_down_prev_var)

        # UP and DOWN "semi-continuous" variables for the gradient
        # First stage: tilde_U and tilde_D (aux_up_grad and aux_down_grad) - eq. (28) and (30)
        # tilde_U (aux_up_grad)
        model.add_constraint(aux_up_grad_var <= q_upper * on_up_prev_var)
        model.add_constraint(aux_up_grad_var >= q_lower * on_up_prev_var)
        model.add_constraint(aux_up_grad_var <= power_level_var - power_prev_var - q_lower * (1 - on_up_prev_var))
        model.add_constraint(aux_up_grad_var >= power_level_var - power_prev_var - q_upper * (1 - on_up_prev_var))

        # tilde_D (aux_down_grad)
        model.add_constraint(aux_down_grad_var <= q_upper * on_down_prev_var)
        model.add_constraint(aux_down_grad_var >= q_lower * on_down_prev_var)
        model.add_constraint(aux_down_grad_var <= power_level_var - power_prev_var - q_lower * (1 - on_down_prev_var))
        model.add_constraint(aux_down_grad_var >= power_level_var - power_prev_var - q_upper * (1 - on_down_prev_var))

        # Second stage: U and D (up_grad and down_grad) - eq. (27) and (29)
        # U (up_grad)
        model.add_constraint(up_grad_var <= q_upper * on_up_var)
        model.add_constraint(up_grad_var >= q_lower * on_up_var)
        model.add_constraint(up_grad_var <= aux_up_grad_var - q_lower * (1 - on_up_var))
        model.add_constraint(up_grad_var >= aux_up_grad_var - q_upper * (1 - on_up_var))

        # D (down_grad)
        model.add_constraint(down_grad_var <= q_upper * on_down_var)
        model.add_constraint(down_grad_var >= q_lower * on_down_var)
        model.add_constraint(down_grad_var <= aux_down_grad_var - q_lower * (1 - on_down_var))
        model.add_constraint(down_grad_var >= aux_down_grad_var - q_upper * (1 - on_down_var))

        # DD Gradient auxiliary - eq. (23)
        # Detects if unit is to be stopped at t+1 after being in DOWN state at t and t-1
        if time in parameters.thermal_op_times[:-1]:  # Not the last time step
            model.add_constraint(dd_grad_prev_var <= q_upper * stop_var)
            model.add_constraint(dd_grad_prev_var >= q_lower * stop_var)
            model.add_constraint(dd_grad_prev_var <= down_grad_prev_var - q_lower * (1 - stop_var))
            model.add_constraint(dd_grad_prev_var >= down_grad_prev_var - q_upper * (1 - stop_var))

        # B. CONSTRAINTS ON THE STATE VARIABLES

        # Mutual exclusion constraint - 6 states - eq. (9)
        model.add_constraint(off_var + on_up_var + on_down_var + on_flat_var + stop_var + start_var == 1)

        # Complex transition constraints - most comprehensive set
        # UP-DOWN and DOWN-UP transitions are forbidden - eq. (25)
        model.add_constraint(on_up_prev_var + on_down_var <= 1)
        model.add_constraint(on_down_prev_var + on_up_var <= 1)

        # STOP to ON transitions are forbidden - eq. (13)
        model.add_constraint(stop_prev_var + on_flat_var <= 1)
        model.add_constraint(stop_prev_var + on_down_var <= 1)
        model.add_constraint(stop_prev_var + on_up_var <= 1)

        # ON_UP to STOP transition is forbidden - eq. (21)
        model.add_constraint(on_up_prev_var + stop_var <= 1)

        # OFF to STOP transition is forbidden - eq. (12)
        model.add_constraint(off_prev_var + stop_var <= 1)

        # ON to START transitions are forbidden - eq. (10)
        model.add_constraint(on_up_prev_var + start_var <= 1)
        model.add_constraint(on_down_prev_var + start_var <= 1)
        model.add_constraint(on_flat_prev_var + start_var <= 1)

        # ON to OFF transitions are forbidden
        model.add_constraint(on_up_prev_var + off_var <= 1)
        model.add_constraint(on_down_prev_var + off_var <= 1)
        model.add_constraint(on_flat_prev_var + off_var <= 1)

        # START to OFF transition is forbidden - eq. (11)
        model.add_constraint(start_prev_var + off_var <= 1)

        # START to STOP and STOP to START transitions are forbidden - eq. (14)
        model.add_constraint(start_prev_var + stop_var <= 1)
        model.add_constraint(stop_prev_var + start_var <= 1)

        # Direct OFF to ON transitions are forbidden - eq. (15)
        model.add_constraint(off_prev_var + on_up_var <= 1)
        model.add_constraint(off_prev_var + on_flat_var <= 1)
        model.add_constraint(off_prev_var + on_down_var <= 1)

        # Eviction constraints
        # STOP eviction - forces unit to leave STOP state after T_stop time steps - eq. (19)
        if self._T_stop > 1:
            stop_eviction_time = time - (self._T_stop - 1) * parameters.timestep
            turned_off_stop_eviction_var = model.get_variable(
                f"t_off_of_e_{self.thermal_unit.name}_at_{stop_eviction_time}"
            )
            model.add_constraint(turned_off_stop_eviction_var + stop_var <= 1)

        # START eviction - forces unit to leave START state after T_start time steps - eq. (16)
        if self._T_start >= 1:
            start_eviction_time = time - (self._T_start - 1) * parameters.timestep
            turned_on_start_eviction_var = model.get_variable(
                f"t_on_of_e_{self.thermal_unit.name}_at_{start_eviction_time}"
            )
            model.add_constraint(turned_on_start_eviction_var + start_var <= 1)

        # Minimum time constraints with all adjustments
        if self._T_on >= 2:
            for s in range(1, self._T_on):
                # eq. (31) with T_start > 0 - adjusted timing for startup
                local_time = time - (s + self._T_start) * parameters.timestep
                turned_on_local_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{local_time}")
                model.add_constraint(turned_on_local_var <= on_up_var + on_down_var + on_flat_var)

        if self._T_off >= 2:
            for s in range(1, self._T_off):
                # eq. (32) with T_stop > 0 - adjusted timing for shutdown
                local_time = time - (s + self._T_stop) * parameters.timestep
                turned_off_local_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{local_time}")
                model.add_constraint(turned_off_local_var <= off_var)

        if self._T_stable >= 2:
            for s in range(1, self._T_stable - 1):
                # eq. (26)
                local_time = time - s * parameters.timestep
                stable_local_var = model.get_variable(f"stable_at_{local_time}_e_{self.thermal_unit.name}")
                model.add_constraint(stable_local_var <= on_flat_var)

        # Shutdown ramp constraints - eq. (24)
        if self._T_stop >= 2:
            for s in range(1, self._T_stop - 1):
                local_time = time - s * parameters.timestep
                turned_off_local_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{local_time}")
                model.add_constraint(turned_off_local_var <= stop_var)

        # Startup ramp constraints - eq. (17)
        if self._T_start >= 2:
            for s in range(1, self._T_start):
                local_time = time - s * parameters.timestep
                turned_on_local_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{local_time}")
                model.add_constraint(turned_on_local_var <= start_var)

        # C. CONSTRAINTS ON THE CONTROL VARIABLE

        # Reserve "fill up" constraints
        model.add_constraint(
            power_level_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
            <= q_upper + parameters.allowed_round_off_error
        )
        model.add_constraint(
            power_level_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
            >= q_upper - parameters.allowed_round_off_error
        )

        model.add_constraint(
            power_level_var
            - reserves_down_var
            - automated_reserves_down_var
            - unprovided_reserves_down_var
            + relaxed_reserves_var
            <= q_lower + parameters.allowed_round_off_error
        )
        model.add_constraint(
            power_level_var
            - reserves_down_var
            - automated_reserves_down_var
            - unprovided_reserves_down_var
            + relaxed_reserves_var
            >= q_lower - parameters.allowed_round_off_error
        )

        # Relaxed reserve disabling condition - eq. (43)
        model.add_constraint(relaxed_reserves_var <= q_lower * (1 - on_up_var - on_flat_var - on_down_var))

        # Reserve availability constraints - eq. (44)
        # No reserves during OFF, START, or STOP states
        model.add_constraint(automated_reserves_up_var <= maximum_automated * (1 - off_var - start_var - stop_var))
        model.add_constraint(automated_reserves_down_var <= maximum_automated * (1 - off_var - start_var - stop_var))
        # Manual reserves only available in FLAT state
        model.add_constraint(
            reserves_up_var <= q_upper * (1 - on_up_var - on_down_var - off_var - start_var - stop_var)
        )
        model.add_constraint(
            reserves_down_var <= q_upper * (1 - on_up_var - on_down_var - off_var - start_var - stop_var)
        )

        # Power output bounds with all ramping capabilities - eq. (29) and (30)
        # Lower bound with shutdown ramping
        model.add_constraint(
            power_level_var
            >= q_lower * (on_up_var + on_down_var + on_flat_var) + turned_off_var * (q_min - q_step_down)
        )
        # Upper bound with both startup and shutdown ramping
        model.add_constraint(
            power_level_var
            <= q_upper * (on_up_var + on_down_var + on_flat_var)
            + (stop_var + start_var) * q_min
            - turned_off_var * q_step_down
        )

        # Power gradients with all auxiliary variables - most complex gradient logic
        if time in parameters.thermal_op_times[:-1]:  # Not the last time step
            if self._Delta_Q > 0:  # Finite gradient
                # Upward gradient - eq. (33)
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q * entered_up_var
                    + up_grad_prev_var
                    + down_grad_prev_var
                    - turned_off_var * q_step_down
                    - stop_prev_var * q_step_down
                    + turned_on_var * q_step_up
                    + start_prev_var * q_step_up
                    - dd_grad_prev_var
                )
                # Downward gradient - eq. (35)
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q * entered_down_var
                    + up_grad_prev_var
                    + down_grad_prev_var
                    - turned_off_var * q_step_down
                    - stop_prev_var * q_step_down
                    + flat_down_stop_var * self._Delta_Q
                    - dd_grad_prev_var
                    + turned_on_var * q_step_up
                    + start_prev_var * q_step_up
                )
            elif self._Delta_Q == 0:  # Infinite gradient
                # Upward unconstrained gradient - eq. (34)
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q_unconstrained * entered_up_var
                    + up_grad_prev_var
                    + down_grad_prev_var
                    - turned_off_var * q_step_down
                    - stop_prev_var * q_step_down
                    + turned_on_var * q_step_up
                    + start_prev_var * q_step_up
                    - dd_grad_prev_var
                )
                # Downward unconstrained gradient - eq. (36)
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q_unconstrained * entered_down_var
                    + up_grad_prev_var
                    + down_grad_prev_var
                    - turned_off_var * q_step_down
                    - stop_prev_var * q_step_down
                    + flat_down_stop_var * self._Delta_Q_unconstrained
                    - dd_grad_prev_var
                    + turned_on_var * q_step_up
                    + start_prev_var * q_step_up
                )

        # Daily energy constraints (if applicable)
        if self.has_daily_energy_constraint:
            # This would need to be implemented at a higher level since it requires all time steps for a day
            pass
