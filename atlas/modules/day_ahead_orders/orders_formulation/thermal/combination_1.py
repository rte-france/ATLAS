"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import atlas.config as cfg
from atlas.modules.day_ahead_orders.orders_formulation.thermal.thermal_optimization_model import (
    ThermalOptimizationModel,
)


def execute(model: ThermalOptimizationModel, day_zero: bool) -> None:
    """Combination 1 : T_stop = model.T_stable = T_start = 0"""
    # In this case, there are three state variables and two auxiliary variables.
    # We review the initial conditions, then the constraints on the state variables
    # and finally the constraints on the power output.
    # A. INITIAL CONDITIONS

    if day_zero:
        # Remind the user how the program has been initialized
        if model.parameters.verbose:
            cfg.logger.info(f"Initial conditions of unit {model.thermal_unit.name} have been set as in equation (47).")

        for t in model.previous_time_frame:
            # Initial conditions on the power output
            model.q[t] = 0
            # Initial conditions on the state variables : the unit is OFF
            model.OFF.set_extended(t, 1)
            model.ON_UP.set_extended(t, 0)
            model.ON_DOWN.set_extended(t, 0)
            # Initial conditions on the auxiliary variables
            model.turned_on.set_extended(t, 0)
            model.turned_off[t] = 0
    else:
        # Initial condition on the power output
        for t in model.previous_time_frame:
            model.q[t] = model.last_power.get_value(t)

        # Initial conditions on the state variables
        # Only need to set one value, the mutual exclusion constraint being defined over the
        # whole extended time frame.
        for t in model.previous_time_frame:
            if model.last_power.get_value(t) > 0:
                model.OFF.set_extended(t, 0)
                model.ON_DOWN.set_extended(t, 1)
                model.ON_UP.set_extended(t, 1)
            else:
                model.OFF.set_extended(t, 1)
                model.ON_UP.set_extended(t, 0)
                model.ON_DOWN.set_extended(t, 0)

        # Initial conditions on the auxiliary variables
        for t in model.previous_time_frame:
            # Initialize all the values to 0
            model.turned_on.set_extended(t, 0)
            model.turned_off[t] = 0
            if not t == model.extended_start_date:
                # Reconstruct potential switches using the state variables
                t_prev = t - model.parameters.time_step
                # See if the unit has been turned off
                if model.OFF.get_extended_value(t) - model.OFF.get_extended_value(t_prev) == 1:
                    model.turned_off[t] = 1
                # Or turned on
                elif model.OFF.get_extended_value(t) - model.OFF.get_extended_value(t_prev) == -1:
                    model.turned_on.set_extended(t, 1)
                else:
                    model.turned_on.set_extended(t, 0)
                    model.turned_off[t] = 0

    # B. CONSTRAINTS ON THE AUXILIARY VARIABLES

    # These constraints define the auxiliary variables. In the first case, there are only two
    # of them : turned_on and turned_off.

    # Constraints on the indicator that the unit has started on t
    # Enforces equation (3)
    for t in model.time_frame:
        model.add_constraint(model.turned_on.get_value(t) <= 1 - model.OFF.get_value(t))
        model.add_constraint(model.turned_on.get_value(t) <= model.OFF.get_value(t - model.parameters.time_step))
        model.add_constraint(
            model.turned_on.get_value(t) >= model.OFF.get_value(t - model.parameters.time_step) - model.OFF.get_value(t)
        )

        # Constraints on turned_off
    # STOP is not defined in this case, so we enforce equation (4)
    for t in model.time_frame:
        model.add_constraint(model.turned_off[t] <= 1 - model.OFF.get_value(t - model.parameters.time_step))
        model.add_constraint(model.turned_off[t] <= model.OFF.get_value(t))
        model.add_constraint(
            model.turned_off[t] >= model.OFF.get_value(t) - model.OFF.get_value(t - model.parameters.time_step)
        )

    # C. CONSTRAINTS ON THE STATE VARIABLES

    # Mutual exclusion constraint
    for t in model.time_frame:
        # Defined over the whole time frame
        # Enforces eq. (9)
        model.add_constraint(model.OFF.get_value(t) + model.ON_UP.get_value(t) + model.ON_DOWN.get_value(t) == 1)

    # Transitions:
    # None. All transitions are allowed

    # Mininum time on and minimum time off constraints:
    # if model.T_on >= 2 or model.T_off >= 2, lock the unit in this state.
    if model.T_on >= 2:
        for t in model.time_frame:
            time_steps = range(1, model.T_on)  # Corresponds to the set {1, ..., model.T_on -1}
            for s in time_steps:  # Add the constraints given by eq. (31), here T_start = 0 so t - s - T_start = t - s
                t_minus_s = t - s * model.parameters.time_step
                model.add_constraint(
                    model.turned_on.get_value(t_minus_s) <= model.ON_UP.get_value(t) + model.ON_DOWN.get_value(t),
                    f"minimum_time_ON_{model.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                )

    if model.T_off >= 2:
        for t in model.time_frame:
            time_steps = range(1, model.T_off)  # Corresponds to the set {1, ..., model.T_off -1}
            for s in time_steps:  # Add the constraints given by eq. (32), here T_stop = 0 so t - s - T_stop = t - s
                t_minus_s = t - s * model.parameters.time_step
                model.add_constraint(
                    model.turned_off[t_minus_s] <= model.OFF.get_value(t),
                    f"minimum_time_OFF_{model.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                )

    # D. CONSTRAINTS ON THE CONTROL VARIABLE

    # Reserves requirements
    # We are in a case where there is no FLAT state, so manual reserves can be provided
    # as long as the unit is online.

    # Constraints on contractedDifference (eq. (40)) and on automatedContractedDifference (eq. (39))
    model.create_contracted_diff_constraints(
        model.time_frame,
        model.reserves_up_procured,
        model.reserves_down_procured,
        model.feasible_automated_reserves_up_procured,
        model.feasible_automated_reserves_down_procured,
    )

    # Upward and downward "fill up" constraints.
    model.create_fill_up_constraints(model.time_frame, model.q, model.q_upper, model.parameters.epsilon, model.q_lower)

    # relaxedReserve disabling condition (eq. (43))
    for t in model.time_frame:
        model.add_constraint(
            model.get_variable(model.relaxed_reserves_at(t))
            <= model.q_lower.get_value(t) * (1 - model.ON_UP.get_value(t) - model.ON_DOWN.get_value(t))
        )

    # impossible commitment and stable reserves constraints (eq. (44))
    for t in model.time_frame:
        model.add_constraint(
            model.get_variable(model.automated_reserves_up_at(t))
            <= model.maximum_automated * (1 - model.OFF.get_value(t))
        )
        model.add_constraint(
            model.get_variable(model.automated_reserves_down_at(t))
            <= model.maximum_automated * (1 - model.OFF.get_value(t))
        )
        model.add_constraint(
            model.get_variable(model.reserves_up_equip_at(t))
            <= model.q_upper.get_value(t) * (1 - model.OFF.get_value(t))
        )
        model.add_constraint(
            model.get_variable(model.reserves_down_equip_at(t))
            <= model.q_upper.get_value(t) * (1 - model.OFF.get_value(t))
        )

        # Power output
    for t in model.time_frame:
        model.add_constraint(
            model.q[t] >= model.q_lower.get_value(t) * (model.ON_UP.get_value(t) + model.ON_DOWN.get_value(t)),
            f"lower_bound_of_{model.thermal_unit.name}_at_{t}",
        )  # Lower bound (eq. 33)

        model.add_constraint(
            model.q[t] <= model.q_upper.get_value(t) * (model.ON_UP.get_value(t) + model.ON_DOWN.get_value(t)),
            f"upper_bound_of_{model.thermal_unit.name}_at_{t}",
        )  # Upper bound (eq. 34)

    if model.delta_q > 0:  # Case where the gradient is finite.
        for t in model.gradients_time_frame:  # The gradients are defined only up to T-1.
            t_next = t + model.parameters.time_step  # Get the next time step

            # Upward constrained gradient (eq. 35):
            model.add_constraint(
                model.q[t_next] - model.q[t]
                <= model.delta_q * model.ON_UP.get_value(t)
                + model.delta_q_unconstrained * model.turned_on.get_value(t_next),
                f"upward_gradient_of_{model.thermal_unit.name}_at_{t}",
            )  # Upward gradient

            # Downward constrained gradient (eq. 37) :
            model.add_constraint(
                model.q[t_next] - model.q[t]
                >= -model.delta_q * model.ON_DOWN.get_value(t) - model.delta_q_unconstrained * model.turned_off[t_next],
                f"downward_gradient_of_{model.thermal_unit.name}_at_{t}",
            )  # Downward gradient

    elif model.delta_q == 0:  # Case where the gradient is 'infinite'
        for t in model.gradients_time_frame:
            t_next = t + model.parameters.time_step  # Get the next time step

            # Upward unconstrained gradient (eq. 36)
            model.add_constraint(
                model.q[t_next] - model.q[t]
                <= model.delta_q_unconstrained * model.ON_UP.get_value(t)
                + model.delta_q_unconstrained * model.turned_on.get_value(t_next)
            )  # Upward gradient

            # Downward unconstrained gradient (eq. 38)
            model.add_constraint(
                model.q[t_next] - model.q[t]
                >= -model.delta_q_unconstrained * model.ON_DOWN.get_value(t)
                - model.delta_q_unconstrained * model.turned_off[t_next]
            )  # Downward gradient
    else:  # Raise an error since no gradients have been detected.
        cfg.logger.error(
            f"*** WARNING ***\n No gradients have been defined for equipment {model.thermal_unit.name}. \n "
            "Please check the value of `maximum_gradient`."
        )
        raise ValueError("Missing gradients for thermic units.")

    model.create_daily_energy_constraint(model.thermal_unit, model.time_frame, model.parameters.time_step, model.q)
