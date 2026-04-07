"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import atlas.config as cfg
from atlas.modules.day_ahead_orders.orders_formulation.thermal.thermal_optimization_model import (
    ThermalOptimizationModel,
)


def execute(model: ThermalOptimizationModel, day_zero: bool) -> None:
    """
    Combination 4 : T_start >= 1, model.T_stable = T_stop = 0
    :param model: the model
    :type day_zero: bool
    :return: None
    """
    # In this case, there are four state variables and two auxiliary variables.
    # We review the initial conditions, then the constraints on the state variables
    # and finally the constraints on the power output.

    # A. INITIAL CONDITIONS

    if day_zero:
        # Remind the user how the program has been initialized
        cfg.logger.debug(f"Initial conditions of unit {model.thermal_unit.name} have been set as in equation (47).")

        for t in model.previous_time_frame:
            # Initial conditions on the power output
            model.q.set_extended(t, 0)
            # Initial conditions on the state variables : the unit is OFF
            model.OFF.set_extended(t, 1)
            model.ON_UP.set_extended(t, 0)
            model.ON_DOWN.set_extended(t, 0)
            model.START.set_extended(t, 0)
            # Initial conditions on the auxiliary variables
            model.turned_on.set_extended(t, 0)
            model.turned_off.set_extended(t, 0)
    else:
        # Initial condition on the power output
        for t in model.previous_time_frame:
            model.q.set_extended(t, int(model.last_power.get_value(t)))

        # Initial conditions on the state variables
        for t in model.previous_time_frame:
            # There are now three cases : either q_t >= q_min, 0 < q_t < q_min or q_t = 0
            if model.last_power.get_value(t) >= model.thermal_unit.minimum_power.get_value(t):
                model.OFF.set_extended(t, 0)
                model.START.set_extended(t, 0)
                # Set both ON states to 1 in order to allow the unit to do whatever it wants as there is no
                # stable constraint at this point.
                model.ON_DOWN.set_extended(t, 1)
                model.ON_UP.set_extended(t, 1)
            elif model.last_power.get_value(t) > 0:
                model.START.set_extended(t, 1)
                model.OFF.set_extended(t, 0)
                model.ON_UP.set_extended(t, 0)
                model.ON_DOWN.set_extended(t, 0)
            else:
                model.START.set_extended(t, 0)
                model.OFF.set_extended(t, 1)
                model.ON_UP.set_extended(t, 0)
                model.ON_DOWN.set_extended(t, 0)

        # Initial conditions on the auxiliary variables
        for t in model.previous_time_frame:
            # Initialize all the values to 0
            model.turned_on.set_extended(t, 0)
            model.turned_off.set_extended(t, 0)
            if not t == model.extended_start_date:
                # Reconstruct potential switches using the state variables
                t_prev = t - model.parameters.temporal.timestep
                # See if the unit has been turned off
                if model.OFF.get_extended_value(t) - model.OFF.get_extended_value(t_prev) == 1:
                    model.turned_off.set_extended(t, 1)
                # Or turned on
                elif model.START.get_extended_value(t) - model.START.get_extended_value(t_prev) == 1:
                    model.turned_on.set_extended(t, 1)

    # B. CONSTRAINTS ON THE AUXILIARY VARIABLES

    # These constraints define the auxiliary variables, turned_on and turned_off.

    # Constraints on the indicator that the unit has started on t
    # which is detected when OFF[t-1] = 1 and OFF[t] = 0
    # This amounts to be turned on when the unit enters the START state as in eq. (3)
    for t in model.time_frame:
        model.add_constraint(model.turned_on.get_value(t) <= 1 - model.OFF.get_value(t))
        model.add_constraint(
            model.turned_on.get_value(t) <= model.OFF.get_value(t - model.parameters.temporal.timestep)
        )
        model.add_constraint(
            model.turned_on.get_value(t)
            >= model.OFF.get_value(t - model.parameters.temporal.timestep) - model.OFF.get_value(t),
            f"constraints_defining_turned_on_{t}",
        )

        # Constraints on turned_off
    # Defined here when entering the OFF state as in eq. (4) because T_stop = 0
    for t in model.time_frame:
        model.add_constraint(
            model.turned_off.get_value(t) <= 1 - model.OFF.get_value(t - model.parameters.temporal.timestep)
        )
        model.add_constraint(model.turned_off.get_value(t) <= model.OFF.get_value(t))
        model.add_constraint(
            model.turned_off.get_value(t)
            >= model.OFF.get_value(t) - model.OFF.get_value(t - model.parameters.temporal.timestep),
            f"constraints_defining_turned_off_{t}",
        )

    # C. CONSTRAINTS ON THE STATE VARIABLES

    # Mutual exclusion constraint
    for t in model.time_frame:
        # Defined over the whole time frame
        # Enforces eq. (9)
        model.add_constraint(
            model.OFF.get_value(t) + model.ON_UP.get_value(t) + model.ON_DOWN.get_value(t) + model.START.get_value(t)
            == 1,
            f"mutual_exclusion_at_{t}",
        )

    # Transitions:
    # Transitions from ON_UP and ON_DOWN to START and START to OFF are forbidden
    # Direct transitions from OFF to ON_UP and ON_DOWN are forbidden.
    for t in model.time_frame:
        t_minus_one = t - model.parameters.temporal.timestep
        model.add_constraint(model.ON_UP.get_value(t_minus_one) + model.START.get_value(t) <= 1)  # eq. (10)
        model.add_constraint(model.ON_DOWN.get_value(t_minus_one) + model.START.get_value(t) <= 1)  # eq. (10)
        model.add_constraint(model.START.get_value(t_minus_one) + model.OFF.get_value(t) <= 1)  # eq. (11)
        model.add_constraint(model.OFF.get_value(t_minus_one) + model.ON_UP.get_value(t) <= 1)  # eq. (15)
        model.add_constraint(
            model.OFF.get_value(t_minus_one) + model.ON_DOWN.get_value(t) <= 1,
            f"transitions_constraints_at_{t}",
        )  # eq. (15)

    # Eviction constraint. This constraint forces the unit to leave the START state once the startup phase is finished.
    for t in model.time_frame:
        t_minus_T_start = t - model.T_start * model.parameters.temporal.timestep
        # Implement eqution (16)
        model.add_constraint(
            model.turned_on.get_value(t_minus_T_start) + model.START.get_value(t) <= 1,
            f"eviction_constraint_at_{t}",
        )

    # Mininum time on and minimum time off constraints:
    # if model.T_on >= 2, model.T_off >= 2 or T_stop >= 2, lock the unit in this state.
    if model.T_on >= 2:
        for t in model.time_frame:
            time_steps = range(1, model.T_on)
            for s in time_steps:
                # Enforce eq. (31) with T_start > 0
                t_minus_s_minus_T_start = (
                    t - s * model.parameters.temporal.timestep - model.T_start * model.parameters.temporal.timestep
                )
                model.add_constraint(
                    model.turned_on.get_value(t_minus_s_minus_T_start)
                    <= model.ON_UP.get_value(t) + model.ON_DOWN.get_value(t),
                    f"minimum_time_ON_{model.thermal_unit.name}_at_{t_minus_s_minus_T_start}_for_{t}",
                )
    if model.T_off >= 2:
        for t in model.time_frame:
            time_steps = range(1, model.T_off)
            for s in time_steps:
                # Enforce eq. (32) with T_stop = 0
                t_minus_s = t - s * model.parameters.temporal.timestep
                model.add_constraint(
                    model.turned_off.get_value(t_minus_s) <= model.OFF.get_value(t),
                    f"minimum_time_OFF_{model.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                )
    if model.T_start >= 2:
        for t in model.time_frame:
            for s in model.start_time_steps:
                t_minus_s = t - s * model.parameters.temporal.timestep
                # Enforce eq. (17)
                model.add_constraint(
                    model.turned_on.get_value(t_minus_s) <= model.START.get_value(t),
                    f"startup_ramp_of_{model.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                )

    # D. CONSTRAINTS ON THE CONTROL VARIABLE

    # Start-up gradient
    q_min = model.thermal_unit.minimum_power.max()  # Get the minimum_power without the reserve requirements
    q_step = q_min / model.T_start

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
            <= model.maximum_automated * (1 - model.OFF.get_value(t) - model.START.get_value(t))
        )
        model.add_constraint(
            model.get_variable(model.automated_reserves_down_at(t))
            <= model.maximum_automated * (1 - model.OFF.get_value(t) - model.START.get_value(t))
        )
        model.add_constraint(
            model.get_variable(model.reserves_up_equip_at(t))
            <= model.q_upper.get_value(t) * (1 - model.OFF.get_value(t) - model.START.get_value(t))
        )
        model.add_constraint(
            model.get_variable(model.reserves_down_equip_at(t))
            <= model.q_upper.get_value(t) * (1 - model.OFF.get_value(t) - model.START.get_value(t))
        )

    # Power output
    for t in model.time_frame:
        model.add_constraint(
            model.q.get_value(t)
            >= model.q_lower.get_value(t) * (model.ON_UP.get_value(t) + model.ON_DOWN.get_value(t)),
            f"lower_bound_of_{model.thermal_unit.name}_at_{t}",
        )  # Lower bound (eq. (33))
        model.add_constraint(
            model.q.get_value(t)
            <= model.q_upper.get_value(t) * (model.ON_UP.get_value(t) + model.ON_DOWN.get_value(t))
            + model.START.get_value(t) * q_min,
            f"upper_bound_of_{model.thermal_unit.name}_at_{t}",
        )  # Upper bound (eq. (34))

    if model.delta_q > 0:  # Case where the gradient is finite.
        for t in model.gradients_time_frame:  # The gradients are defined only up to T-1.
            # NB. The downward gradient implemented here requires the unit to be at most at deltaQ in order to be able to enter the stop state.
            # The resulting constraint set is considerably more constraining than if the gradient was relaxed.
            t_next = t + model.parameters.temporal.timestep  # Get the next time job

            # Upward constrained gradient (eq. (35))
            model.add_constraint(
                model.q.get_value(t_next) - model.q.get_value(t)
                <= model.delta_q * model.ON_UP.get_value(t)
                + model.turned_on.get_value(t_next) * q_step
                + model.START.get_value(t) * q_step,
                f"upward_gradient_of_{model.thermal_unit.name}_at_{t}",
            )  # Upward gradient

            # Downward constrained gradient (eq. (37))
            model.add_constraint(
                model.q.get_value(t_next) - model.q.get_value(t)
                >= -model.delta_q * model.ON_DOWN.get_value(t)
                + model.turned_on.get_value(t_next) * q_step
                + model.START.get_value(t) * q_step
                - model.delta_q_unconstrained * model.turned_off.get_value(t_next),
                f"downward_gradient_of_{model.thermal_unit.name}_at_{t}",
            )  # Downward gradient

    elif model.delta_q == 0:  # Case where the gradient is 'infinite'
        for t in model.gradients_time_frame:
            t_next = t + model.parameters.temporal.timestep  # Get the next time job

            # Upward unconstrained gradient (eq. (36))
            model.add_constraint(
                model.q.get_value(t_next) - model.q.get_value(t)
                <= model.delta_q_unconstrained * model.ON_UP.get_value(t)
                + model.turned_on.get_value(t_next) * q_step
                + model.START.get_value(t) * q_step,
                f"unconstrained_upward_gradient_of_{model.thermal_unit.name}_at_{t}",
            )  # Upward gradient

            # Downward unconstrained gradient (eq. (38))
            model.add_constraint(
                model.q.get_value(t_next) - model.q.get_value(t)
                >= (
                    -model.delta_q_unconstrained * model.ON_DOWN.get_value(t)
                    + model.turned_on.get_value(t_next) * q_step
                    + model.START.get_value(t) * q_step
                    - model.delta_q_unconstrained * model.turned_off.get_value(t_next)
                ),
                f"unconstrained_downward_gradient_of_{model.thermal_unit.name}_at_{t}",
            )  # Downward gradient
    else:  # Raise an error since no gradients have been detected.
        cfg.logger.error(
            f"No gradients have been defined for equipment {model.thermal_unit.name}. \n "
            "Please check the value of `maximum_gradient`."
        )
        raise ValueError("Missing gradients for thermic units.")
