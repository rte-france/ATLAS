"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import math
from typing import Any

from pydantic_extra_types.pendulum_dt import DateTime

import atlas.config as cfg
from atlas.modules.day_ahead_orders.orders_formulation.thermal.thermal_optimization_model import (
    ThermalOptimizationModel,
)


def execute(model: ThermalOptimizationModel, day_zero: bool) -> None:
    """Combination 8 : T_start = model.T_stable = T_stop >= 1"""
    # In this case, there are six state variables and the following auxiliary variables :
    #     - turned_on[t] and turned_off[t], indicating whether the unit has been turned on or off
    #     - stable[t], indicating whether the unit entered the stable state
    #     - U[t] and D[t], implemented in two stages with tilde_D[t], tilde_D[t] as the first stage
    #     - entered_up[t] and entered_down[t] indicating that the unit entered the UP or down STATE
    #
    # We also need the gradient auxiliaries DD[t] and flat_down_stop[t] to follow the shut down procedure of
    # the unit.
    #
    # We review the initial conditions, then the constraints on the state variables
    # and finally the constraints on the power output.

    # PREAMBLE
    # Definition of two additional auxiliary variables needed specifically to handle this case,
    # flat_down_stop, which detects when the unit follows a FLAT(t-2) - DOWN(t-1) and STOP(t) path
    # and DD, which detects if the unit is to be stopped at t+1 (i.e. STOP(t+1) = 1) after having been
    # in the DOWN state at time steps t and t-1.

    # flat_down_stop
    flat_down_stop: dict[DateTime, Any] = {}
    for t in model.time_frame:
        flat_down_stop[t] = model.add_continuous_variable(
            f"flat_down_stop_at_{t}_equip_{model.thermal_unit.name}",
            0,
            1,
        )

    DD: dict[DateTime, Any] = {}
    for t in model.gradients_time_frame:
        DD[t] = model.add_continuous_variable(f"DD_{t}_equip_{model.thermal_unit.name}", model.Q_min, model.Q_max)

    # A. INITIAL CONDITIONS

    # Define the start_date - 2 time steps.
    start_date_minus_two = model.parameters.start_date - 2 * model.parameters.time_step

    if day_zero:
        # Remind the user how the program has been initialized
        cfg.logger.info(f"Initial conditions of unit {model.thermal_unit.name} have been set as in equation (47).")

        for t in model.previous_time_frame:
            # Initial conditions on the power output
            model.q[t] = 0
            # Initial conditions on the state variables : the unit is OFF
            model.OFF.set_extended(t, 1)
            model.STOP[t] = 0
            model.START[t] = 0
            if not t == model.start_date_minus_one:
                model.ON_UP.set_extended(t, 0)
                model.ON_DOWN.set_extended(t, 0)
                model.ON_FLAT[t] = 0
                # Initial conditions on the auxiliary variables defined over time_frame_union_minus_one
                model.stable[t] = 0
                model.entered_up[t] = 0
                model.entered_down[t] = 0

            # Initial conditions on the remaining auxiliary variables
            model.turned_on[t] = 0
            model.turned_off[t] = 0
            flat_down_stop[t] = 0
    else:
        # Setting up the initial conditions will be a bit more complex. We consecutively do the following:
        #    - Set the inital conditions on the power output
        #    - See wether the unit is ON or OFF
        #    - Initialize the auxiliaries turned_up and turned_down accordingly
        #    - For the steps where the unit is ON:
        #         - See whether the unit was UP, DOWN or FLAT
        #         - Initialize the auxiliary variables accordingly

        # Initial condition on the power output
        for t in model.previous_time_frame:
            model.q[t] = model.last_power.get_value(t)

        # Initial conditions on the state variables OFF/ON
        for t in model.previous_time_frame:
            if model.last_power.get_value(t) >= model.thermal_unit.minimum_power.get_value(t):
                # Only the OFF and STOP variables are initialized. ON_FLAT, ON_DOWN and ON_UP will be initialized afterwards.
                model.OFF.set_extended(t, 0)
                model.STOP[t] = 0
                model.START[t] = 0
            elif model.last_power.get_value(t) > 0:
                model.OFF.set_extended(t, 0)
                model.STOP[t] = 1  # Set both START and STOP at 1 for now, will be distinguished afterwards.
                model.START[t] = 1
                if not t == model.start_date_minus_one:
                    model.ON_UP.set_extended(t, 0)
                    model.ON_DOWN.set_extended(t, 0)
                    model.ON_FLAT[t] = 0
            else:
                model.OFF.set_extended(t, 1)
                model.STOP[t] = 0
                model.START[t] = 0
                if not t == model.start_date_minus_one:
                    model.ON_UP.set_extended(t, 0)
                    model.ON_DOWN.set_extended(t, 0)
                    model.ON_FLAT[t] = 0

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

                    # Initial conditions on the auxiliary variables turned_on turned_off
        for t in model.previous_time_frame:
            # Initialize all the values to 0
            model.turned_on[t] = 0
            model.turned_off[t] = 0
            if not t == model.extended_start_date:
                # Reconstruct potential switches using the state variables
                t_prev = t - model.parameters.time_step
                # See if the unit has been turned off
                if model.STOP[t] - model.STOP[t_prev] == 1:
                    model.turned_off[t] = 1
                # Or turned on
                elif model.START[t] - model.START[t_prev] == 1:
                    model.turned_on[t] = 1

        # Reconstruct the values of UP, DOWN and FLAT and their associated
        # auxiliary variables
        for t in model.previous_time_frame[
            :-1
        ]:  # Loop excluding last date because we are reconstructing the values of the
            # ON variables using  variations between q[t] and q[t-1].

            t_prev = t - model.parameters.time_step
            if model.OFF.get_extended_value(t_prev) == 0:
                # See if the power output was stable, increasing or decreasing:
                if model.q[t] > model.q[t_prev]:  # Recall that here t_prev is earlier than t.
                    model.ON_UP.set_extended(t_prev, 1)
                    model.ON_DOWN.set_extended(t_prev, 0)
                    model.ON_FLAT[t_prev] = 0
                elif model.q[t] < model.q[t_prev]:
                    model.ON_UP.set_extended(t_prev, 0)
                    model.ON_DOWN.set_extended(t_prev, 1)
                    model.ON_FLAT[t_prev] = 0
                elif model.q[t] == model.q[t_prev]:
                    model.ON_UP.set_extended(t_prev, 0)
                    model.ON_DOWN.set_extended(t_prev, 0)
                    model.ON_FLAT[t_prev] = 1
            else:
                model.ON_UP.set_extended(t_prev, 0)
                model.ON_DOWN.set_extended(t_prev, 0)
                model.ON_FLAT[t_prev] = 0

        # Initialize the auxiliary variables
        for t in model.previous_time_frame[
            1:
        ]:  # Loop excluding start_date_minus_one, which is the first element in the previous_time_frame list.
            # Default value set to 0
            model.stable[t] = 0
            model.entered_up[t] = 0
            model.entered_down[t] = 0

            if (not t == model.extended_start_date) and (not model.OFF.get_extended_value(t) == 1):
                t_prev = t - model.parameters.time_step

                # See if the unit entered the FLAT state
                if model.ON_FLAT[t] - model.ON_FLAT[t_prev] == 1:
                    model.stable[t] = 1
                # or the UP state
                if model.ON_UP.get_extended_value(t) - model.ON_UP.get_extended_value(t_prev) == 1:
                    model.entered_up[t] = 1
                # or the DOWN state
                if model.ON_DOWN.get_extended_value(t) - model.ON_DOWN.get_extended_value(t_prev) == 1:
                    model.entered_down[t] = 1

        # Initialize flat_down_stop.
        for t in model.previous_time_frame[:-2]:
            # Moreover, if we are after extended_start_date + time_step
            # initialize flat_down_stop (which traces back up to two time index before)
            t_minus_one = t - model.parameters.time_step
            t_minus_two = t - 2 * model.parameters.time_step
            flat_down_stop[t] = int(
                math.floor(
                    (model.STOP[t] + model.ON_DOWN.get_extended_value(t_minus_one) + model.ON_FLAT[t_minus_two]) / 3
                )
            )

            # Initialize the gradient auxiliaries. This is only required for the last time step of the
    # previous_time_frame. Only ON_UP[start_date_minus_one] and ON_DOWN[start_date_minus_one] are decision variables
    # in the expressions below.
    model.U[model.start_date_minus_one] = (
        model.ON_UP.get_value(model.start_date_minus_one)
        * model.ON_UP.get_value(start_date_minus_two)
        * (model.q[model.start_date_minus_one] - model.q[start_date_minus_two])
    )
    model.D[model.start_date_minus_one] = (
        model.ON_DOWN.get_value(model.start_date_minus_one)
        * model.ON_DOWN.get_value(start_date_minus_two)
        * (model.q[model.start_date_minus_one] - model.q[start_date_minus_two])
    )

    # B. CONSTRAINTS ON THE AUXILIARY VARIABLES

    # These constraints define the auxiliary variables. In the first case, there are only two
    # of them : turned_on and turned_off.

    # Constraints on the indicator that the unit has started on t
    # Enforces eq. (3)
    for t in model.time_frame:
        model.add_constraint(model.turned_on[t] <= 1 - model.OFF.get_value(t))
        model.add_constraint(model.turned_on[t] <= model.OFF.get_value(t - model.parameters.time_step))
        model.add_constraint(
            model.turned_on[t] >= model.OFF.get_value(t - model.parameters.time_step) - model.OFF.get_value(t)
        )

        # Constraints on turned_off
    # Enforces eq. (5)
    for t in model.time_frame:
        model.add_constraint(model.turned_off[t] <= 1 - model.STOP[t - model.parameters.time_step])
        model.add_constraint(model.turned_off[t] <= model.STOP[t])
        model.add_constraint(model.turned_off[t] >= model.STOP[t] - model.STOP[t - model.parameters.time_step])

    # stable auxiliary variable
    # Enforces eq. (6)
    for t in model.time_frame_union_minus_one:
        model.add_constraint(model.stable[t] <= 1 - model.ON_FLAT[t - model.parameters.time_step])
        model.add_constraint(model.stable[t] <= model.ON_FLAT[t])
        model.add_constraint(model.stable[t] >= model.ON_FLAT[t] - model.ON_FLAT[t - model.parameters.time_step])

    # flat_down_stop auxiliary (eq. (22))
    for t in model.time_frame:
        t_minus_one = t - model.parameters.time_step
        t_minus_two = t - 2 * model.parameters.time_step
        model.add_constraint(flat_down_stop[t] <= model.STOP[t])
        model.add_constraint(flat_down_stop[t] <= model.ON_DOWN.get_value(t_minus_one))
        model.add_constraint(flat_down_stop[t] <= model.ON_FLAT[t_minus_two])
        model.add_constraint(
            flat_down_stop[t] >= model.STOP[t] + model.ON_DOWN.get_value(t_minus_one) + model.ON_FLAT[t_minus_two] - 2
        )

    # entered_up and entered_down auxiliaries (defined in sections 6.1.4 and 6.1.5)
    for t in model.time_frame_union_minus_one:
        # entered_up (eq. (7))
        model.add_constraint(model.entered_up[t] <= 1 - model.ON_UP.get_value(t - model.parameters.time_step))
        model.add_constraint(model.entered_up[t] <= model.ON_UP.get_value(t))
        model.add_constraint(
            model.entered_up[t] >= model.ON_UP.get_value(t) - model.ON_UP.get_value(t - model.parameters.time_step)
        )
        # entered_down (eq. (8))
        model.add_constraint(model.entered_down[t] <= 1 - model.ON_DOWN.get_value(t - model.parameters.time_step))
        model.add_constraint(model.entered_down[t] <= model.ON_DOWN.get_value(t))
        model.add_constraint(
            model.entered_down[t]
            >= model.ON_DOWN.get_value(t) - model.ON_DOWN.get_value(t - model.parameters.time_step)
        )

    # UP and DOWN auxiliary variables for the gradient.
    # These auxiliary variables model the fact that if the unit is increasing (decreasing) its
    # power output twice in a row, then the second time the gradient is locked.
    # In practice, these variables are defined in two stages

    # First stage : tilde_U and tilde_D
    for t in model.time_frame:  # Loop in all the time_frame but start_date.
        t_minus_one = t - model.parameters.time_step
        # tilde_U (eq. (28))
        model.add_constraint(
            model.get_variable(model.aux_up_grad_at(t)) <= model.Q_max * model.ON_UP.get_value(t_minus_one)
        )
        model.add_constraint(
            model.get_variable(model.aux_up_grad_at(t)) >= model.Q_min * model.ON_UP.get_value(t_minus_one)
        )
        model.add_constraint(
            model.get_variable(model.aux_up_grad_at(t))
            <= model.q[t] - model.q[t_minus_one] - model.Q_min * (1 - model.ON_UP.get_value(t_minus_one))
        )
        model.add_constraint(
            model.get_variable(model.aux_up_grad_at(t))
            >= model.q[t] - model.q[t_minus_one] - model.Q_max * (1 - model.ON_UP.get_value(t_minus_one)),
            f"VALUE_of_tilde_UP_at_{t}",
        )

        # tilde_D (eq. (30))
        model.add_constraint(
            model.get_variable(model.aux_down_grad_at(t)) <= model.Q_max * model.ON_DOWN.get_value(t_minus_one)
        )
        model.add_constraint(
            model.get_variable(model.aux_down_grad_at(t)) >= model.Q_min * model.ON_DOWN.get_value(t_minus_one)
        )
        model.add_constraint(
            model.get_variable(model.aux_down_grad_at(t))
            <= model.q[t] - model.q[t_minus_one] - model.Q_min * (1 - model.ON_DOWN.get_value(t_minus_one))
        )
        model.add_constraint(
            model.get_variable(model.aux_down_grad_at(t))
            >= model.q[t] - model.q[t_minus_one] - model.Q_max * (1 - model.ON_DOWN.get_value(t_minus_one)),
            f"VALUE_of_tilde_DOWN_at_{t}",
        )

    # Second stage : U and D
    # These variables wil be added to the gradient constraints.
    for t in model.time_frame:
        # U (eq. (27))
        model.add_constraint(model.U[t] <= model.Q_max * model.ON_UP.get_value(t))
        model.add_constraint(model.U[t] >= model.Q_min * model.ON_UP.get_value(t))
        model.add_constraint(
            model.U[t] <= model.get_variable(model.aux_up_grad_at(t)) - model.Q_min * (1 - model.ON_UP.get_value(t))
        )
        model.add_constraint(
            model.U[t] >= model.get_variable(model.aux_up_grad_at(t)) - model.Q_max * (1 - model.ON_UP.get_value(t)),
            f"VALUE_of_UP_at_{t}",
        )
        # D (eq. (29))
        model.add_constraint(model.D[t] <= model.Q_max * model.ON_DOWN.get_value(t))
        model.add_constraint(model.D[t] >= model.Q_min * model.ON_DOWN.get_value(t))
        model.add_constraint(
            model.D[t] <= model.get_variable(model.aux_down_grad_at(t)) - model.Q_min * (1 - model.ON_DOWN.get_value(t))
        )
        model.add_constraint(
            model.D[t]
            >= model.get_variable(model.aux_down_grad_at(t)) - model.Q_max * (1 - model.ON_DOWN.get_value(t)),
            f"VALUE_of_DOWN_at_{t}",
        )

    # DD Gradient auxiliary (eq. (23))
    for t in model.gradients_time_frame:
        t_plus_one = t + model.parameters.time_step
        model.add_constraint(DD[t] <= model.Q_max * model.STOP[t_plus_one])
        model.add_constraint(DD[t] >= model.Q_min * model.STOP[t_plus_one])
        model.add_constraint(DD[t] <= model.D[t] - model.Q_min * (1 - model.STOP[t_plus_one]))
        model.add_constraint(
            DD[t] >= model.D[t] - model.Q_max * (1 - model.STOP[t_plus_one]),
            f"DD_gradient_auxiliary_at_{t}",
        )

    # C. CONSTRAINTS ON THE STATE VARIABLES

    # Mutual exclusion constraint
    for t in model.time_frame_union_minus_one:
        # Defined over the whole time frame.
        # Enforces eq. (9)
        model.add_constraint(
            model.OFF.get_value(t)
            + model.ON_UP.get_value(t)
            + model.ON_DOWN.get_value(t)
            + model.ON_FLAT[t]
            + model.STOP[t]
            + model.START[t]
            == 1,
            f"mutual_exclusion_at_{t}",
        )

    # Transitions:
    # UP-DOWN and DOWN-UP transitions are forbidden.
    # STOP to ON transitions are also forbidden
    # OFF to STOP transitions
    # START to OFF
    # ON to START
    # START to STOP and STOP to START
    # OFF to ON
    # Finally, we forbid ON_UP to STOP (which never happens in practice) in order
    # to avoid defining a UU auxiliary analoguous to DD.
    for t in model.time_frame_union_minus_one:
        t_minus_one = t - model.parameters.time_step
        # Implement eq. (25).
        model.add_constraint(model.ON_UP.get_value(t_minus_one) + model.ON_DOWN.get_value(t) <= 1)
        model.add_constraint(model.ON_DOWN.get_value(t_minus_one) + model.ON_UP.get_value(t) <= 1)
        # STOP to ON (eq. (13))
        model.add_constraint(model.STOP[t_minus_one] + model.ON_FLAT[t] <= 1)
        model.add_constraint(model.STOP[t_minus_one] + model.ON_DOWN.get_value(t) <= 1)
        model.add_constraint(
            model.STOP[t_minus_one] + model.ON_UP.get_value(t) <= 1,
            f"transitions_constraints_on_timeFrame_union_minus_one_at_{t}",
        )
    for t in model.time_frame:
        t_minus_one = t - model.parameters.time_step
        # ON_UP to STOP transition (eq. (21))
        model.add_constraint(model.ON_UP.get_value(t_minus_one) + model.STOP[t] <= 1)
        # OFF to STOP (eq. (13)).
        model.add_constraint(model.OFF.get_value(t_minus_one) + model.STOP[t] <= 1)
        # ON to START (eq. (10))
        model.add_constraint(model.ON_UP.get_value(t_minus_one) + model.START[t] <= 1)
        model.add_constraint(model.ON_DOWN.get_value(t_minus_one) + model.START[t] <= 1)
        model.add_constraint(model.ON_FLAT[t_minus_one] + model.START[t] <= 1)
        # START to OFF (eq. (11))
        model.add_constraint(model.START[t_minus_one] + model.OFF.get_value(t) <= 1)
        # START to STOP and STOP to START (eq. (14))
        model.add_constraint(model.START[t_minus_one] + model.STOP[t] <= 1)
        model.add_constraint(model.STOP[t_minus_one] + model.START[t] <= 1)
        # OFF to ON (eq. (15))
        model.add_constraint(model.OFF.get_value(t_minus_one) + model.ON_UP.get_value(t) <= 1)
        model.add_constraint(model.OFF.get_value(t_minus_one) + model.ON_FLAT[t] <= 1)
        model.add_constraint(
            model.OFF.get_value(t_minus_one) + model.ON_DOWN.get_value(t) <= 1,
            f"transitions_constraints_at_{t}",
        )
        # The latter constraints are only defined on the time_frame because it does not involve ON variables at the t index.

    # Eviction constraints
    # The unit must leave the STOP state after T_stop time steps.
    # and the START state after T_start time steps.
    for t in model.time_frame:
        t_minus_T_stop = t - model.T_stop * model.parameters.time_step
        t_minus_T_start = t - model.T_start * model.parameters.time_step
        # Implements equation (19)
        model.add_constraint(
            model.turned_off[t_minus_T_stop] + model.STOP[t] <= 1,
            f"STOP_eviction_constraint_at_{t}",
        )
        # Implements equation (16)
        model.add_constraint(
            model.turned_on[t_minus_T_start] + model.START[t] <= 1,
            f"START_eviction_constraint_at_{t}",
        )

        # Mininum time on and minimum time off constraints:
    # if model.T_on >= 2 or model.T_off >= 2 or model.T_stable >= 2, lock the unit in this state.
    if model.T_on >= 2:
        for t in model.time_frame_union_minus_one:
            time_steps = range(1, model.T_on)  # Corresponds to the set {1,..., model.T_on - 1}
            for s in time_steps:
                # Enforces eq. (31), with T_start > 0
                t_minus_s_minus_T_start = (
                    t - s * model.parameters.time_step - model.T_start * model.parameters.time_step
                )
                model.add_constraint(
                    model.turned_on[t_minus_s_minus_T_start]
                    <= model.ON_UP.get_value(t) + model.ON_DOWN.get_value(t) + model.ON_FLAT[t],
                    f"minimum_time_ON_{model.thermal_unit.name}_at_{t_minus_s_minus_T_start}_for_{t}",
                )
    if model.T_off >= 2:
        for t in model.time_frame:
            time_steps = range(1, model.T_off)  # Corresponds to the set {1,..., model.T_off - 1}
            for s in time_steps:
                # Enforces eq. (32) with T_stop > 0
                t_minus_s_minus_T_stop = t - s * model.parameters.time_step - model.T_stop * model.parameters.time_step
                model.add_constraint(
                    model.turned_off[t_minus_s_minus_T_stop] <= model.OFF.get_value(t),
                    f"minimum_time_OFF_{model.thermal_unit.name}_at_{t_minus_s_minus_T_stop}_for_{t}",
                )
    if model.T_stable >= 2:
        for t in model.time_frame_union_minus_one:
            time_steps = range(1, model.T_stable - 1)  # Corresponds to the set {1,..., model.T_stable - 2}
            for s in time_steps:
                # Enforces eq. (26)
                t_minus_s = t - s * model.parameters.time_step
                model.add_constraint(
                    model.stable[t_minus_s] <= model.ON_FLAT[t],
                    f"minimum_time_STABLE_{model.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                )
    if model.T_stop >= 2:
        for t in model.time_frame:
            for s in model.stop_time_steps:
                t_minus_s = t - s * model.parameters.time_step
                # Enforces eq. (24)
                model.add_constraint(
                    model.turned_off[t_minus_s] <= model.STOP[t],
                    f"shutdown_ramp_of_{model.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                )
    if model.T_start >= 2:
        for t in model.time_frame:
            for s in model.start_time_steps:
                t_minus_s = t - s * model.parameters.time_step
                # Enforces eq. (17)
                model.add_constraint(
                    model.turned_on[t_minus_s] <= model.START[t],
                    f"start_up_ramp_of_{model.thermal_unit.name}_at_{t_minus_s}_for_{t}",
                )

    # D. CONSTRAINTS ON THE CONTROL VARIABLE

    # Start-up gradient:
    q_min = model.thermal_unit.minimum_power.max()
    q_step_down = q_min / model.T_stop
    q_step_up = q_min / model.T_start

    # Reserves requirements
    # We are in a case where there is a FLAT state, so manual reserves can only be provided
    # when the unit is in the FLAT state.

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
            <= model.q_lower.get_value(t)
            * (1 - model.ON_UP.get_value(t) - model.ON_FLAT[t] - model.ON_DOWN.get_value(t))
        )

    # impossible commitment and stable reserves constraints (eqs. (44) and (45))
    for t in model.time_frame:
        model.add_constraint(
            model.get_variable(model.automated_reserves_up_at(t))
            <= model.maximum_automated * (1 - model.OFF.get_value(t) - model.START[t] - model.STOP[t])
        )
        model.add_constraint(
            model.get_variable(model.automated_reserves_down_at(t))
            <= model.maximum_automated * (1 - model.OFF.get_value(t) - model.START[t] - model.STOP[t])
        )
        model.add_constraint(
            model.get_variable(model.reserves_up_equip_at(t))
            <= model.q_upper.get_value(t)
            * (
                1
                - model.ON_UP.get_value(t)
                - model.ON_DOWN.get_value(t)
                - model.OFF.get_value(t)
                - model.START[t]
                - model.STOP[t]
            )
        )
        # for compacity, implements both eq (44) and (45)
        model.add_constraint(
            model.get_variable(model.reserves_down_equip_at(t))
            <= model.q_upper.get_value(t)
            * (
                1
                - model.ON_UP.get_value(t)
                - model.ON_DOWN.get_value(t)
                - model.OFF.get_value(t)
                - model.START[t]
                - model.STOP[t]
            )
        )

    # Power output
    for t in model.time_frame:
        model.add_constraint(
            model.q[t]
            >= model.q_lower.get_value(t) * (model.ON_UP.get_value(t) + model.ON_DOWN.get_value(t) + model.ON_FLAT[t])
            + model.turned_off[t] * (q_min - q_step_down),
            f"lower_bound_of_{model.thermal_unit.name}_at_{t}",
        )  # Lower bound (eq. (33))
        model.add_constraint(
            model.q[t]
            <= model.q_upper.get_value(t) * (model.ON_UP.get_value(t) + model.ON_DOWN.get_value(t) + model.ON_FLAT[t])
            + (model.STOP[t] + model.START[t]) * q_min
            - model.turned_off[t] * q_step_down,
            f"upper_bound_of_{model.thermal_unit.name}_at_{t}",
        )  # Upper bound (eq. (34))

    # Power gradients
    if model.delta_q > 0:  # Case where the gradient is finite.
        for t in model.gradients_time_frame:  # The gradients are defined only up to T-1.
            t_next = t + model.parameters.time_step  # Get the next time step

            # Upward constrained gradient (eq. (35))
            model.add_constraint(
                model.q[t_next] - model.q[t]
                <= (
                    model.delta_q * model.entered_up[t]
                    + model.U[t]
                    + model.D[t]
                    - q_step_down * model.turned_off[t_next]
                    - model.STOP[t] * q_step_down
                    + q_step_up * model.turned_on[t_next]
                    + model.START[t] * q_step_up
                    - DD[t]
                ),
                f"upward_gradient_of_{model.thermal_unit.name}_at_{t}",
            )  # Upward gradient

            # Downward constrained gradient (eq. (37))
            model.add_constraint(
                model.q[t_next] - model.q[t]
                >= (
                    -model.delta_q * model.entered_down[t]
                    + model.U[t]
                    + model.D[t]
                    - q_step_down * model.turned_off[t_next]
                    - model.STOP[t] * q_step_down
                    + flat_down_stop[t_next] * model.delta_q
                    - DD[t]
                    + q_step_up * model.turned_on[t_next]
                    + model.START[t] * q_step_up
                ),
                f"downward_gradient_of_{model.thermal_unit.name}_at_{t}",
            )  # Downward gradient

    elif model.delta_q == 0:  # Case where the gradient is 'infinite'
        for t in model.gradients_time_frame:
            t_next = t + model.parameters.time_step  # Get the next time step

            # Upward unconstrained gradient (eq. (36))
            model.add_constraint(
                model.q[t_next] - model.q[t]
                <= (
                    model.delta_q_unconstrained * model.entered_up[t]
                    + model.U[t]
                    + model.D[t]
                    - q_step_down * model.turned_off[t_next]
                    - model.STOP[t] * q_step_down
                    + q_step_up * model.turned_on[t_next]
                    + model.START[t] * q_step_up
                    - DD[t]
                ),
                f"upward_gradient_of_{model.thermal_unit.name}_at_{t}",
            )  # Upward gradient

            # Downward unconstrained gradient (eq. (38))
            model.add_constraint(
                model.q[t_next] - model.q[t]
                >= (
                    -model.delta_q_unconstrained * model.entered_down[t]
                    + model.U[t]
                    + model.D[t]
                    - q_step_down * model.turned_off[t_next]
                    - model.STOP[t] * q_step_down
                    + flat_down_stop[t_next] * model.delta_q_unconstrained
                    - DD[t]
                    + q_step_up * model.turned_on[t_next]
                    + model.START[t] * q_step_up
                ),
                f"downward_gradient_of_{model.thermal_unit.name}_at_{t}",
            )  # Downward gradient

    else:  # Raise an error since no gradients have been detected.
        cfg.logger.error(
            f"*** WARNING ***\n No gradients have been defined for equipment {model.thermal_unit.name}. \n "
            "Please check the value of `maximum_gradient`."
        )
        raise ValueError("Missing gradients for thermic units.")

    model.create_daily_energy_constraint(model.thermal_unit, model.time_frame, model.parameters.time_step, model.q)
