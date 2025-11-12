"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Any

from pydantic_extra_types.pendulum_dt import DateTime

import atlas.config as cfg
from atlas.modules.day_ahead_orders.orders_formulation.thermal.thermal_optimization_model import (
    ThermalOptimizationModel,
)


def execute(model: ThermalOptimizationModel, day_zero: bool) -> None:
    """Combination 7 : T_stop >= 1, model.T_stable = 0 T_start >= 1"""
    # In this case, there are five state variables and two auxiliary variables.
    # We review the initial conditions, then the constraints on the state variables
    # and finally the constraints on the power output.

    # PREAMBLE
    # Define the down_to_stop auxiliary, which is used in this combination and in combination 2
    down_to_stop: dict[DateTime, Any] = {}
    for t in model.time_frame:
        down_to_stop[t] = model.add_continuous_variable(f"down_to_stop_equip_{model.thermal_unit.name}_at_{t}", 0, 1)

    # A. INITIAL CONDITIONS

    if day_zero:
        # Remind the user how the program has been initialized
        if model.parameters.verbose:
            cfg.logger.info(f"Initial conditions of unit {model.thermal_unit.name} have been set as in equation (47).")

        for t in model.previous_time_frame:
            # Initial conditions on the power output
            model.q[t] = 0
            # Initial conditions on the state variables : the unit is OFF
            model.OFF[t] = 1
            model.ON_UP[t] = 0
            model.ON_DOWN[t] = 0
            model.STOP[t] = 0
            model.START[t] = 0
            # Initial conditions on the auxiliary variables
            model.turned_on[t] = 0
            model.turned_off[t] = 0
            down_to_stop[t] = 0
    else:
        # Initial condition on the power output
        for t in model.previous_time_frame:
            model.q[t] = model.last_power.get_value(t)

        # Initial conditions on the state variables
        for t in model.previous_time_frame:
            # There are now three cases : either q_t >= q_min, 0 < q_t < q_min or q_t = 0
            if model.last_power.get_value(t) >= model.thermal_unit.minimum_power.get_value(t):
                model.OFF[t] = 0
                model.STOP[t] = 0
                model.START[t] = 0
                model.ON_DOWN[t] = 1
                model.ON_UP[t] = (
                    1
                    # Set both ON states to 1 in order to allow the unit to do whatever it wants as there is no
                )
                # stable constraint at this point.
            elif (
                model.last_power.get_value(t) > 0
            ):  # We will below see whether the unit was being turned on or turned off.
                model.STOP[t] = 1
                model.START[t] = 1
                model.OFF[t] = 0
                model.ON_UP[t] = 0
                model.ON_DOWN[t] = 0
            else:
                model.STOP[t] = 0
                model.START[t] = 0
                model.OFF[t] = 1
                model.ON_UP[t] = 0
                model.ON_DOWN[t] = 0

        # Distinguish between start-ups and shutdowns
        # discard the extended_start_date only.
        for t in model.previous_time_frame[:-1]:
            t_prev = t - model.parameters.time_step
            if model.START[t] == 1:  # Take start or stop, does not matter.
                if model.q[t] > model.q[t_prev]:  # If the power output increases, then we are starting up.
                    model.STOP[t] = 0
                    model.START[t] = 1
                elif model.q[t] < model.q[t_prev]:  # otherwise we are shutting down the unit.
                    model.STOP[t] = 1
                    model.START[t] = 0

                    # Initial conditions on the auxiliary variables
        for t in model.previous_time_frame:
            # Initialize all the values to 0
            model.turned_on[t] = 0
            model.turned_off[t] = 0
            down_to_stop[t] = 0
            if not t == model.extended_start_date:
                # Reconstruct potential switches using the state variables
                t_prev = t - model.parameters.time_step
                # See if the unit has been turned off
                if model.STOP[t] - model.STOP[t_prev] == 1:
                    model.turned_off[t] = 1
                # Or turned on
                elif model.START[t] - model.START[t_prev] == 1:
                    model.turned_on[t] = 1
                # Reconstruction of down_to_stop
                elif model.STOP[t] - model.ON_DOWN[t_prev] == 0:
                    down_to_stop[t] = 1

    # B. CONSTRAINTS ON THE AUXILIARY VARIABLES

    # These constraints define the auxiliary variables. In the first case, there are only two
    # of them : turned_on and turned_off.

    # Constraints on the indicator that the unit has started on t
    # Amounts to leaving the OFF state, due to the mutual exclusion and transition constraints.
    # Enforces eq (3).
    for t in model.time_frame:
        model.add_constraint(model.turned_on[t] <= 1 - model.OFF[t])
        model.add_constraint(model.turned_on[t] <= model.OFF[t - model.parameters.time_step])
        model.add_constraint(
            model.turned_on[t] >= model.OFF[t - model.parameters.time_step] - model.OFF[t],
            f"constraints_defining_turned_on_{t}",
        )

    # Constraints on turned_off
    # Defined here when entering the STOP state as in eq. (5) because T_stop > 0
    for t in model.time_frame:
        model.add_constraint(model.turned_off[t] <= 1 - model.STOP[t - model.parameters.time_step])
        model.add_constraint(model.turned_off[t] <= model.STOP[t])
        model.add_constraint(
            model.turned_off[t] >= model.STOP[t] - model.STOP[t - model.parameters.time_step],
            f"constraints_defining_turned_off_{t}",
        )

    # Constraints on down_to_stop (eq. (20))
    for t in model.time_frame:
        t_minus_one = t - model.parameters.time_step
        model.add_constraint(down_to_stop[t] <= model.STOP[t])
        model.add_constraint(down_to_stop[t] <= model.ON_DOWN[t_minus_one])
        model.add_constraint(down_to_stop[t] >= model.STOP[t] + model.ON_DOWN[t_minus_one] - 1)

    # C. CONSTRAINTS ON THE STATE VARIABLES

    # Mutual exclusion constraint
    for t in model.time_frame:
        # Defined over the whole time frame
        # Enforces eq. (9)
        model.add_constraint(
            model.OFF[t] + model.ON_UP[t] + model.ON_DOWN[t] + model.STOP[t] + model.START[t] == 1,
            f"mutual_exclusion_at_{t}",
        )

    # Transitions:
    # Transitions from OFF to STOP and STOP to ON_DOWN and ON_UP are forbidden
    # Direct transitions from ON_UP and ON_DOWN to OFF are forbidden.
    # Transitions from ON_UP and ON_DOWN to START and START to OFF are forbidden
    # Direct transitions from OFF to ON_UP and ON_DOWN are forbidden.
    for t in model.time_frame:
        t_minus_one = t - model.parameters.time_step
        # STOP to ON (eq. (13))
        model.add_constraint(model.STOP[t_minus_one] + model.ON_UP[t] <= 1)
        model.add_constraint(model.STOP[t_minus_one] + model.ON_DOWN[t] <= 1)
        # OFF to STOP (eq. (12))
        model.add_constraint(model.OFF[t_minus_one] + model.STOP[t] <= 1)
        # ON to OFF (eq.(18) )
        model.add_constraint(model.ON_UP[t_minus_one] + model.OFF[t] <= 1)
        model.add_constraint(model.ON_DOWN[t_minus_one] + model.OFF[t] <= 1)
        # ON to START (eq. (10))
        model.add_constraint(model.ON_UP[t_minus_one] + model.START[t] <= 1)
        model.add_constraint(model.ON_DOWN[t_minus_one] + model.START[t] <= 1)
        # START to OFF (eq. (11))
        model.add_constraint(model.START[t_minus_one] + model.OFF[t] <= 1)
        # START to STOP and STOP to START (eq. (14))
        model.add_constraint(model.START[t_minus_one] + model.STOP[t] <= 1)
        model.add_constraint(model.STOP[t_minus_one] + model.START[t] <= 1)
        # OFF to ON (eq. (15))
        model.add_constraint(model.OFF[t_minus_one] + model.ON_UP[t] <= 1)
        model.add_constraint(
            model.OFF[t_minus_one] + model.ON_DOWN[t] <= 1,
            f"transitions_constraints_at_{t}",
        )

        # Eviction constraints.
    for t in model.time_frame:
        # Define t - T_start and t - T_stop.
        t_minus_T_start = t - model.T_start * model.parameters.time_step
        t_minus_T_stop = t - model.T_stop * model.parameters.time_step
        # Add the constraints.
        # Implements equation (16)
        model.add_constraint(
            model.turned_on[t_minus_T_start] + model.START[t] <= 1,
            f"START_eviction_constraint_at_{t}",
        )
        # Implements equation (19)
        model.add_constraint(
            model.turned_off[t_minus_T_stop] + model.STOP[t] <= 1,
            f"STOP_eviction_constraint_at_{t}",
        )

    # Mininum time on and minimum time off constraints:
    # if model.T_on >= 2, model.T_off >= 2 or T_stop >= 2, lock the unit in this state.
    if model.T_on >= 2:
        for t in model.time_frame:
            time_steps = range(1, model.T_on)
            for s in time_steps:
                # Enforces eq. (31) with T_start > 0
                t_minus_s_minus_T_start = (
                    t - s * model.parameters.time_step - model.T_start * model.parameters.time_step
                )
                model.add_constraint(
                    model.turned_on[t_minus_s_minus_T_start] <= model.ON_UP[t] + model.ON_DOWN[t],
                    f"minimum_time_ON_{model.thermal_unit.name}_at_{t_minus_s_minus_T_start}_for_{t}",
                )
    if model.T_off >= 2:
        for t in model.time_frame:
            time_steps = range(1, model.T_off)
            for s in time_steps:
                # Enforces eq. (32) with T_stop > 0
                # Shift the index because the OFF is formally considered when entering the STOP state.
                t_minus_s_minus_T_stop = t - s * model.parameters.time_step - model.T_stop * model.parameters.time_step
                model.add_constraint(
                    model.turned_off[t_minus_s_minus_T_stop] <= model.OFF[t],
                    f"minimum_time_OFF_{model.thermal_unit.name}_at_{t_minus_s_minus_T_stop}_for_{t}",
                )
    if model.T_stop >= 2:
        for t in model.time_frame:
            for s in model.stop_time_steps:
                # Enforces eq. (24)
                t_minus_s = t - s * model.parameters.time_step
                model.add_constraint(
                    model.turned_off[t_minus_s] <= model.STOP[t],
                    f"shutdown_ramp_of_{model.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                )
    if model.T_start >= 2:
        for t in model.time_frame:
            for s in model.start_time_steps:
                # Enforces eq. (17)
                t_minus_s = t - s * model.parameters.time_step
                model.add_constraint(
                    model.turned_on[t_minus_s] <= model.START[t],
                    f"start_up_ramp_of_{model.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                )

    # D. CONSTRAINTS ON THE CONTROL VARIABLE

    # Shutdown and start_up gradients
    q_min = model.thermal_unit.minimum_power.max()  # Get the minimum_power without the reserve requirements
    q_step_up = q_min / model.T_start
    q_step_down = q_min / model.T_stop

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
            <= model.q_lower.get_value(t) * (1 - model.ON_UP[t] - model.ON_DOWN[t])
        )

    # impossible commitment and stable reserves constraints (eq. (44))
    for t in model.time_frame:
        model.add_constraint(
            model.get_variable(model.automated_reserves_up_at(t))
            <= model.maximum_automated * (1 - model.OFF[t] - model.START[t] - model.STOP[t])
        )
        model.add_constraint(
            model.get_variable(model.automated_reserves_down_at(t))
            <= model.maximum_automated * (1 - model.OFF[t] - model.START[t] - model.STOP[t])
        )
        model.add_constraint(
            model.get_variable(model.reserves_up_equip_at(t))
            <= model.q_upper.get_value(t) * (1 - model.OFF[t] - model.START[t] - model.STOP[t])
        )
        model.add_constraint(
            model.get_variable(model.reserves_down_equip_at(t))
            <= model.q_upper.get_value(t) * (1 - model.OFF[t] - model.START[t] - model.STOP[t])
        )

    # Power output
    for t in model.time_frame:
        model.add_constraint(
            model.q[t]
            >= model.q_lower.get_value(t) * (model.ON_UP[t] + model.ON_DOWN[t])
            + model.turned_off[t] * (q_min - q_step_down),
            f"lower_bound_of_{model.thermal_unit.name}_at_{t}",
        )
        # Lower bound (eq. (33))
        model.add_constraint(
            model.q[t]
            <= model.q_upper.get_value(t) * (model.ON_UP[t] + model.ON_DOWN[t])
            + model.STOP[t] * q_min
            + model.START[t] * q_min
            - model.turned_off[t] * q_step_down,
            f"upper_bound_of_{model.thermal_unit.name}_at_{t}",
        )
        # Upper bound (eq. (34))

    if model.delta_q > 0:  # Case where the gradient is finite.
        for t in model.gradients_time_frame:  # The gradients are defined only up to T-1.
            # NB. The downward gradient implemented here requires the unit to be at most at deltaQ in order to be able to enter the stop state.
            # The resulting constraint set is considerably more constraining than if the gradient was relaxed.
            t_next = t + model.parameters.time_step  # Get the next time step

            # Upward constrained gradient (eq. (35))
            model.add_constraint(
                model.q[t_next] - model.q[t]
                <= (
                    model.delta_q * model.ON_UP[t]
                    - model.turned_off[t_next] * q_step_down
                    - model.STOP[t] * q_step_down
                    + model.turned_on[t_next] * q_step_up
                    + model.START[t] * q_step_up
                ),
                f"upward_gradient_of_{model.thermal_unit.name}_at_{t}",
            )  # Upward gradient

            # Downward constrained gradient (eq. (37))
            model.add_constraint(
                model.q[t_next] - model.q[t]
                >= (
                    -model.delta_q * model.ON_DOWN[t]
                    - model.turned_off[t_next] * q_step_down
                    - model.STOP[t] * q_step_down
                    + down_to_stop[t_next] * model.delta_q
                    + model.turned_on[t_next] * q_step_up
                    + model.START[t] * q_step_up
                ),
                f"downward_gradient_of_{model.thermal_unit.name}_at_{t}",
            )  # Downward gradient
    elif model.delta_q == 0:
        for t in model.gradients_time_frame:
            t_next = t + model.parameters.time_step

            # Upward unconstrained gradient (eq. (36))
            model.add_constraint(
                model.q[t_next] - model.q[t]
                <= (
                    model.delta_q_unconstrained * model.ON_UP[t]
                    - model.turned_off[t_next] * q_step_down
                    - model.STOP[t] * q_step_down
                    + model.turned_on[t_next] * q_step_up
                    + model.START[t] * q_step_up
                ),
                f"unconstrained_upward_gradient_of_{model.thermal_unit.name}_at_{t}",
            )  # Upward gradient

            # Downward unconstrained gradient (eq. (38))
            model.add_constraint(
                model.q[t_next] - model.q[t]
                >= (
                    -model.delta_q_unconstrained * model.ON_DOWN[t]
                    - model.turned_off[t_next] * q_step_down
                    - model.STOP[t] * q_step_down
                    + down_to_stop[t_next] * model.delta_q_unconstrained
                    + model.turned_on[t_next] * q_step_up
                    + model.START[t] * q_step_up
                ),
                f"unconstrained_downward_gradient_of_{model.thermal_unit.name}_at_{t}",
            )  # Downward gradient
    else:  # Raise an error since no gradients have been detected.
        cfg.logger.error(
            f"*** WARNING ***\n No gradients have been defined for equipment {model.thermal_unit.name}. \n "
            "Please check the value of `maximum_gradient`."
        )
        raise ValueError("Missing gradients for thermic units.")

    model.create_daily_energy_constraint(model.thermal_unit, model.time_frame, model.parameters.time_step, model.q)
