import API
from PO_functions import get_date_to_clean_string
from System import DateTime


def GetVariablesAndConstraints_Thermics(
    time,
    equipments_DT,
    objFunction,
    constraintList,
    sum_power_level,
    contractedDifferenceUpti,
    contractedDifferenceDownti,
    automatedContractedDifferenceUpti,
    automatedContractedDifferenceDownti,
    priceForecast,
    p,
):
    # Preload some variables to avoid calling methods or functions too often
    time_str = get_date_to_clean_string(time)
    prev_time = time.AddMinutes(-p.time_step)
    optimes = p.thermal_op_times

    for equipment_name, PO_DTj in equipments_DT.items():
        stopTimeSteps = range(1, PO_DTj.T_stop - 1)
        startTimeSteps = range(1, PO_DTj.T_start - 1)

        # get objective function
        objFunction.Add(PO_DTj.VariableCost[time] * PO_DTj.PowerLevel[time] * p.time_step / 60.0)

        if time >= len(p.target_times):
            objFunction.Add(-priceForecast[time] * PO_DTj.PowerLevel[time] * p.time_step / 60.0)

        sum_power_level.Add(PO_DTj.PowerLevel[time])

        objFunction.Add(PO_DTj.StartupCost[time] * PO_DTj.turned_on[time])

        contractedDifferenceUpti.Add(PO_DTj.reservesUp[time])
        contractedDifferenceDownti.Add(PO_DTj.reservesDown[time])
        automatedContractedDifferenceUpti.Add(PO_DTj.automatedReservesUp[time])
        automatedContractedDifferenceDownti.Add(PO_DTj.automatedReservesDown[time])

        # ---------------------------------------------------------#
        #                                                         #
        ##### Combination 1 : T_stop = T_stable = T_start = 0 #####
        #                                                         #
        # ---------------------------------------------------------#
        if PO_DTj.T_stop == 0 and PO_DTj.T_start == 0 and PO_DTj.T_stable == 0:
            if p.debug and time == p.start_date:
                API.IO.Trace.Log(f"Equipment : {equipment_name}", API.IO.LogTypeInfo)
                API.IO.Trace.Log("Combination 1 for optimization constraints", API.IO.LogTypeInfo)
            # A. CONSTRAINTS ON THE AUXILIARY VARIABLES

            # These constraints define the auxiliary variables. In the first case, there are only two
            # of them: turned_on and turned_off.

            # Constraints on the indicator that the unit has started on t (turned_on, sec. 6.1.1)
            constraintList.Add(PO_DTj.turned_on[time] <= 1 - PO_DTj.OFF[time])
            constraintList.Add(PO_DTj.turned_on[time] <= PO_DTj.OFF[prev_time])
            constraintList.Add(PO_DTj.turned_on[time] >= PO_DTj.OFF[prev_time] - PO_DTj.OFF[time])

            # Constraints on turned_off (sec. 6.1.2)

            constraintList.Add(PO_DTj.turned_off[time] <= 1 - PO_DTj.OFF[prev_time])
            constraintList.Add(PO_DTj.turned_off[time] <= PO_DTj.OFF[time])
            constraintList.Add(PO_DTj.turned_off[time] >= PO_DTj.OFF[time] - PO_DTj.OFF[prev_time])

            # B. CONSTRAINTS ON THE STATE VARIABLES

            # Mutual exclusion constraint
            constraintList.Add(PO_DTj.OFF[time] + PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time] == 1)

            # Transitions:
            # None. All transitions are allowed

            # Mininum time on and minimum time off constraints:
            # if T_on >= 2 or T_off >= 2, lock the unit in this state.
            if PO_DTj.T_on >= 2:
                timeSteps = range(1, PO_DTj.T_on)  # Nombre de time steps sur lesquels on a une contrainte
                for s in timeSteps:
                    local_time = time.AddMinutes(-s * p.time_step)
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.turned_on[local_time] <= PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time],
                            "minimum_time_ON_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )
            if PO_DTj.T_off >= 2:
                timeSteps = range(1, PO_DTj.T_off)
                for s in timeSteps:
                    local_time = time.AddMinutes(-s * p.time_step)
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.turned_off[local_time] <= PO_DTj.OFF[time],
                            "minimum_time_OFF_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )

            # C. CONSTRAINTS ON THE CONTROL VARIABLE

            # Reserves requirements
            # We are in a case where there is no FLAT state, so manual reserves can be provided
            # as long as the unit is online.

            # Constraints on contractedDifference (eq. (40))
            # and on automatedContractedDifference (eq. (39))

            # Upward and downward "fill up" constraints.
            constraintList.Add(
                PO_DTj.PowerLevel[time]
                + PO_DTj.reservesUp[time]
                + PO_DTj.automatedReservesUp[time]
                + PO_DTj.unprovidedReservesUp[time]
                <= PO_DTj.q_upper[time] + p.allowed_round_off_error
            )  # Upward constraint - eq. (41)
            constraintList.Add(
                PO_DTj.PowerLevel[time]
                + PO_DTj.reservesUp[time]
                + PO_DTj.automatedReservesUp[time]
                + PO_DTj.unprovidedReservesUp[time]
                >= PO_DTj.q_upper[time] - p.allowed_round_off_error
            )  # Upward constraint - eq. (41)

            constraintList.Add(
                PO_DTj.PowerLevel[time]
                - PO_DTj.reservesDown[time]
                - PO_DTj.automatedReservesDown[time]
                - PO_DTj.unprovidedReservesDown[time]
                + PO_DTj.relaxedReserves[time]
                <= PO_DTj.q_lower[time] + p.allowed_round_off_error
            )  # Downward constraint - eq. (42)
            constraintList.Add(
                PO_DTj.PowerLevel[time]
                - PO_DTj.reservesDown[time]
                - PO_DTj.automatedReservesDown[time]
                - PO_DTj.unprovidedReservesDown[time]
                + PO_DTj.relaxedReserves[time]
                >= PO_DTj.q_lower[time] - p.allowed_round_off_error
            )  # Downward constraint - eq. (42)

            # relaxedReserve disabling condition (eq. (43))
            constraintList.Add(
                PO_DTj.relaxedReserves[time] <= PO_DTj.q_lower[time] * (1 - PO_DTj.ON_UP[time] - PO_DTj.ON_DOWN[time])
            )

            # impossible commitment and stable reserves constraints (eq. (44))
            constraintList.Add(PO_DTj.automatedReservesUp[time] <= PO_DTj.maximumAutomated * (1 - PO_DTj.OFF[time]))
            constraintList.Add(PO_DTj.automatedReservesDown[time] <= PO_DTj.maximumAutomated * (1 - PO_DTj.OFF[time]))
            constraintList.Add(PO_DTj.reservesUp[time] <= PO_DTj.q_upper[time] * (1 - PO_DTj.OFF[time]))
            constraintList.Add(PO_DTj.reservesDown[time] <= PO_DTj.q_upper[time] * (1 - PO_DTj.OFF[time]))

            # Power output
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.PowerLevel[time] >= PO_DTj.q_lower[time] * (PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time]),
                    "lower_bound_of_%s_at_%s" % (equipment_name, time_str),
                )
            )
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.PowerLevel[time] <= PO_DTj.q_upper[time] * (PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time]),
                    "upper_bound_of_%s_at_%s" % (equipment_name, time_str),
                )
            )

            # Power gradients
            # Definition of the gradientsTimeFrame: starts at startDate - p.time_step and goes until T-1
            # Gradients are defined on a "shifted" time frame -> we replace time with prev_time
            if time in optimes[: len(optimes) - 2]:
                if PO_DTj.Delta_Q > 0:  # Case where the gradient is finite.
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            <= (
                                PO_DTj.Delta_Q * PO_DTj.ON_UP[prev_time]
                                + PO_DTj.Delta_Q_unconstrained * PO_DTj.turned_on[time]
                            ),
                            "upward_gradient_of_%s_at_%s" % (equipment_name, prev_time),
                        )
                    )

                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            >= (
                                -PO_DTj.Delta_Q * PO_DTj.ON_DOWN[prev_time]
                                - PO_DTj.Delta_Q_unconstrained * PO_DTj.turned_off[time]
                            ),
                            "downward_gradient_of_%s_at_%s" % (equipment_name, prev_time),
                        )
                    )
                elif PO_DTj.Delta_Q == 0:  # Case where the gradient is 'infinite'
                    constraintList.Add(
                        PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                        <= (
                            PO_DTj.Delta_Q_unconstrained * PO_DTj.ON_UP[prev_time]
                            + PO_DTj.Delta_Q_unconstrained * PO_DTj.turned_on[time]
                        )
                    )
                    constraintList.Add(
                        PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                        >= (
                            -PO_DTj.Delta_Q_unconstrained * PO_DTj.ON_DOWN[prev_time]
                            - PO_DTj.Delta_Q_unconstrained * PO_DTj.turned_off[time]
                        )
                    )
                else:  # Raise an error since no gradients have been detected.
                    API.IO.Trace.Log(
                        "WARNING: No gradients have been defined for equipment%s. \n"
                        "Please check the value of MaximumGradient." % str(equipment_name),
                        API.IO.LogTypeInfo,
                    )
                    raise ValueError("Missing gradients for thermic units.")

            # Energy limits
            if PO_DTj.hasDailyEnergyConstraint:
                days_in_optimes = []

                for op_time in optimes:
                    if DateTime(op_time.Year, op_time.Month, op_time.Day, 0, 0, 0) not in days_in_optimes:
                        days_in_optimes.append(DateTime(op_time.Year, op_time.Month, op_time.Day, 0, 0, 0))

                for date in days_in_optimes:
                    upper_bound = PO_DTj.maximumDailyEnergy.GetValue(date)

                    matching_steps = []
                    for local_op_time in optimes:
                        if (
                            (local_op_time.Year == date.Year)
                            and (local_op_time.Month == date.Month)
                            and (local_op_time.Day == date.Day)
                        ):
                            matching_steps.append(local_op_time)

                    if matching_steps:  # Add a constraint only if the list of filtered dates is not empty.
                        # Enforce eq. (37)
                        constraintList.Add(
                            API.Solver.NewOpConstraint(
                                sum([PO_DTj.PowerLevel[t] for t in matching_steps])
                                <= upper_bound * p.time_step / 1440 * len(matching_steps),
                                "energy_limit_of_%s_at_%s" % (str(equipment_name), time_str),
                            )
                        )
                        # p.time_stepime / 1440 * len(matching_steps) is a converting factor

        # -------------------------------------------------------------#
        #                                                             #
        ##### Combination 2 : T_stop >= 1, T_stable = T_start = 0 #####
        #                                                             #
        # -------------------------------------------------------------#

        if PO_DTj.T_stop >= 1 and PO_DTj.T_start == 0 and PO_DTj.T_stable == 0:
            if p.debug and time == p.start_date:
                API.IO.Trace.Log(f"Equipment : {equipment_name}", API.IO.LogTypeInfo)
                API.IO.Trace.Log("Combination 2 for optimization constraints", API.IO.LogTypeInfo)
            # A. CONSTRAINTS ON THE AUXILIARY VARIABLES

            # These constraints define the auxiliary variables. In the first case, there are only two
            # of them: turned_on and turned_off.

            # Constraints on the indicator that the unit has started on t (turned_on, sec. 6.1.1)
            constraintList.Add(PO_DTj.turned_on[time] <= 1 - PO_DTj.OFF[time])
            constraintList.Add(PO_DTj.turned_on[time] <= PO_DTj.OFF[prev_time])
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.turned_on[time] >= PO_DTj.OFF[prev_time] - PO_DTj.OFF[time],
                    "constraints_defining_turned_on_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # Constraints on turned_off (sec. 6.1.2)
            # Defined here when entering the STOP state.
            constraintList.Add(PO_DTj.turned_off[time] <= 1 - PO_DTj.STOP[prev_time])
            constraintList.Add(PO_DTj.turned_off[time] <= PO_DTj.STOP[time])
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.turned_off[time] >= PO_DTj.STOP[time] - PO_DTj.STOP[prev_time],
                    "constraints_defining_turned_off_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # Constraints on delta_t_stop (sec. 6.1.5)

            constraintList.Add(PO_DTj.down_to_stop[time] <= 1 - PO_DTj.ON_DOWN[prev_time])
            constraintList.Add(PO_DTj.down_to_stop[time] <= PO_DTj.ON_DOWN[time])
            constraintList.Add(PO_DTj.down_to_stop[time] >= PO_DTj.ON_DOWN[time] - PO_DTj.ON_DOWN[prev_time])

            # B. CONSTRAINTS ON THE STATE VARIABLES

            # Mutual exclusion constraint
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.OFF[time] + PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time] + PO_DTj.STOP[time] == 1,
                    "mutual_exclusion_at_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # Transitions:
            # Transitions from OFF to STOP and STOP to ON_DOWN and ON_UP are forbidden
            # Direct transitions from ON_UP and ON_DOWN to OFF are forbidden.
            constraintList.Add(PO_DTj.STOP[prev_time] + PO_DTj.ON_UP[time] <= 1)
            constraintList.Add(PO_DTj.STOP[prev_time] + PO_DTj.ON_DOWN[time] <= 1)
            constraintList.Add(PO_DTj.OFF[prev_time] + PO_DTj.STOP[time] <= 1)
            constraintList.Add(PO_DTj.ON_UP[prev_time] + PO_DTj.OFF[time] <= 1)
            constraintList.Add(PO_DTj.ON_DOWN[prev_time] + PO_DTj.OFF[time] <= 1)
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.ON_DOWN[prev_time] + PO_DTj.OFF[time] <= 1,
                    "transitions_constraints_at_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # Eviction constraints.
            # Implements equation (19)
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.turned_off[time.AddMinutes(-(PO_DTj.T_stop - 1) * p.time_step)] + PO_DTj.STOP[time] <= 1,
                    "eviction_constraint_at_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # Mininum time on and minimum time off constraints:
            # if T_on >= 2, T_off >= 2 or T_stop >= 2, lock the unit in this state.
            if PO_DTj.T_on >= 2:
                timeSteps = range(1, PO_DTj.T_on)  # Nombre de time steps sur lesquels on a une contrainte
                for s in timeSteps:
                    local_time = time.AddMinutes(-s * p.time_step)
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.turned_on[local_time] <= PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time],
                            "minimum_time_ON_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )

            if PO_DTj.T_off >= 2:
                timeSteps = range(1, PO_DTj.T_off)
                for s in timeSteps:
                    local_time = time.AddMinutes(
                        -(s + PO_DTj.T_stop) * p.time_step
                    )  # Shift the index because the OFF is formally considered when entering the STOP state.
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.turned_off[local_time] <= PO_DTj.OFF[time],
                            "minimum_time_OFF_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )

            # TODO: clarify this
            if PO_DTj.T_stop >= 2:
                for s in stopTimeSteps:
                    local_time = time.AddMinutes(-s * p.time_step)
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.turned_off[local_time] <= PO_DTj.STOP[time],
                            "shutdown_ramp_of_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )

            """
            if PO_DTj.T_stop >= 2:
                timeSteps = range(1, PO_DTj.T_stop)
                for s in timeSteps:
                    local_time = time.AddMinutes(-s * p.time_step)
                    constraintList.Add(API.Solver.NewOpConstraint(PO_DTj.turned_off[local_time] <= PO_DTj.STOP[time],
                                                                  'shutdown_ramp_of_%s_at_%s_for_%s'%(equipment_name,
                                                                                                      get_date_to_clean_string(local_time),
                                                                                                      time_str)))
            """
            # C. CONSTRAINTS ON THE CONTROL VARIABLE

            # Shutdown gradient
            q_min = max(PO_DTj.MinimumPower.values())  # Get the minimumPower without the reserve requirements
            # q_step = q_min / (PO_DTj.T_stop + 1)  #Should be q_step = q_min / (PO_DTj.T_stop) #but it doesn't work
            q_step = q_min / (PO_DTj.T_stop)

            # Reserves requirements
            # We are in a case where there is no FLAT state, so manual reserves can be provided
            # as long as the unit is online.

            # Constraints on contractedDifference (eq. (40))
            # and on automatedContractedDifference (eq. (39))

            # Upward and downward "fill up" constraints.
            constraintList.Add(
                PO_DTj.PowerLevel[time]
                + PO_DTj.reservesUp[time]
                + PO_DTj.automatedReservesUp[time]
                + PO_DTj.unprovidedReservesUp[time]
                <= PO_DTj.q_upper[time] + p.allowed_round_off_error
            )  # Upward constraint - eq. (41)
            constraintList.Add(
                PO_DTj.PowerLevel[time]
                + PO_DTj.reservesUp[time]
                + PO_DTj.automatedReservesUp[time]
                + PO_DTj.unprovidedReservesUp[time]
                >= PO_DTj.q_upper[time] - p.allowed_round_off_error
            )  # Upward constraint - eq. (41)

            constraintList.Add(
                PO_DTj.PowerLevel[time]
                - PO_DTj.reservesDown[time]
                - PO_DTj.automatedReservesDown[time]
                - PO_DTj.unprovidedReservesDown[time]
                + PO_DTj.relaxedReserves[time]
                <= PO_DTj.q_lower[time] + p.allowed_round_off_error
            )  # Downward constraint - eq. (42)
            constraintList.Add(
                PO_DTj.PowerLevel[time]
                - PO_DTj.reservesDown[time]
                - PO_DTj.automatedReservesDown[time]
                - PO_DTj.unprovidedReservesDown[time]
                + PO_DTj.relaxedReserves[time]
                >= PO_DTj.q_lower[time] - p.allowed_round_off_error
            )  # Downward constraint - eq. (42)

            # relaxedReserve disabling condition (eq. (43))
            constraintList.Add(
                PO_DTj.relaxedReserves[time] <= PO_DTj.q_lower[time] * (1 - PO_DTj.ON_UP[time] - PO_DTj.ON_DOWN[time])
            )

            # impossible commitment and stable reserves constraints (eq. (44))
            constraintList.Add(
                PO_DTj.automatedReservesUp[time] <= PO_DTj.maximumAutomated * (1 - PO_DTj.OFF[time] - PO_DTj.STOP[time])
            )
            constraintList.Add(
                PO_DTj.automatedReservesDown[time]
                <= PO_DTj.maximumAutomated * (1 - PO_DTj.OFF[time] - PO_DTj.STOP[time])
            )
            constraintList.Add(
                PO_DTj.reservesUp[time] <= PO_DTj.q_upper[time] * (1 - PO_DTj.OFF[time] - PO_DTj.STOP[time])
            )
            constraintList.Add(
                PO_DTj.reservesDown[time] <= PO_DTj.q_upper[time] * (1 - PO_DTj.OFF[time] - PO_DTj.STOP[time])
            )

            # Power output
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.PowerLevel[time]
                    >= (
                        PO_DTj.q_lower[time] * (PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time])
                        + PO_DTj.turned_off[time] * (q_min - q_step)
                    ),
                    "lower_bound_of_%s_at_%s" % (equipment_name, time_str),
                )
            )  # Lower bound
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.PowerLevel[time]
                    <= (
                        PO_DTj.q_upper[time] * (PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time])
                        + PO_DTj.STOP[time] * q_min
                        - PO_DTj.turned_off[time] * q_step
                    ),
                    "upper_bound_of_%s_at_%s" % (equipment_name, time_str),
                )
            )  # Upper bound

            # Power gradients
            # Definition of the gradientsTimeFrame: starts at startDate - p.time_stepime and goes until T-1
            # Gradients are defined on a "shifted" time frame.

            if time in optimes[: len(optimes) - 2]:
                if PO_DTj.Delta_Q > 0:  # Case where the gradient is finite.
                    # NB. The downward gradient implemented here requires the unit to be at most at deltaQ in order to be able to enter the stop state.
                    # The resulting constraint set is considerably more constraining than if the gradient was relaxed.
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            <= (
                                PO_DTj.Delta_Q * PO_DTj.ON_UP[prev_time]
                                - PO_DTj.turned_off[time] * q_step
                                - PO_DTj.STOP[prev_time] * q_step
                                + PO_DTj.Delta_Q_unconstrained * PO_DTj.turned_on[time]
                            ),
                            "upward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Upward gradient

                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            >= (
                                -PO_DTj.Delta_Q * PO_DTj.ON_DOWN[prev_time]
                                - PO_DTj.turned_off[time] * q_step
                                - PO_DTj.STOP[prev_time] * q_step
                                + PO_DTj.down_to_stop[time] * PO_DTj.Delta_Q
                            ),
                            "downward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Downward gradient

                elif PO_DTj.Delta_Q == 0:  # Case where the gradient is 'infinite'
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            <= (
                                PO_DTj.Delta_Q_unconstrained * PO_DTj.ON_UP[prev_time]
                                - PO_DTj.turned_off[time] * q_step
                                - PO_DTj.STOP[prev_time] * q_step
                                + PO_DTj.Delta_Q_unconstrained * PO_DTj.turned_on[time]
                            ),
                            "unconstrained_upward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Upward gradient

                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            >= (
                                -PO_DTj.Delta_Q_unconstrained * PO_DTj.ON_DOWN[prev_time]
                                - PO_DTj.turned_off[time] * q_step
                                - PO_DTj.STOP[prev_time] * q_step
                                + PO_DTj.Delta_Q_unconstrained * PO_DTj.down_to_stop[time]
                            ),
                            "unconstrained_downward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Downward gradient

                else:  # Raise an error since no gradients have been detected.
                    API.IO.Trace.Log(
                        "*** WARNING ***\n No gradients have been defined for equipment%s. \n"
                        "Please check the value of `MaximumGradient`." % equipment_name,
                        API.IO.LogTypeInfo,
                    )
                    raise ValueError("Missing gradients for thermic units.")

            # Energy limits
            if PO_DTj.hasDailyEnergyConstraint:
                days_in_optimes = []

                for op_time in optimes:
                    if DateTime(op_time.Year, op_time.Month, op_time.Day, 0, 0, 0) not in days_in_optimes:
                        days_in_optimes.append(DateTime(op_time.Year, op_time.Month, op_time.Day, 0, 0, 0))

                for date in days_in_optimes:
                    upper_bound = PO_DTj.maximumDailyEnergy.GetValue(date)

                    matching_steps = []
                    for local_op_time in optimes:
                        if (
                            (local_op_time.Year == date.Year)
                            and (local_op_time.Month == date.Month)
                            and (local_op_time.Day == date.Day)
                        ):
                            matching_steps.append(local_op_time)

                    if matching_steps:  # Add a constraint only if the list of filtered dates is not empty.
                        # Enforce eq. (37)
                        constraintList.Add(
                            API.Solver.NewOpConstraint(
                                sum([PO_DTj.PowerLevel[t] for t in matching_steps])
                                <= upper_bound * p.time_step / 1440 * len(matching_steps),
                                "energy_limit_of_%s_at_%s" % (str(equipment_name), time_str),
                            )
                        )
                        # p.time_stepime / 1440 * len(matching_steps) is a converting factor

        # -------------------------------------------------------------#
        #                                                             #
        #### Combination 3 : T_stop = 0, T_stable >= 1 T_start = 0 ####
        #                                                             #
        # -------------------------------------------------------------#

        if PO_DTj.T_stop == 0 and PO_DTj.T_start == 0 and PO_DTj.T_stable >= 1:
            if p.debug and time == p.start_date:
                API.IO.Trace.Log(f"Equipment : {equipment_name}", API.IO.LogTypeInfo)
                API.IO.Trace.Log("Combination 3 for optimization constraints", API.IO.LogTypeInfo)
            # A. CONSTRAINTS ON THE AUXILIARY VARIABLES

            # These constraints define the auxiliary variables. In the first case, there are only two
            # of them: turned_on and turned_off.

            # Constraints on the indicator that the unit has started on t (turned_on, sec. 6.1.1)
            constraintList.Add(PO_DTj.turned_on[time] <= 1 - PO_DTj.OFF[time])
            constraintList.Add(PO_DTj.turned_on[time] <= PO_DTj.OFF[prev_time])
            constraintList.Add(PO_DTj.turned_on[time] >= PO_DTj.OFF[prev_time] - PO_DTj.OFF[time])

            # Constraints on turned_off (sec. 6.1.2)
            constraintList.Add(PO_DTj.turned_off[time] <= 1 - PO_DTj.OFF[prev_time])
            constraintList.Add(PO_DTj.turned_off[time] <= PO_DTj.OFF[time])
            constraintList.Add(PO_DTj.turned_off[time] >= PO_DTj.OFF[time] - PO_DTj.OFF[prev_time])

            # delta_t_stable (sec. 6.1.3.)
            constraintList.Add(PO_DTj.stable[time] <= 1 - PO_DTj.ON_FLAT[prev_time])
            constraintList.Add(PO_DTj.stable[time] <= PO_DTj.ON_FLAT[time])
            constraintList.Add(PO_DTj.stable[time] >= PO_DTj.ON_FLAT[time] - PO_DTj.ON_FLAT[prev_time])

            # entered_up and entered_down auxiliaries
            # single_on_up
            constraintList.Add(PO_DTj.entered_up[time] <= 1 - PO_DTj.ON_UP[prev_time])
            constraintList.Add(PO_DTj.entered_up[time] <= PO_DTj.ON_UP[time])
            constraintList.Add(PO_DTj.entered_up[time] >= PO_DTj.ON_UP[time] - PO_DTj.ON_UP[prev_time])
            # single_on_down
            constraintList.Add(PO_DTj.entered_down[time] <= 1 - PO_DTj.ON_DOWN[prev_time])
            constraintList.Add(PO_DTj.entered_down[time] <= PO_DTj.ON_DOWN[time])
            constraintList.Add(PO_DTj.entered_down[time] >= PO_DTj.ON_DOWN[time] - PO_DTj.ON_DOWN[prev_time])

            if time == p.start_date:  # add constraints to match time_frame_union_minus_one in BO
                constraintList.Add(PO_DTj.stable[prev_time] <= 1 - PO_DTj.ON_FLAT[time.AddMinutes(-2 * p.time_step)])
                constraintList.Add(PO_DTj.stable[prev_time] <= PO_DTj.ON_FLAT[prev_time])
                constraintList.Add(
                    PO_DTj.stable[prev_time]
                    >= PO_DTj.ON_FLAT[prev_time] - PO_DTj.ON_FLAT[time.AddMinutes(-2 * p.time_step)]
                )

                # entered_up and entered_down auxiliaries
                # single_on_up
                constraintList.Add(PO_DTj.entered_up[prev_time] <= 1 - PO_DTj.ON_UP[time.AddMinutes(-2 * p.time_step)])
                constraintList.Add(PO_DTj.entered_up[prev_time] <= PO_DTj.ON_UP[prev_time])
                constraintList.Add(
                    PO_DTj.entered_up[prev_time]
                    >= PO_DTj.ON_UP[prev_time] - PO_DTj.ON_UP[time.AddMinutes(-2 * p.time_step)]
                )
                # single_on_down
                constraintList.Add(
                    PO_DTj.entered_down[prev_time] <= 1 - PO_DTj.ON_DOWN[time.AddMinutes(-2 * p.time_step)]
                )
                constraintList.Add(PO_DTj.entered_down[prev_time] <= PO_DTj.ON_DOWN[prev_time])
                constraintList.Add(
                    PO_DTj.entered_down[prev_time]
                    >= PO_DTj.ON_DOWN[prev_time] - PO_DTj.ON_DOWN[time.AddMinutes(-2 * p.time_step)]
                )

            # UP and DOWN "semi-continuous" variables for the gradient.
            # These auxiliary variables model the fact that if the unit is increasing (decreasing) its
            # power output twice in a row, then the second time the gradient is locked.
            # In practice, these variables are defined in two stages

            # First stage: tilde_U and tilde_D
            # tilde_U
            constraintList.Add(PO_DTj.tilde_U[time] <= PO_DTj.Q_max * PO_DTj.ON_UP[prev_time])
            constraintList.Add(PO_DTj.tilde_U[time] >= PO_DTj.Q_min * PO_DTj.ON_UP[prev_time])
            constraintList.Add(
                PO_DTj.tilde_U[time]
                <= (
                    PO_DTj.PowerLevel[time]
                    - PO_DTj.PowerLevel[prev_time]
                    - PO_DTj.Q_min * (1 - PO_DTj.ON_UP[prev_time])
                )
            )
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.tilde_U[time]
                    >= (
                        PO_DTj.PowerLevel[time]
                        - PO_DTj.PowerLevel[prev_time]
                        - PO_DTj.Q_max * (1 - PO_DTj.ON_UP[prev_time])
                    ),
                    "VALUE_of_tilde_UP_at_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # tilde_D
            constraintList.Add(PO_DTj.tilde_D[time] <= PO_DTj.Q_max * PO_DTj.ON_DOWN[prev_time])
            constraintList.Add(PO_DTj.tilde_D[time] >= PO_DTj.Q_min * PO_DTj.ON_DOWN[prev_time])
            constraintList.Add(
                PO_DTj.tilde_D[time]
                <= (
                    PO_DTj.PowerLevel[time]
                    - PO_DTj.PowerLevel[prev_time]
                    - PO_DTj.Q_min * (1 - PO_DTj.ON_DOWN[prev_time])
                )
            )
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.tilde_D[time]
                    >= (
                        PO_DTj.PowerLevel[time]
                        - PO_DTj.PowerLevel[prev_time]
                        - PO_DTj.Q_max * (1 - PO_DTj.ON_DOWN[prev_time])
                    ),
                    "VALUE_of_tilde_DOWN_at_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # Second stage: U and D
            # These variables will be added to the gradient constraints.
            # U
            constraintList.Add(PO_DTj.U[time] <= PO_DTj.Q_max * PO_DTj.ON_UP[time])
            constraintList.Add(PO_DTj.U[time] >= PO_DTj.Q_min * PO_DTj.ON_UP[time])
            constraintList.Add(PO_DTj.U[time] <= PO_DTj.tilde_U[time] - PO_DTj.Q_min * (1 - PO_DTj.ON_UP[time]))
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.U[time] >= PO_DTj.tilde_U[time] - PO_DTj.Q_max * (1 - PO_DTj.ON_UP[time]),
                    "VALUE_of_UP_at_%s_for_%s" % (time_str, equipment_name),
                )
            )
            # D
            constraintList.Add(PO_DTj.D[time] <= PO_DTj.Q_max * PO_DTj.ON_DOWN[time])
            constraintList.Add(PO_DTj.D[time] >= PO_DTj.Q_min * PO_DTj.ON_DOWN[time])
            constraintList.Add(PO_DTj.D[time] <= PO_DTj.tilde_D[time] - PO_DTj.Q_min * (1 - PO_DTj.ON_DOWN[time]))
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.D[time] >= PO_DTj.tilde_D[time] - PO_DTj.Q_max * (1 - PO_DTj.ON_DOWN[time]),
                    "VALUE_of_DOWN_at_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # B. CONSTRAINTS ON THE STATE VARIABLES

            # Mutual exclusion constraint
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.OFF[time] + PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time] + PO_DTj.ON_FLAT[time] == 1,
                    "mutual_exclusion_at_%s_for_%s" % (time_str, equipment_name),
                )
            )
            if time == p.start_date:  # add constraints to match time_frame_union_minus_one in BO
                constraintList.Add(
                    API.Solver.NewOpConstraint(
                        PO_DTj.OFF[prev_time]
                        + PO_DTj.ON_UP[prev_time]
                        + PO_DTj.ON_DOWN[prev_time]
                        + PO_DTj.ON_FLAT[prev_time]
                        == 1,
                        "mutual_exclusion_at_%s_for_%s" % (get_date_to_clean_string(prev_time), equipment_name),
                    )
                )

            # Transitions:
            # UP-DOWN and DOWN-UP transitions are forbidden.
            constraintList.Add(PO_DTj.ON_UP[prev_time] + PO_DTj.ON_DOWN[time] <= 1)
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.ON_DOWN[prev_time] + PO_DTj.ON_UP[time] <= 1,
                    "transitions_constraints_at_%s_for_%s" % (time_str, equipment_name),
                )
            )
            if time == p.start_date:  # add constraints to match time_frame_union_minus_one in BO
                constraintList.Add(PO_DTj.ON_UP[time.AddMinutes(-2 * p.time_step)] + PO_DTj.ON_DOWN[prev_time] <= 1)
                constraintList.Add(
                    API.Solver.NewOpConstraint(
                        PO_DTj.ON_DOWN[time.AddMinutes(-2 * p.time_step)] + PO_DTj.ON_UP[prev_time] <= 1,
                        "transitions_constraints_at_%s" % (get_date_to_clean_string(prev_time)),
                    )
                )

            # Mininum time on and minimum time off constraints:
            # if T_on >= 2 or T_off >= 2 or T_stable >= 2, lock the unit in this state.
            if PO_DTj.T_on >= 2:
                timeSteps = range(1, PO_DTj.T_on)
                for s in timeSteps:
                    local_time = time.AddMinutes(-s * p.time_step)
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.turned_on[local_time]
                            <= PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time] + PO_DTj.ON_FLAT[time],
                            "minimum_time_ON_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )
            if PO_DTj.T_off >= 2:
                timeSteps = range(1, PO_DTj.T_off)
                for s in timeSteps:
                    local_time = time.AddMinutes(-s * p.time_step)
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.turned_off[local_time] <= PO_DTj.OFF[time],
                            "minimum_time_OFF_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )
            if PO_DTj.T_stable >= 2:
                timeSteps = range(1, PO_DTj.T_stable - 1)
                for s in timeSteps:
                    local_time = time.AddMinutes(-s * p.time_step)
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.stable[local_time] <= PO_DTj.ON_FLAT[time],
                            "minimum_time_STABLE_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )

            ##########################################################
            # C. CONSTRAINTS ON THE CONTROL VARIABLE

            # Reserve requirements: adjust the power bounds if necessary
            # Upward requirements
            # Reserves requirements
            # We are in a case where there is no FLAT state, so manual reserves can be provided
            # as long as the unit is online.

            # Constraints on contractedDifference (eq. (40))
            # and on automatedContractedDifference (eq. (39))

            # Upward and downward "fill up" constraints.
            constraintList.Add(
                PO_DTj.PowerLevel[time]
                + PO_DTj.reservesUp[time]
                + PO_DTj.automatedReservesUp[time]
                + PO_DTj.unprovidedReservesUp[time]
                <= PO_DTj.q_upper[time] + p.allowed_round_off_error
            )  # Upward constraint - eq. (41)
            constraintList.Add(
                PO_DTj.PowerLevel[time]
                + PO_DTj.reservesUp[time]
                + PO_DTj.automatedReservesUp[time]
                + PO_DTj.unprovidedReservesUp[time]
                >= PO_DTj.q_upper[time] - p.allowed_round_off_error
            )  # Upward constraint - eq. (41)
            constraintList.Add(
                PO_DTj.PowerLevel[time]
                - PO_DTj.reservesDown[time]
                - PO_DTj.automatedReservesDown[time]
                - PO_DTj.unprovidedReservesDown[time]
                + PO_DTj.relaxedReserves[time]
                <= PO_DTj.q_lower[time] + p.allowed_round_off_error
            )  # Downward constraint - eq. (42)
            constraintList.Add(
                PO_DTj.PowerLevel[time]
                - PO_DTj.reservesDown[time]
                - PO_DTj.automatedReservesDown[time]
                - PO_DTj.unprovidedReservesDown[time]
                + PO_DTj.relaxedReserves[time]
                >= PO_DTj.q_lower[time] - p.allowed_round_off_error
            )  # Downward constraint - eq. (42)

            # relaxedReserve disabling condition (eq. (43))
            constraintList.Add(
                PO_DTj.relaxedReserves[time]
                <= PO_DTj.q_lower[time] * (1 - PO_DTj.ON_UP[time] - PO_DTj.ON_FLAT[time] - PO_DTj.ON_DOWN[time])
            )

            # impossible commitment and stable reserves constraints (eq. (44))
            constraintList.Add(PO_DTj.automatedReservesUp[time] <= PO_DTj.maximumAutomated * (1 - PO_DTj.OFF[time]))
            constraintList.Add(PO_DTj.automatedReservesDown[time] <= PO_DTj.maximumAutomated * (1 - PO_DTj.OFF[time]))
            constraintList.Add(
                PO_DTj.reservesUp[time]
                <= PO_DTj.q_upper[time] * (1 - PO_DTj.OFF[time] - PO_DTj.ON_UP[time] - PO_DTj.ON_DOWN[time])
            )
            constraintList.Add(
                PO_DTj.reservesDown[time]
                <= PO_DTj.q_upper[time] * (1 - PO_DTj.OFF[time] - PO_DTj.ON_UP[time] - PO_DTj.ON_DOWN[time])
            )

            # Power output
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.PowerLevel[time]
                    >= PO_DTj.q_lower[time] * (PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time] + PO_DTj.ON_FLAT[time]),
                    "lower_bound_of_%s_at_%s" % (equipment_name, time_str),
                )
            )  # Lower bound

            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.PowerLevel[time]
                    <= PO_DTj.q_upper[time] * (PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time] + PO_DTj.ON_FLAT[time]),
                    "upper_bound_of_%s_at_%s" % (equipment_name, time_str),
                )
            )  # Upper bound

            # Power gradients
            if time in optimes[: len(optimes) - 2]:
                if PO_DTj.Delta_Q > 0:  # Case where the gradient is finite.
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            <= (
                                PO_DTj.Delta_Q * PO_DTj.entered_up[prev_time]
                                + PO_DTj.U[prev_time]
                                + PO_DTj.D[prev_time]
                                + PO_DTj.Delta_Q_unconstrained * PO_DTj.turned_on[time]
                            ),
                            "upward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Upward gradient

                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            >= (
                                -PO_DTj.Delta_Q * PO_DTj.entered_down[prev_time]
                                + PO_DTj.U[prev_time]
                                + PO_DTj.D[prev_time]
                                - PO_DTj.Delta_Q_unconstrained * PO_DTj.turned_off[time]
                            ),
                            "downward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Downward gradient

                elif PO_DTj.Delta_Q == 0:  # Case where the gradient is 'infinite'
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            <= (
                                PO_DTj.Delta_Q_unconstrained * PO_DTj.entered_up[prev_time]
                                + PO_DTj.U[prev_time]
                                + PO_DTj.D[prev_time]
                                + PO_DTj.Delta_Q_unconstrained * PO_DTj.turned_on[time]
                            ),
                            "unconstrained_upward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Upward gradient

                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            >= (
                                -PO_DTj.Delta_Q_unconstrained * PO_DTj.entered_down[prev_time]
                                + PO_DTj.U[prev_time]
                                + PO_DTj.D[prev_time]
                                - PO_DTj.Delta_Q_unconstrained * PO_DTj.turned_off[time]
                            ),
                            "unconstrained_downward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Downward gradient
                else:  # Raise an error since no gradients have been detected.
                    API.IO.Trace.Log(
                        "*** WARNING ***\n No gradients have been defined for equipment%s. \n"
                        "Please check the value of `MaximumGradient`." % equipment_name,
                        API.IO.LogTypeInfo,
                    )
                    raise ValueError("Missing gradients for thermic units.")

            # Energy limits
            if PO_DTj.hasDailyEnergyConstraint:
                days_in_optimes = []

                for op_time in optimes:
                    if DateTime(op_time.Year, op_time.Month, op_time.Day, 0, 0, 0) not in days_in_optimes:
                        days_in_optimes.append(DateTime(op_time.Year, op_time.Month, op_time.Day, 0, 0, 0))

                for date in days_in_optimes:
                    upper_bound = PO_DTj.maximumDailyEnergy.GetValue(date)

                    matching_steps = []
                    for local_op_time in optimes:
                        if (
                            (local_op_time.Year == date.Year)
                            and (local_op_time.Month == date.Month)
                            and (local_op_time.Day == date.Day)
                        ):
                            matching_steps.append(local_op_time)

                    if matching_steps:  # Add a constraint only if the list of filtered dates is not empty.
                        # Enforce eq. (37)
                        constraintList.Add(
                            API.Solver.NewOpConstraint(
                                sum([PO_DTj.PowerLevel[t] for t in matching_steps])
                                <= upper_bound * p.time_step / 1440 * len(matching_steps),
                                "energy_limit_of_%s_at_%s" % (str(equipment_name), time_str),
                            )
                        )
                        # p.time_stepime / 1440 * len(matching_steps) is a converting factor

        # -------------------------------------------------------------#
        #                                                             #
        ##### Combination 4 : T_start >= 1, T_stable = T_stop = 0 #####
        #                                                             #
        # -------------------------------------------------------------#

        if PO_DTj.T_start >= 1 and PO_DTj.T_stop == 0 and PO_DTj.T_stable == 0:
            # In this case, there are four state variables and three auxiliary variables.
            if p.debug and time == p.start_date:
                API.IO.Trace.Log(f"Equipment : {equipment_name}", API.IO.LogTypeInfo)
                API.IO.Trace.Log("Combination 4 for optimization constraints", API.IO.LogTypeInfo)
            # A. CONSTRAINTS ON THE AUXILIARY VARIABLES

            # Constraints on the indicator that the unit has started on t (turned_on, sec. 6.1.1)
            # Defined here when entering the START state as in eq. (3)
            constraintList.Add(PO_DTj.turned_on[time] <= 1 - PO_DTj.OFF[time])
            constraintList.Add(PO_DTj.turned_on[time] <= PO_DTj.OFF[prev_time])
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.turned_on[time] >= PO_DTj.OFF[prev_time] - PO_DTj.OFF[time],
                    "constraints_defining_turned_on_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # Constraints on turned_off (sec. 6.1.2)
            # Defined here when entering the OFF state as in eq. (4) because T_stop = 0
            constraintList.Add(PO_DTj.turned_off[time] <= 1 - PO_DTj.OFF[prev_time])
            constraintList.Add(PO_DTj.turned_off[time] <= PO_DTj.OFF[time])
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.turned_off[time] >= PO_DTj.OFF[time] - PO_DTj.OFF[prev_time],
                    "constraints_defining_turned_off_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # C. CONSTRAINTS ON THE STATE VARIABLES

            # Mutual exclusion constraint
            # Enforces eq. (11)
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.OFF[time] + PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time] + PO_DTj.START[time] == 1,
                    "mutual_exclusion_at_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # Transitions:
            # Transitions from ON_UP and ON_DOWN to START and START to OFF are forbidden
            # Direct transitions from OFF to ON_UP and ON_DOWN are forbidden.

            constraintList.Add(PO_DTj.ON_UP[prev_time] + PO_DTj.START[time] <= 1)  # eq. (12)
            constraintList.Add(PO_DTj.ON_DOWN[prev_time] + PO_DTj.START[time] <= 1)  # eq. (12)
            constraintList.Add(PO_DTj.START[prev_time] + PO_DTj.OFF[time] <= 1)  # eq. (13)
            constraintList.Add(PO_DTj.OFF[prev_time] + PO_DTj.ON_UP[time] <= 1)  # eq. (17)
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.OFF[prev_time] + PO_DTj.ON_DOWN[time] <= 1,
                    "transitions_constraints_at_%s_for_%s" % (time_str, equipment_name),
                )
            )  # eq. (17)

            # Eviction constraint. This constraint forces the unit to leave the START state once the startup phase is finished.:
            # Implement eqution (16)
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.turned_on[time.AddMinutes(-p.time_step * (PO_DTj.T_start - 1))] + PO_DTj.START[time] <= 1,
                    "eviction_constraint_at_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # Mininum time on and minimum time off constraints:
            if PO_DTj.T_on >= 2:
                timeSteps = range(1, PO_DTj.T_on)
                for s in timeSteps:
                    # Enforce eq. (27) with T_start > 0
                    local_time = time.AddMinutes(-(s + PO_DTj.T_start) * p.time_step)
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.turned_on[local_time] <= PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time],
                            "minimum_time_ON_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )
            if PO_DTj.T_off >= 2:
                timeSteps = range(1, PO_DTj.T_off)
                for s in timeSteps:
                    local_time = time.AddMinutes(-s * p.time_step)
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.turned_off[local_time] <= PO_DTj.OFF[time],
                            "minimum_time_OFF_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )
            """
            if PO_DTj.T_start >= 2:
                timeSteps = range(1, PO_DTj.T_start)
                for s in timeSteps:
                    local_time = time.AddMinutes(-s * p.time_step)
                    constraintList.Add(API.Solver.NewOpConstraint(PO_DTj.turned_on[local_time] <= PO_DTj.START[time],
                                                                  'startup_ramp_of_%s_at_%s_for_%s'%(equipment_name,
                                                                                                     get_date_to_clean_string(local_time),
                                                                                                     time_str)))
            """

            if PO_DTj.T_start >= 2:
                for s in startTimeSteps:
                    local_time = time.AddMinutes(-s * p.time_step)
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.turned_on[local_time] <= PO_DTj.START[time],
                            "startup_ramp_of_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )

            # C. CONSTRAINTS ON THE CONTROL VARIABLE

            # Shutdown gradient
            q_min = max(PO_DTj.MinimumPower.values())  # Get the minimumPower without the reserve requirements

            # TODO: to be clarified
            # q_step = q_min / (PO_DTj.T_start +1)
            q_step = q_min / (PO_DTj.T_start)

            # Reserves requirements
            # We are in a case where there is no FLAT state, so manual reserves can be provided
            # as long as the unit is online.

            # Constraints on contractedDifference (eq. (40))
            # and on automatedContractedDifference (eq. (39))

            # Upward and downward "fill up" constraints.
            constraintList.Add(
                PO_DTj.PowerLevel[time]
                + PO_DTj.reservesUp[time]
                + PO_DTj.automatedReservesUp[time]
                + PO_DTj.unprovidedReservesUp[time]
                <= PO_DTj.q_upper[time] + p.allowed_round_off_error
            )  # Upward constraint - eq. (41)
            constraintList.Add(
                PO_DTj.PowerLevel[time]
                + PO_DTj.reservesUp[time]
                + PO_DTj.automatedReservesUp[time]
                + PO_DTj.unprovidedReservesUp[time]
                >= PO_DTj.q_upper[time] - p.allowed_round_off_error
            )  # Upward constraint - eq. (41)

            constraintList.Add(
                PO_DTj.PowerLevel[time]
                - PO_DTj.reservesDown[time]
                - PO_DTj.automatedReservesDown[time]
                - PO_DTj.unprovidedReservesDown[time]
                + PO_DTj.relaxedReserves[time]
                <= PO_DTj.q_lower[time] + p.allowed_round_off_error
            )  # Downward constraint - eq. (42)
            constraintList.Add(
                PO_DTj.PowerLevel[time]
                - PO_DTj.reservesDown[time]
                - PO_DTj.automatedReservesDown[time]
                - PO_DTj.unprovidedReservesDown[time]
                + PO_DTj.relaxedReserves[time]
                >= PO_DTj.q_lower[time] - p.allowed_round_off_error
            )  # Downward constraint - eq. (42)

            # relaxedReserve disabling condition (eq. (43))
            constraintList.Add(
                PO_DTj.relaxedReserves[time] <= PO_DTj.q_lower[time] * (1 - PO_DTj.ON_UP[time] - PO_DTj.ON_DOWN[time])
            )

            # impossible commitment and stable reserves constraints (eq. (44))
            constraintList.Add(
                PO_DTj.automatedReservesUp[time]
                <= PO_DTj.maximumAutomated * (1 - PO_DTj.OFF[time] - PO_DTj.START[time])
            )
            constraintList.Add(
                PO_DTj.automatedReservesDown[time]
                <= PO_DTj.maximumAutomated * (1 - PO_DTj.OFF[time] - PO_DTj.START[time])
            )
            constraintList.Add(
                PO_DTj.reservesUp[time] <= PO_DTj.q_upper[time] * (1 - PO_DTj.OFF[time] - PO_DTj.START[time])
            )
            constraintList.Add(
                PO_DTj.reservesDown[time] <= PO_DTj.q_upper[time] * (1 - PO_DTj.OFF[time] - PO_DTj.START[time])
            )

            # Power output
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.PowerLevel[time] >= PO_DTj.q_lower[time] * (PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time]),
                    "lower_bound_of_%s_at_%s" % (equipment_name, time_str),
                )
            )  # Lower bound

            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.PowerLevel[time]
                    <= (
                        PO_DTj.q_upper[time] * (PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time]) + PO_DTj.START[time] * q_min
                    ),
                    "upper_bound_of_%s_at_%s" % (equipment_name, time_str),
                )
            )  # Upper bound

            # Power gradients
            # Definition of the gradientsTimeFrame: starts at startDate - p.time_stepime and goes until T-1
            # Gradients are defined on a "shifted" time frame.
            if time in optimes[: len(optimes) - 2]:
                if PO_DTj.Delta_Q > 0:  # Case where the gradient is finite.
                    # NB. The downward gradient implemented here requires the unit to be at most at deltaQ in order to be able to enter the stop state.
                    # The resulting constraint set is considerably more constraining than if the gradient was relaxed.
                    # Upward constrained gradient (eq. (33))
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            <= (
                                PO_DTj.Delta_Q * PO_DTj.ON_UP[prev_time]
                                + PO_DTj.turned_on[time] * q_step
                                + PO_DTj.START[prev_time] * q_step
                            ),
                            "upward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Upward gradient

                    # Downward constrained gradient (eq. (35))
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            >= (
                                -PO_DTj.Delta_Q * PO_DTj.ON_DOWN[prev_time]
                                + PO_DTj.turned_on[time] * q_step
                                + PO_DTj.START[prev_time] * q_step
                                - PO_DTj.Delta_Q_unconstrained * PO_DTj.turned_off[time]
                            ),
                            "downward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Downward gradient

                elif PO_DTj.Delta_Q == 0:  # Case where the gradient is 'infinite'
                    # Upward unconstrained gradient (eq. (34))
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            <= (
                                PO_DTj.Delta_Q_unconstrained * PO_DTj.ON_UP[prev_time]
                                + PO_DTj.turned_on[time] * q_step
                                + PO_DTj.START[prev_time] * q_step
                            ),
                            "unconstrained_upward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Upward gradient

                    # Downward unconstrained gradient (eq. (36))
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            >= (
                                -PO_DTj.Delta_Q_unconstrained * PO_DTj.ON_DOWN[prev_time]
                                + PO_DTj.turned_on[time] * q_step
                                + PO_DTj.START[prev_time] * q_step
                                - PO_DTj.Delta_Q_unconstrained * PO_DTj.turned_off[time]
                            ),
                            "unconstrained_downward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Downward gradient

                else:  # Raise an error since no gradients have been detected.
                    API.IO.Trace.Log(
                        "*** WARNING ***\n No gradients have been defined for equipment%s. \n"
                        " Please check the value of `MaximumGradient`." % equipment_name,
                        API.IO.LogTypeInfo,
                    )
                    raise ValueError("Missing gradients for thermic units.")

            # Energy limits
            if PO_DTj.hasDailyEnergyConstraint:
                days_in_optimes = []

                for op_time in optimes:
                    if DateTime(op_time.Year, op_time.Month, op_time.Day, 0, 0, 0) not in days_in_optimes:
                        days_in_optimes.append(DateTime(op_time.Year, op_time.Month, op_time.Day, 0, 0, 0))

                for date in days_in_optimes:
                    upper_bound = PO_DTj.maximumDailyEnergy.GetValue(date)

                    matching_steps = []
                    for local_op_time in optimes:
                        if (
                            (local_op_time.Year == date.Year)
                            and (local_op_time.Month == date.Month)
                            and (local_op_time.Day == date.Day)
                        ):
                            matching_steps.append(local_op_time)

                    if matching_steps:  # Add a constraint only if the list of filtered dates is not empty.
                        # Enforce eq. (37)
                        constraintList.Add(
                            API.Solver.NewOpConstraint(
                                sum([PO_DTj.PowerLevel[t] for t in matching_steps])
                                <= upper_bound * p.time_step / 1440 * len(matching_steps),
                                "energy_limit_of_%s_at_%s" % (str(equipment_name), time_str),
                            )
                        )
                        # p.time_stepime / 1440 * len(matching_steps) is a converting factor

        # -------------------------------------------------------------#
        #                                                             #
        ###   Combination 5 : T_start =0, T_stable = T_stop >= 1    ###
        #                                                             #
        # -------------------------------------------------------------#

        if PO_DTj.T_stop >= 1 and PO_DTj.T_start == 0 and PO_DTj.T_stable >= 1:
            if p.debug and time == p.start_date:
                API.IO.Trace.Log(f"Equipment : {equipment_name}", API.IO.LogTypeInfo)
                API.IO.Trace.Log("Combination 5 for optimization constraints", API.IO.LogTypeInfo)
            # In this case, there are four state variables and the following auxiliary variables:
            #     - turned_on[t] and turned_off[t], indicating whether the unit has been turned on or off
            #     - stable[t], indicating whether the unit entered the stable state
            #     - U[t] and D[t], implemented in two stages with tilde_D[t], tilde_D[t] as the first stage
            #     - entered_up[t] and entered_down[t] indicating that the unit entered the UP or down STATE
            #
            # We review the initial conditions, then the constraints on the state variables
            # and finally the constraints on the power output.

            # PREAMBLE
            # Definition of two additional auxiliary variables needed specifically to handle this case,
            # flat_down_stop, which detects when the unit follows a FLAT(t-2) - DOWN(t-1) and STOP(t) path
            # and DD, which detects if the unit is to be stopped at t+1 (i.e. STOP(t+1) = 1) after having been
            # in the DOWN state at time steps t and t-1.

            # A. CONSTRAINTS ON THE AUXILIARY VARIABLES

            # These constraints define the auxiliary variables. In the first case, there are only two
            # of them: turned_on and turned_off.

            # Constraints on the indicator that the unit has started on t
            # Enforces eq. (3)
            constraintList.Add(PO_DTj.turned_on[time] <= 1 - PO_DTj.OFF[time])
            constraintList.Add(PO_DTj.turned_on[time] <= PO_DTj.OFF[prev_time])
            constraintList.Add(PO_DTj.turned_on[time] >= PO_DTj.OFF[prev_time] - PO_DTj.OFF[time])

            # Constraints on turned_off
            # Enforces eq. (5) as there a STOP state in this case.
            constraintList.Add(PO_DTj.turned_off[time] <= 1 - PO_DTj.STOP[prev_time])
            constraintList.Add(PO_DTj.turned_off[time] <= PO_DTj.STOP[time])
            constraintList.Add(PO_DTj.turned_off[time] >= PO_DTj.STOP[time] - PO_DTj.STOP[prev_time])

            # stable auxiliary variable
            # Enforces eq. (6)
            constraintList.Add(PO_DTj.stable[time] <= 1 - PO_DTj.ON_FLAT[prev_time])
            constraintList.Add(PO_DTj.stable[time] <= PO_DTj.ON_FLAT[time])
            constraintList.Add(PO_DTj.stable[time] >= PO_DTj.ON_FLAT[time] - PO_DTj.ON_FLAT[prev_time])
            if time == p.start_date:  # add an index to match timeFrame_union_minus_one
                constraintList.Add(PO_DTj.stable[prev_time] <= 1 - PO_DTj.ON_FLAT[time.AddMinutes(-2 * p.time_step)])
                constraintList.Add(PO_DTj.stable[prev_time] <= PO_DTj.ON_FLAT[prev_time])
                constraintList.Add(
                    PO_DTj.stable[prev_time]
                    >= PO_DTj.ON_FLAT[prev_time] - PO_DTj.ON_FLAT[time.AddMinutes(-2 * p.time_step)]
                )

            # flat_down_stop auxiliary (eq. (22))
            constraintList.Add(PO_DTj.flat_down_stop[time] <= PO_DTj.STOP[time])
            constraintList.Add(PO_DTj.flat_down_stop[time] <= PO_DTj.ON_DOWN[prev_time])
            constraintList.Add(PO_DTj.flat_down_stop[time] <= PO_DTj.ON_FLAT[time.AddMinutes(-2 * p.time_step)])
            constraintList.Add(
                PO_DTj.flat_down_stop[time]
                >= PO_DTj.STOP[time] + PO_DTj.ON_DOWN[prev_time] + PO_DTj.ON_FLAT[time.AddMinutes(-2 * p.time_step)] - 2
            )

            # entered_up and entered_down auxiliaries
            # entered_up (eq. (7))
            constraintList.Add(PO_DTj.entered_up[time] <= 1 - PO_DTj.ON_UP[prev_time])
            constraintList.Add(PO_DTj.entered_up[time] <= PO_DTj.ON_UP[time])
            constraintList.Add(PO_DTj.entered_up[time] >= PO_DTj.ON_UP[time] - PO_DTj.ON_UP[prev_time])
            # entered_down (eq. (8))
            constraintList.Add(PO_DTj.entered_down[time] <= 1 - PO_DTj.ON_DOWN[prev_time])
            constraintList.Add(PO_DTj.entered_down[time] <= PO_DTj.ON_DOWN[time])
            constraintList.Add(PO_DTj.entered_down[time] >= PO_DTj.ON_DOWN[time] - PO_DTj.ON_DOWN[prev_time])

            if time == p.start_date:  # add an index to match timeFrame_union_minus_one
                constraintList.Add(PO_DTj.entered_up[prev_time] <= 1 - PO_DTj.ON_UP[time.AddMinutes(-2 * p.time_step)])
                constraintList.Add(PO_DTj.entered_up[prev_time] <= PO_DTj.ON_UP[prev_time])
                constraintList.Add(
                    PO_DTj.entered_up[prev_time]
                    >= PO_DTj.ON_UP[prev_time] - PO_DTj.ON_UP[time.AddMinutes(-2 * p.time_step)]
                )

                constraintList.Add(
                    PO_DTj.entered_down[prev_time] <= 1 - PO_DTj.ON_DOWN[time.AddMinutes(-2 * p.time_step)]
                )
                constraintList.Add(PO_DTj.entered_down[prev_time] <= PO_DTj.ON_DOWN[prev_time])
                constraintList.Add(
                    PO_DTj.entered_down[prev_time]
                    >= PO_DTj.ON_DOWN[prev_time] - PO_DTj.ON_DOWN[time.AddMinutes(-2 * p.time_step)]
                )

            # UP and DOWN auxiliary variables for the gradient.
            # These auxiliary variables model the fact that if the unit is increasing (decreasing) its
            # power output twice in a row, then the second time the gradient is locked.
            # In practice, these variables are defined in two stages

            # First stage: tilde_U and tilde_D i
            # tilde_U (eq. (28))
            constraintList.Add(PO_DTj.tilde_U[time] <= PO_DTj.Q_max * PO_DTj.ON_UP[prev_time])
            constraintList.Add(PO_DTj.tilde_U[time] >= PO_DTj.Q_min * PO_DTj.ON_UP[prev_time])
            constraintList.Add(
                PO_DTj.tilde_U[time]
                <= (
                    PO_DTj.PowerLevel[time]
                    - PO_DTj.PowerLevel[prev_time]
                    - PO_DTj.Q_min * (1 - PO_DTj.ON_UP[prev_time])
                )
            )
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.tilde_U[time]
                    >= (
                        PO_DTj.PowerLevel[time]
                        - PO_DTj.PowerLevel[prev_time]
                        - PO_DTj.Q_max * (1 - PO_DTj.ON_UP[prev_time])
                    ),
                    "VALUE_of_tilde_UP_at_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # tilde_D (eq. (30))
            constraintList.Add(PO_DTj.tilde_D[time] <= PO_DTj.Q_max * PO_DTj.ON_DOWN[prev_time])
            constraintList.Add(PO_DTj.tilde_D[time] >= PO_DTj.Q_min * PO_DTj.ON_DOWN[prev_time])
            constraintList.Add(
                PO_DTj.tilde_D[time]
                <= (
                    PO_DTj.PowerLevel[time]
                    - PO_DTj.PowerLevel[prev_time]
                    - PO_DTj.Q_min * (1 - PO_DTj.ON_DOWN[prev_time])
                )
            )
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.tilde_D[time]
                    >= (
                        PO_DTj.PowerLevel[time]
                        - PO_DTj.PowerLevel[prev_time]
                        - PO_DTj.Q_max * (1 - PO_DTj.ON_DOWN[prev_time])
                    ),
                    "VALUE_of_tilde_DOWN_at_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # Second stage: U and D
            # These variables wil be added to the gradient constraints.
            # U (eq. (27))
            constraintList.Add(PO_DTj.U[time] <= PO_DTj.Q_max * PO_DTj.ON_UP[time])
            constraintList.Add(PO_DTj.U[time] >= PO_DTj.Q_min * PO_DTj.ON_UP[time])
            constraintList.Add(PO_DTj.U[time] <= PO_DTj.tilde_U[time] - PO_DTj.Q_min * (1 - PO_DTj.ON_UP[time]))
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.U[time] >= PO_DTj.tilde_U[time] - PO_DTj.Q_max * (1 - PO_DTj.ON_UP[time]),
                    "VALUE_of_UP_at_%s_for_%s" % (time_str, equipment_name),
                )
            )
            # D (eq. (29))
            constraintList.Add(PO_DTj.D[time] <= PO_DTj.Q_max * PO_DTj.ON_DOWN[time])
            constraintList.Add(PO_DTj.D[time] >= PO_DTj.Q_min * PO_DTj.ON_DOWN[time])
            constraintList.Add(PO_DTj.D[time] <= PO_DTj.tilde_D[time] - PO_DTj.Q_min * (1 - PO_DTj.ON_DOWN[time]))
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.D[time] >= PO_DTj.tilde_D[time] - PO_DTj.Q_max * (1 - PO_DTj.ON_DOWN[time]),
                    "VALUE_of_DOWN_at_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # DD Gradient auxiliary (eq. (23))
            if time in optimes[: len(optimes) - 2]:  # condition to match the gradientsTimeFrame
                constraintList.Add(PO_DTj.DD[prev_time] <= PO_DTj.Q_max * PO_DTj.STOP[time])
                constraintList.Add(PO_DTj.DD[prev_time] >= PO_DTj.Q_min * PO_DTj.STOP[time])
                constraintList.Add(PO_DTj.DD[prev_time] <= PO_DTj.D[prev_time] - PO_DTj.Q_min * (1 - PO_DTj.STOP[time]))
                constraintList.Add(
                    API.Solver.NewOpConstraint(
                        PO_DTj.DD[prev_time] >= PO_DTj.D[prev_time] - PO_DTj.Q_max * (1 - PO_DTj.STOP[time]),
                        "DD_gradient_auxiliary_at_%s_for_%s" % (time_str, equipment_name),
                    )
                )

            # B. CONSTRAINTS ON THE STATE VARIABLES

            # Mutual exclusion constraint
            # Defined over the whole time frame.
            # Enforces eq. (9)
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.OFF[time]
                    + PO_DTj.ON_UP[time]
                    + PO_DTj.ON_DOWN[time]
                    + PO_DTj.ON_FLAT[time]
                    + PO_DTj.STOP[time]
                    == 1,
                    "mutual_exclusion_at_%s_for_%s" % (time_str, equipment_name),
                )
            )
            if time == p.start_date:  # add an index to match timeFrame_union_minus_one
                constraintList.Add(
                    API.Solver.NewOpConstraint(
                        PO_DTj.OFF[prev_time]
                        + PO_DTj.ON_UP[prev_time]
                        + PO_DTj.ON_DOWN[prev_time]
                        + PO_DTj.ON_FLAT[prev_time]
                        + PO_DTj.STOP[prev_time]
                        == 1,
                        "mutual_exclusion_at_%s_for_%s" % (get_date_to_clean_string(prev_time), equipment_name),
                    )
                )

            # Transitions:
            # UP-DOWN and DOWN-UP transitions are forbidden.
            # STOP to ON transitions are also forbidden
            # OFF to STOP transitions
            # ON_XX to OFF is forbidden
            # Finally, we forbid ON_UP to STOP (which never happens in practice) in order
            # to avoid defining a UU auxiliary analoguous to DD.
            # Implement eq. (25)

            constraintList.Add(PO_DTj.ON_UP[prev_time] + PO_DTj.ON_DOWN[time] <= 1)
            constraintList.Add(PO_DTj.ON_DOWN[prev_time] + PO_DTj.ON_UP[time] <= 1)
            constraintList.Add(PO_DTj.ON_UP[prev_time] + PO_DTj.OFF[time] <= 1)
            constraintList.Add(PO_DTj.ON_DOWN[prev_time] + PO_DTj.OFF[time] <= 1)

            # Eq (13)
            constraintList.Add(PO_DTj.STOP[prev_time] + PO_DTj.ON_FLAT[time] <= 1)
            constraintList.Add(PO_DTj.STOP[prev_time] + PO_DTj.ON_DOWN[time] <= 1)
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.STOP[prev_time] + PO_DTj.ON_UP[time] <= 1,
                    "transitions_constraints_on_timeFrame_union_minus_one_at_%s_for_%s" % (time_str, equipment_name),
                )
            )
            if time == p.start_date:  # add an index to match timeFrame_union_minus_one
                constraintList.Add(PO_DTj.ON_UP[time.AddMinutes(-2 * p.time_step)] + PO_DTj.ON_DOWN[prev_time] <= 1)
                constraintList.Add(PO_DTj.ON_DOWN[time.AddMinutes(-2 * p.time_step)] + PO_DTj.ON_UP[prev_time] <= 1)

                constraintList.Add(PO_DTj.STOP[time.AddMinutes(-2 * p.time_step)] + PO_DTj.ON_FLAT[prev_time] <= 1)
                constraintList.Add(PO_DTj.STOP[time.AddMinutes(-2 * p.time_step)] + PO_DTj.ON_DOWN[prev_time] <= 1)
                constraintList.Add(
                    API.Solver.NewOpConstraint(
                        PO_DTj.STOP[time.AddMinutes(-2 * p.time_step)] + PO_DTj.ON_UP[prev_time] <= 1,
                        "transitions_constraints_on_timeFrame_union_minus_one_at_%s_for_%s"
                        % (get_date_to_clean_string(prev_time), equipment_name),
                    )
                )

            # ON_UP to STOP transition (eq. (21))
            constraintList.Add(PO_DTj.ON_UP[prev_time] + PO_DTj.STOP[time] <= 1)
            # Eq. (12)
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.OFF[prev_time] + PO_DTj.STOP[time] <= 1,
                    "transitions_constraints_at_%s_for_%s" % (time_str, equipment_name),
                )
            )
            # The latter constraints are only defined on the timeFrame because it does not involve ON variables at the t index.

            # Eviction constraint
            # The unit must leave the STOP state after T_stop time steps.
            # Implements equation (19)
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.turned_off[time.AddMinutes(-p.time_step * (PO_DTj.T_stop - 1))] + PO_DTj.STOP[time] <= 1,
                    "eviction_constraint_at_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # Mininum time on and minimum time off constraints:
            # if T_on >= 2 or T_off >= 2 or T_stable >= 2, lock the unit in this state.
            if PO_DTj.T_on >= 2:
                timeSteps = range(1, PO_DTj.T_on)  # Corresponds to the set {1,..., T_on - 1}
                for s in timeSteps:
                    # Enforces eq. (31), with T_start = 0
                    local_time = time.AddMinutes(-s * p.time_step)
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.turned_on[local_time]
                            <= (PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time] + PO_DTj.ON_FLAT[time]),
                            "minimum_time_ON_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )
                if time == p.start_date:  # add an index to match timeFrame_union_minus_one
                    for s in timeSteps:
                        local_time = time.AddMinutes(-(s + 1) * p.time_step)
                        constraintList.Add(
                            API.Solver.NewOpConstraint(
                                PO_DTj.turned_on[local_time]
                                <= (PO_DTj.ON_UP[prev_time] + PO_DTj.ON_DOWN[prev_time] + PO_DTj.ON_FLAT[prev_time]),
                                "minimum_time_ON_%s_at_%s_for_%s"
                                % (
                                    equipment_name,
                                    get_date_to_clean_string(local_time),
                                    get_date_to_clean_string(prev_time),
                                ),
                            )
                        )

            if PO_DTj.T_off >= 2:
                timeSteps = range(1, PO_DTj.T_off)  # Corresponds to the set {1,..., T_off - 1}
                for s in timeSteps:
                    # Enforces eq. (32) with T_stop > 0
                    local_time = time.AddMinutes(-(s + PO_DTj.T_stop) * p.time_step)
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.turned_off[local_time] <= PO_DTj.OFF[time],
                            "minimum_time_OFF_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )
            if PO_DTj.T_stable >= 2:
                timeSteps = range(1, PO_DTj.T_stable - 1)  # Corresponds to the set {1,..., T_stable - 1}
                for s in timeSteps:
                    # Enforces eq. (26)
                    local_time = time.AddMinutes(-s * p.time_step)
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.stable[local_time] <= PO_DTj.ON_FLAT[time],
                            "minimum_time_STABLE_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )
                if time == p.start_date:  # add an index to match timeFrame_union_minus_one
                    for s in timeSteps:
                        local_time = time.AddMinutes(-(s + 1) * p.time_step)
                        constraintList.Add(
                            API.Solver.NewOpConstraint(
                                PO_DTj.stable[local_time] <= PO_DTj.ON_FLAT[prev_time],
                                "minimum_time_STABLE_%s_at_%s_for_%s"
                                % (
                                    equipment_name,
                                    get_date_to_clean_string(local_time),
                                    get_date_to_clean_string(prev_time),
                                ),
                            )
                        )
            if PO_DTj.T_stop >= 2:
                for s in stopTimeSteps:
                    # Enforces eq. (24)
                    local_time = time.AddMinutes(-s * p.time_step)
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.turned_off[local_time] <= PO_DTj.STOP[time],
                            "shutdown_ramp_of_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )

            # C. CONSTRAINTS ON THE CONTROL VARIABLE

            # Shutdown gradient
            q_min = max(PO_DTj.MinimumPower.values())  # Get the minimumPower without the reserve requirements

            # TODO: mistake here, T_start taken instead of T_stop
            # q_step = q_min / (PO_DTj.T_stop + 1)
            q_step = q_min / (PO_DTj.T_stop)

            # Reserves requirements
            # We are in a case where there is no FLAT state, so manual reserves can be provided
            # as long as the unit is online.

            # Constraints on contractedDifference (eq. (40))
            # and on automatedContractedDifference (eq. (39))

            # Upward and downward "fill up" constraints.
            constraintList.Add(
                PO_DTj.PowerLevel[time]
                + PO_DTj.reservesUp[time]
                + PO_DTj.automatedReservesUp[time]
                + PO_DTj.unprovidedReservesUp[time]
                <= PO_DTj.q_upper[time] + p.allowed_round_off_error
            )  # Upward constraint - eq. (41)
            constraintList.Add(
                PO_DTj.PowerLevel[time]
                + PO_DTj.reservesUp[time]
                + PO_DTj.automatedReservesUp[time]
                + PO_DTj.unprovidedReservesUp[time]
                >= PO_DTj.q_upper[time] - p.allowed_round_off_error
            )  # Upward constraint - eq. (41)

            constraintList.Add(
                PO_DTj.PowerLevel[time]
                - PO_DTj.reservesDown[time]
                - PO_DTj.automatedReservesDown[time]
                - PO_DTj.unprovidedReservesDown[time]
                + PO_DTj.relaxedReserves[time]
                <= PO_DTj.q_lower[time] + p.allowed_round_off_error
            )  # Downward constraint - eq. (42)
            constraintList.Add(
                PO_DTj.PowerLevel[time]
                - PO_DTj.reservesDown[time]
                - PO_DTj.automatedReservesDown[time]
                - PO_DTj.unprovidedReservesDown[time]
                + PO_DTj.relaxedReserves[time]
                >= PO_DTj.q_lower[time] - p.allowed_round_off_error
            )  # Downward constraint - eq. (42)

            # relaxedReserve disabling condition (eq. (43))
            constraintList.Add(
                PO_DTj.relaxedReserves[time]
                <= PO_DTj.q_lower[time] * (1 - PO_DTj.ON_UP[time] - PO_DTj.ON_FLAT[time] - PO_DTj.ON_DOWN[time])
            )

            # impossible commitment and stable reserves constraints (eq. (44))
            constraintList.Add(
                PO_DTj.automatedReservesUp[time] <= PO_DTj.maximumAutomated * (1 - PO_DTj.OFF[time] - PO_DTj.STOP[time])
            )
            constraintList.Add(
                PO_DTj.automatedReservesDown[time]
                <= PO_DTj.maximumAutomated * (1 - PO_DTj.OFF[time] - PO_DTj.STOP[time])
            )
            constraintList.Add(
                PO_DTj.reservesUp[time]
                <= PO_DTj.q_upper[time]
                * (1 - PO_DTj.ON_UP[time] - PO_DTj.ON_DOWN[time] - PO_DTj.OFF[time] - PO_DTj.STOP[time])
            )
            constraintList.Add(
                PO_DTj.reservesDown[time]
                <= PO_DTj.q_upper[time]
                * (1 - PO_DTj.ON_UP[time] - PO_DTj.ON_DOWN[time] - PO_DTj.OFF[time] - PO_DTj.STOP[time])
            )

            # Power output
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.PowerLevel[time]
                    >= (
                        PO_DTj.q_lower[time] * (PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time] + PO_DTj.ON_FLAT[time])
                        + PO_DTj.turned_off[time] * (q_min - q_step)
                    ),
                    "lower_bound_of_%s_at_%s" % (equipment_name, time_str),
                )
            )  # Lower bound

            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.PowerLevel[time]
                    <= (
                        PO_DTj.q_upper[time] * (PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time] + PO_DTj.ON_FLAT[time])
                        + PO_DTj.STOP[time] * q_min
                        - PO_DTj.turned_off[time] * q_step
                    ),
                    "upper_bound_of_%s_at_%s" % (equipment_name, time_str),
                )
            )  # Upper bound

            # Power gradients
            # Definition of the gradientsTimeFrame: starts at startDate - p.time_stepime and goes until T-1
            # Gradients are defined on a "shifted" time frame.
            if time in optimes[: len(optimes) - 2]:
                if PO_DTj.Delta_Q > 0:  # Case where the gradient is finite.
                    # NB. The downward gradient implemented here requires the unit to be at most at deltaQ in order to be able to enter the stop state.
                    # The resulting constraint set is considerably more constraining than if the gradient was relaxed.

                    # Upward constrained gradient (eq. (33))
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            <= (
                                PO_DTj.Delta_Q * PO_DTj.entered_up[prev_time]
                                + PO_DTj.U[prev_time]
                                + PO_DTj.D[prev_time]
                                - q_step * PO_DTj.turned_off[time]
                                - PO_DTj.STOP[prev_time] * q_step
                                + PO_DTj.Delta_Q_unconstrained * PO_DTj.turned_on[time]
                                - PO_DTj.DD[prev_time]
                            ),
                            "upward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Upward gradient

                    # Downward constrained gradient (eq. (35))
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            >= (
                                -PO_DTj.Delta_Q * PO_DTj.entered_down[prev_time]
                                + PO_DTj.U[prev_time]
                                + PO_DTj.D[prev_time]
                                - q_step * PO_DTj.turned_off[time]
                                - PO_DTj.STOP[prev_time] * q_step
                                + PO_DTj.flat_down_stop[time] * PO_DTj.Delta_Q
                                - PO_DTj.DD[prev_time]
                            ),
                            "downward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Downward gradient

                elif PO_DTj.Delta_Q == 0:  # Case where the gradient is 'infinite'
                    # Upward unconstrained gradient (eq. (34))
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            <= (
                                PO_DTj.Delta_Q_unconstrained * PO_DTj.entered_up[prev_time]
                                + PO_DTj.U[prev_time]
                                + PO_DTj.D[prev_time]
                                - q_step * PO_DTj.turned_off[time]
                                - PO_DTj.STOP[prev_time] * q_step
                                + PO_DTj.Delta_Q_unconstrained * PO_DTj.turned_on[time]
                            ),
                            "unconstrained_upward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Upward gradient

                    # Downward unconstrained gradient (eq. (36))
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            >= (
                                -PO_DTj.Delta_Q_unconstrained * PO_DTj.entered_down[prev_time]
                                + PO_DTj.U[prev_time]
                                + PO_DTj.D[prev_time]
                                - q_step * PO_DTj.turned_off[time]
                                - PO_DTj.STOP[prev_time] * q_step
                                + PO_DTj.flat_down_stop[time] * PO_DTj.Delta_Q_unconstrained
                                - PO_DTj.DD[prev_time]
                            ),
                            "unconstrained_downward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Downward gradient

                else:  # Raise an error since no gradients have been detected.
                    API.IO.Trace.Log(
                        "*** WARNING ***\n No gradients have been defined for equipment%s. \n "
                        "Please check the value of `MaximumGradient`." % equipment_name,
                        API.IO.LogTypeInfo,
                    )
                    raise ValueError("Missing gradients for thermic units.")

            # Energy limits
            if PO_DTj.hasDailyEnergyConstraint:
                days_in_optimes = []

                for op_time in optimes:
                    if DateTime(op_time.Year, op_time.Month, op_time.Day, 0, 0, 0) not in days_in_optimes:
                        days_in_optimes.append(DateTime(op_time.Year, op_time.Month, op_time.Day, 0, 0, 0))

                for date in days_in_optimes:
                    upper_bound = PO_DTj.maximumDailyEnergy.GetValue(date)

                    matching_steps = []
                    for local_op_time in optimes:
                        if (
                            (local_op_time.Year == date.Year)
                            and (local_op_time.Month == date.Month)
                            and (local_op_time.Day == date.Day)
                        ):
                            matching_steps.append(local_op_time)

                    if matching_steps:  # Add a constraint only if the list of filtered dates is not empty.
                        # Enforce eq. (37)
                        constraintList.Add(
                            API.Solver.NewOpConstraint(
                                sum([PO_DTj.PowerLevel[t] for t in matching_steps])
                                <= upper_bound * p.time_step / 1440 * len(matching_steps),
                                "energy_limit_of_%s_at_%s" % (str(equipment_name), time_str),
                            )
                        )
                        # p.time_stepime / 1440 * len(matching_steps) is a converting factor

        # -------------------------------------------------------------#
        #                                                             #
        ###   Combination 6 : T_stop = 0, T_stable = T_start >= 1   ###
        #                                                             #
        # -------------------------------------------------------------#

        if PO_DTj.T_stop == 0 and PO_DTj.T_start >= 1 and PO_DTj.T_stable >= 1:
            # In this case, there are five state variables and the following auxiliary variables:
            #     - turned_on[t] and turned_off[t], indicating whether the unit has been turned on or off
            #     - stable[t], indicating whether the unit entered the stable state
            #     - U[t] and D[t], implemented in two stages with tilde_D[t], tilde_D[t] as the first stage
            #     - entered_up[t] and entered_down[t] indicating that the unit entered the UP or down STATE
            #
            # We review the initial conditions, then the constraints on the state variables
            # and finally the constraints on the power output.
            if p.debug and time == p.start_date:
                API.IO.Trace.Log(f"Equipment : {equipment_name}", API.IO.LogTypeInfo)
                API.IO.Trace.Log("Combination 6 for optimization constraints", API.IO.LogTypeInfo)

            # A. CONSTRAINTS ON THE AUXILIARY VARIABLES

            # These constraints define the auxiliary variables. In the first case, there are only two
            # of them: turned_on and turned_off.

            # Constraints on the indicator that the unit has started on t
            # Enforces eq. (3)
            constraintList.Add(PO_DTj.turned_on[time] <= 1 - PO_DTj.OFF[time])
            constraintList.Add(PO_DTj.turned_on[time] <= PO_DTj.OFF[prev_time])
            constraintList.Add(PO_DTj.turned_on[time] >= PO_DTj.OFF[prev_time] - PO_DTj.OFF[time])

            # Constraints on turned_off
            # Enforces eq. (4) as there is no STOP state in this case.
            constraintList.Add(PO_DTj.turned_off[time] <= 1 - PO_DTj.OFF[prev_time])
            constraintList.Add(PO_DTj.turned_off[time] <= PO_DTj.OFF[time])
            constraintList.Add(PO_DTj.turned_off[time] >= PO_DTj.OFF[time] - PO_DTj.OFF[prev_time])

            # stable auxiliary variable
            # Enforces eq. (6)
            constraintList.Add(PO_DTj.stable[time] <= 1 - PO_DTj.ON_FLAT[prev_time])
            constraintList.Add(PO_DTj.stable[time] <= PO_DTj.ON_FLAT[time])
            constraintList.Add(PO_DTj.stable[time] >= PO_DTj.ON_FLAT[time] - PO_DTj.ON_FLAT[prev_time])
            if time == p.start_date:
                constraintList.Add(PO_DTj.stable[prev_time] <= 1 - PO_DTj.ON_FLAT[time.AddMinutes(-2 * p.time_step)])
                constraintList.Add(PO_DTj.stable[prev_time] <= PO_DTj.ON_FLAT[prev_time])
                constraintList.Add(
                    PO_DTj.stable[prev_time]
                    >= PO_DTj.ON_FLAT[prev_time] - PO_DTj.ON_FLAT[time.AddMinutes(-2 * p.time_step)]
                )

            # entered_up and entered_down auxiliaries
            # entered_up (eq. (7))
            constraintList.Add(PO_DTj.entered_up[time] <= 1 - PO_DTj.ON_UP[prev_time])
            constraintList.Add(PO_DTj.entered_up[time] <= PO_DTj.ON_UP[time])
            constraintList.Add(PO_DTj.entered_up[time] >= PO_DTj.ON_UP[time] - PO_DTj.ON_UP[prev_time])
            # entered_down (eq. (8))
            constraintList.Add(PO_DTj.entered_down[time] <= 1 - PO_DTj.ON_DOWN[prev_time])
            constraintList.Add(PO_DTj.entered_down[time] <= PO_DTj.ON_DOWN[time])
            constraintList.Add(PO_DTj.entered_down[time] >= PO_DTj.ON_DOWN[time] - PO_DTj.ON_DOWN[prev_time])

            if time == p.start_date:
                constraintList.Add(PO_DTj.entered_up[prev_time] <= 1 - PO_DTj.ON_UP[time.AddMinutes(-2 * p.time_step)])
                constraintList.Add(PO_DTj.entered_up[prev_time] <= PO_DTj.ON_UP[prev_time])
                constraintList.Add(
                    PO_DTj.entered_up[prev_time]
                    >= PO_DTj.ON_UP[prev_time] - PO_DTj.ON_UP[time.AddMinutes(-2 * p.time_step)]
                )
                # entered_down (eq. (8))
                constraintList.Add(
                    PO_DTj.entered_down[prev_time] <= 1 - PO_DTj.ON_DOWN[time.AddMinutes(-2 * p.time_step)]
                )
                constraintList.Add(PO_DTj.entered_down[prev_time] <= PO_DTj.ON_DOWN[prev_time])
                constraintList.Add(
                    PO_DTj.entered_down[prev_time]
                    >= PO_DTj.ON_DOWN[prev_time] - PO_DTj.ON_DOWN[time.AddMinutes(-2 * p.time_step)]
                )

            # UP and DOWN auxiliary variables for the gradient.
            # These auxiliary variables model the fact that if the unit is increasing (decreasing) its
            # power output twice in a row, then the second time the gradient is locked.
            # In practice, these variables are defined in two stages

            # First stage: tilde_U and tilde_D
            # tilde_U (eq. (28))
            constraintList.Add(PO_DTj.tilde_U[time] <= PO_DTj.Q_max * PO_DTj.ON_UP[prev_time])
            constraintList.Add(PO_DTj.tilde_U[time] >= PO_DTj.Q_min * PO_DTj.ON_UP[prev_time])
            constraintList.Add(
                PO_DTj.tilde_U[time]
                <= (
                    PO_DTj.PowerLevel[time]
                    - PO_DTj.PowerLevel[prev_time]
                    - PO_DTj.Q_min * (1 - PO_DTj.ON_UP[prev_time])
                )
            )
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.tilde_U[time]
                    >= (
                        PO_DTj.PowerLevel[time]
                        - PO_DTj.PowerLevel[prev_time]
                        - PO_DTj.Q_max * (1 - PO_DTj.ON_UP[prev_time])
                    ),
                    "VALUE_of_tilde_UP_at_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # tilde_D (eq. (30))
            constraintList.Add(PO_DTj.tilde_D[time] <= PO_DTj.Q_max * PO_DTj.ON_DOWN[prev_time])
            constraintList.Add(PO_DTj.tilde_D[time] >= PO_DTj.Q_min * PO_DTj.ON_DOWN[prev_time])
            constraintList.Add(
                PO_DTj.tilde_D[time]
                <= (
                    PO_DTj.PowerLevel[time]
                    - PO_DTj.PowerLevel[prev_time]
                    - PO_DTj.Q_min * (1 - PO_DTj.ON_DOWN[prev_time])
                )
            )
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.tilde_D[time]
                    >= (
                        PO_DTj.PowerLevel[time]
                        - PO_DTj.PowerLevel[prev_time]
                        - PO_DTj.Q_max * (1 - PO_DTj.ON_DOWN[prev_time])
                    ),
                    "VALUE_of_tilde_DOWN_at_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # Second stage: U and D
            # These variables wil be added to the gradient constraints.
            # U (eq. (27))
            constraintList.Add(PO_DTj.U[time] <= PO_DTj.Q_max * PO_DTj.ON_UP[time])
            constraintList.Add(PO_DTj.U[time] >= PO_DTj.Q_min * PO_DTj.ON_UP[time])
            constraintList.Add(PO_DTj.U[time] <= PO_DTj.tilde_U[time] - PO_DTj.Q_min * (1 - PO_DTj.ON_UP[time]))
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.U[time] >= PO_DTj.tilde_U[time] - PO_DTj.Q_max * (1 - PO_DTj.ON_UP[time]),
                    "VALUE_of_UP_at_%s_for_%s" % (time_str, equipment_name),
                )
            )
            # D (eq. (29))
            constraintList.Add(PO_DTj.D[time] <= PO_DTj.Q_max * PO_DTj.ON_DOWN[time])
            constraintList.Add(PO_DTj.D[time] >= PO_DTj.Q_min * PO_DTj.ON_DOWN[time])
            constraintList.Add(PO_DTj.D[time] <= PO_DTj.tilde_D[time] - PO_DTj.Q_min * (1 - PO_DTj.ON_DOWN[time]))
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.D[time] >= PO_DTj.tilde_D[time] - PO_DTj.Q_max * (1 - PO_DTj.ON_DOWN[time]),
                    "VALUE_of_DOWN_at_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # C. CONSTRAINTS ON THE STATE VARIABLES

            # Mutual exclusion constraint
            # Defined over the whole time frame.
            # Enforces eq. (9)
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.OFF[time]
                    + PO_DTj.ON_UP[time]
                    + PO_DTj.ON_DOWN[time]
                    + PO_DTj.ON_FLAT[time]
                    + PO_DTj.START[time]
                    == 1,
                    "mutual_exclusion_at_%s_for_%s" % (time_str, equipment_name),
                )
            )
            if time == p.start_date:  # timeFrame_union_minus_one
                constraintList.Add(
                    API.Solver.NewOpConstraint(
                        PO_DTj.OFF[prev_time]
                        + PO_DTj.ON_UP[prev_time]
                        + PO_DTj.ON_DOWN[prev_time]
                        + PO_DTj.ON_FLAT[prev_time]
                        + PO_DTj.START[prev_time]
                        == 1,
                        "mutual_exclusion_at_%s_for_%s" % (get_date_to_clean_string(prev_time), equipment_name),
                    )
                )

            # Transitions:
            # UP-DOWN and DOWN-UP transitions are forbidden.
            # Implement eq. (25).
            constraintList.Add(PO_DTj.ON_UP[prev_time] + PO_DTj.ON_DOWN[time] <= 1)
            constraintList.Add(PO_DTj.ON_DOWN[prev_time] + PO_DTj.ON_UP[time] <= 1)
            if time == p.start_date:  # timeFrame_union_minus_one
                constraintList.Add(PO_DTj.ON_UP[time.AddMinutes(-2 * p.time_step)] + PO_DTj.ON_DOWN[prev_time] <= 1)
                constraintList.Add(PO_DTj.ON_DOWN[time.AddMinutes(-2 * p.time_step)] + PO_DTj.ON_UP[prev_time] <= 1)

            # Constraints involving START and OFF are only defined on the timeFrame time frame.
            # Eq. (10)
            constraintList.Add(PO_DTj.ON_UP[prev_time] + PO_DTj.START[time] <= 1)
            constraintList.Add(PO_DTj.ON_DOWN[prev_time] + PO_DTj.START[time] <= 1)
            constraintList.Add(PO_DTj.ON_FLAT[prev_time] + PO_DTj.START[time] <= 1)
            # Eq. (11)
            constraintList.Add(PO_DTj.START[prev_time] + PO_DTj.OFF[time] <= 1)
            # Eq. (15)
            constraintList.Add(PO_DTj.OFF[prev_time] + PO_DTj.ON_UP[time] <= 1)
            constraintList.Add(PO_DTj.OFF[prev_time] + PO_DTj.ON_DOWN[time] <= 1)
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.OFF[prev_time] + PO_DTj.ON_FLAT[time] <= 1,
                    "transitions_constraints_at_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # Eviction constraint
            # The unit must leave the START state after T_start time steps.
            # Implement equation (16)
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.turned_on[time.AddMinutes(-p.time_step * (PO_DTj.T_start - 1))] + PO_DTj.START[time] <= 1,
                    "eviction_constraint_at_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # Mininum time on and minimum time off constraints:
            # if T_on >= 2 or T_off >= 2 or T_stable >= 2, lock the unit in this state.
            if PO_DTj.T_on >= 2:
                timeSteps = range(1, PO_DTj.T_on)  # Corresponds to the set {1,..., T_on - 1}
                for s in timeSteps:
                    # Enforces eq. (31), with T_start >
                    local_time = time.AddMinutes(-(s + PO_DTj.T_start) * p.time_step)
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.turned_on[local_time]
                            <= (PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time] + PO_DTj.ON_FLAT[time]),
                            "minimum_time_ON_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )
                if time == p.start_date:
                    for s in timeSteps:
                        local_time = time.AddMinutes(-(s + PO_DTj.T_start + 1) * p.time_step)
                        constraintList.Add(
                            API.Solver.NewOpConstraint(
                                PO_DTj.turned_on[local_time]
                                <= (PO_DTj.ON_UP[prev_time] + PO_DTj.ON_DOWN[prev_time] + PO_DTj.ON_FLAT[prev_time]),
                                "minimum_time_ON_%s_at_%s_for_%s"
                                % (
                                    equipment_name,
                                    get_date_to_clean_string(local_time),
                                    get_date_to_clean_string(prev_time),
                                ),
                            )
                        )

            if PO_DTj.T_off >= 2:
                timeSteps = range(1, PO_DTj.T_off)  # Corresponds to the set {1,..., T_off - 1}
                for s in timeSteps:
                    local_time = time.AddMinutes(-s * p.time_step)
                    # Enforces eq. (32) with T_stop = 0
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.turned_off[local_time] <= PO_DTj.OFF[time],
                            "minimum_time_OFF_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )
            if PO_DTj.T_stable >= 2:
                timeSteps = range(1, PO_DTj.T_stable - 1)  # Corresponds to the set {1,..., T_stable - 2}
                for s in timeSteps:
                    local_time = time.AddMinutes(-s * p.time_step)
                    # Enforces eq. (26)
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.stable[local_time] <= PO_DTj.ON_FLAT[time],
                            "minimum_time_STABLE_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )
                if time == p.start_date:
                    for s in timeSteps:
                        local_time = time.AddMinutes(-(s + 1) * p.time_step)
                        constraintList.Add(
                            API.Solver.NewOpConstraint(
                                PO_DTj.stable[local_time] <= PO_DTj.ON_FLAT[prev_time],
                                "minimum_time_STABLE_%s_at_%s_for_%s"
                                % (equipment_name, get_date_to_clean_string(local_time), time_str),
                            )
                        )
            """
            if PO_DTj.T_start >= 2:
                for s in startTimeSteps:
                    local_time = time.AddMinutes(-s * p.time_step)
                    # Enforces eq. (17)
                    constraintList.Add(API.Solver.NewOpConstraint(PO_DTj.turned_on[time.AddMinutes(-s * p.time_step)] <= PO_DTj.START[time],
                                                                  'start_up_ramp_of_%s_at_%s_for_%s'%(equipment_name,
                                                                                                      get_date_to_clean_string(local_time),
                                                                                                      time_str)))
            """

            if PO_DTj.T_start >= 2:
                for s in startTimeSteps:
                    local_time = time.AddMinutes(-s * p.time_step)
                    # Enforces eq. (17)
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.turned_on[time.AddMinutes(-s * p.time_step)] <= PO_DTj.START[time],
                            "start_up_ramp_of_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )

            # C. CONSTRAINTS ON THE CONTROL VARIABLE

            # Shutdown gradient
            q_min = max(PO_DTj.MinimumPower.values())  # Get the minimumPower without the reserve requirements

            # q_step = q_min / (PO_DTj.T_start +1)
            q_step = q_min / (PO_DTj.T_start)

            # Reserves requirements
            # We are in a case where there is no FLAT state, so manual reserves can be provided
            # as long as the unit is online.

            # Constraints on contractedDifference (eq. (40))
            # and on automatedContractedDifference (eq. (39))

            # Upward and downward "fill up" constraints.
            constraintList.Add(
                PO_DTj.PowerLevel[time]
                + PO_DTj.reservesUp[time]
                + PO_DTj.automatedReservesUp[time]
                + PO_DTj.unprovidedReservesUp[time]
                <= PO_DTj.q_upper[time] + p.allowed_round_off_error
            )  # Upward constraint - eq. (41)

            constraintList.Add(
                PO_DTj.PowerLevel[time]
                + PO_DTj.reservesUp[time]
                + PO_DTj.automatedReservesUp[time]
                + PO_DTj.unprovidedReservesUp[time]
                >= PO_DTj.q_upper[time] - p.allowed_round_off_error
            )  # Upward constraint - eq. (41)

            constraintList.Add(
                PO_DTj.PowerLevel[time]
                - PO_DTj.reservesDown[time]
                - PO_DTj.automatedReservesDown[time]
                - PO_DTj.unprovidedReservesDown[time]
                + PO_DTj.relaxedReserves[time]
                <= PO_DTj.q_lower[time] + p.allowed_round_off_error
            )  # Downward constraint - eq. (42)

            constraintList.Add(
                PO_DTj.PowerLevel[time]
                - PO_DTj.reservesDown[time]
                - PO_DTj.automatedReservesDown[time]
                - PO_DTj.unprovidedReservesDown[time]
                + PO_DTj.relaxedReserves[time]
                >= PO_DTj.q_lower[time] - p.allowed_round_off_error
            )  # Downward constraint - eq. (42)

            # relaxedReserve disabling condition (eq. (43))
            constraintList.Add(
                PO_DTj.relaxedReserves[time]
                <= PO_DTj.q_lower[time] * (1 - PO_DTj.ON_UP[time] - PO_DTj.ON_FLAT[time] - PO_DTj.ON_DOWN[time])
            )

            # impossible commitment and stable reserves constraints (eq. (44))
            constraintList.Add(
                PO_DTj.automatedReservesUp[time]
                <= PO_DTj.maximumAutomated * (1 - PO_DTj.OFF[time] - PO_DTj.START[time])
            )
            constraintList.Add(
                PO_DTj.automatedReservesDown[time]
                <= PO_DTj.maximumAutomated * (1 - PO_DTj.OFF[time] - PO_DTj.START[time])
            )
            constraintList.Add(
                PO_DTj.reservesUp[time]
                <= PO_DTj.q_upper[time]
                * (1 - PO_DTj.ON_UP[time] - PO_DTj.ON_DOWN[time] - PO_DTj.OFF[time] - PO_DTj.START[time])
            )
            constraintList.Add(
                PO_DTj.reservesDown[time]
                <= PO_DTj.q_upper[time]
                * (1 - PO_DTj.ON_UP[time] - PO_DTj.ON_DOWN[time] - PO_DTj.OFF[time] - PO_DTj.START[time])
            )

            # Power output
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.PowerLevel[time]
                    >= (PO_DTj.q_lower[time] * (PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time] + PO_DTj.ON_FLAT[time])),
                    "lower_bound_of_%s_at_%s" % (equipment_name, time_str),
                )
            )  # Lower bound

            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.PowerLevel[time]
                    <= (
                        PO_DTj.q_upper[time] * (PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time] + PO_DTj.ON_FLAT[time])
                        + PO_DTj.START[time] * q_min
                    ),
                    "upper_bound_of_%s_at_%s" % (equipment_name, time_str),
                )
            )  # Upper bound

            # Power gradients
            # Definition of the gradientsTimeFrame: starts at startDate - p.time_stepime and goes until T-1
            # Gradients are defined on a "shifted" time frame.
            if time in optimes[: len(optimes) - 2]:
                if PO_DTj.Delta_Q > 0:  # Case where the gradient is finite.
                    # NB. The downward gradient implemented here requires the unit to be at most at deltaQ in order to be able to enter the stop state.
                    # The resulting constraint set is considerably more constraining than if the gradient was relaxed.

                    # Upward constrained gradient (eq. (33))
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            <= (
                                PO_DTj.Delta_Q * PO_DTj.entered_up[prev_time]
                                + PO_DTj.U[prev_time]
                                + PO_DTj.D[prev_time]
                                + q_step * PO_DTj.turned_on[time]
                                + PO_DTj.START[prev_time] * q_step
                            ),
                            "upward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Upward gradient

                    # Downward constrained gradient (eq. (35))
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            >= (
                                -PO_DTj.Delta_Q * PO_DTj.entered_down[prev_time]
                                + PO_DTj.U[prev_time]
                                + PO_DTj.D[prev_time]
                                - PO_DTj.Delta_Q_unconstrained * PO_DTj.turned_off[time]
                                + q_step * PO_DTj.turned_on[time]
                                + PO_DTj.START[prev_time] * q_step
                            ),
                            "downward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Downward gradient

                elif PO_DTj.Delta_Q == 0:  # Case where the gradient is 'infinite'
                    # Upward unconstrained gradient (eq. (34))
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            <= (
                                PO_DTj.Delta_Q_unconstrained * PO_DTj.entered_up[prev_time]
                                + PO_DTj.U[prev_time]
                                + PO_DTj.D[prev_time]
                                + q_step * PO_DTj.turned_on[time]
                                + PO_DTj.START[prev_time] * q_step
                            ),
                            "unconstrained_upward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Upward gradient

                    # Downward unconstrained gradient (eq. (36))
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            >= (
                                -PO_DTj.Delta_Q_unconstrained * PO_DTj.entered_down[prev_time]
                                + PO_DTj.U[prev_time]
                                + PO_DTj.D[prev_time]
                                - PO_DTj.Delta_Q_unconstrained * PO_DTj.turned_off[time]
                                + q_step * PO_DTj.turned_on[time]
                                + PO_DTj.START[prev_time] * q_step
                            ),
                            "unconstrained_downward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Downward gradient

                else:  # Raise an error since no gradients have been detected.
                    API.IO.Trace.Log(
                        "*** WARNING ***\n No gradients have been defined for equipment%s. \n "
                        "Please check the value of `MaximumGradient`." % equipment_name,
                        API.IO.LogTypeInfo,
                    )
                    raise ValueError("Missing gradients for thermic units.")

            # Energy limits
            if PO_DTj.hasDailyEnergyConstraint:
                days_in_optimes = []

                for op_time in optimes:
                    if DateTime(op_time.Year, op_time.Month, op_time.Day, 0, 0, 0) not in days_in_optimes:
                        days_in_optimes.append(DateTime(op_time.Year, op_time.Month, op_time.Day, 0, 0, 0))

                for date in days_in_optimes:
                    upper_bound = PO_DTj.maximumDailyEnergy.GetValue(date)

                    matching_steps = []
                    for local_op_time in optimes:
                        if (
                            (local_op_time.Year == date.Year)
                            and (local_op_time.Month == date.Month)
                            and (local_op_time.Day == date.Day)
                        ):
                            matching_steps.append(local_op_time)

                    if matching_steps:  # Add a constraint only if the list of filtered dates is not empty.
                        # Enforce eq. (37)
                        constraintList.Add(
                            API.Solver.NewOpConstraint(
                                sum([PO_DTj.PowerLevel[t] for t in matching_steps])
                                <= upper_bound * p.time_step / 1440 * len(matching_steps),
                                "energy_limit_of_%s_at_%s" % (str(equipment_name), time_str),
                            )
                        )
                        # p.time_stepime / 1440 * len(matching_steps) is a converting factor

        # -------------------------------------------------------------#
        #                                                             #
        ### Combination 7 : T_stop >= 1, T_stable = 0 T_start >= 1  ###
        #                                                             #
        # -------------------------------------------------------------#

        if PO_DTj.T_stop >= 1 and PO_DTj.T_start >= 1 and PO_DTj.T_stable == 0:
            # In this case, there are five state variables and four auxiliary variables.
            if p.debug and time == p.start_date:
                API.IO.Trace.Log(f"Equipment : {equipment_name}", API.IO.LogTypeInfo)
                API.IO.Trace.Log("Combination 7 for optimization constraints", API.IO.LogTypeInfo)
            # A. CONSTRAINTS ON THE AUXILIARY VARIABLES

            # These constraints define the auxiliary variables. In the first case, there are only two
            # of them: turned_on and turned_off.

            # Constraints on the indicator that the unit has started on t (turned_on, sec. 6.1.1)
            # Amounts to leaving the OFF state, due to the mutual exclusion and transition constraints.
            # Enforces eq (3).
            constraintList.Add(PO_DTj.turned_on[time] <= 1 - PO_DTj.OFF[time])
            constraintList.Add(PO_DTj.turned_on[time] <= PO_DTj.OFF[prev_time])
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.turned_on[time] >= PO_DTj.OFF[prev_time] - PO_DTj.OFF[time],
                    "constraints_defining_turned_on_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # Constraints on turned_off (sec. 6.1.2)
            # Defined here when entering the STOP state as in eq. (5) because T_stop > 0
            constraintList.Add(PO_DTj.turned_off[time] <= 1 - PO_DTj.STOP[prev_time])
            constraintList.Add(PO_DTj.turned_off[time] <= PO_DTj.STOP[time])
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.turned_off[time] >= PO_DTj.STOP[time] - PO_DTj.STOP[prev_time],
                    "constraints_defining_turned_off_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # Constraints on down_to_stop (eq. (20))
            constraintList.Add(PO_DTj.down_to_stop[time] <= PO_DTj.STOP[time])
            constraintList.Add(PO_DTj.down_to_stop[time] <= PO_DTj.ON_DOWN[prev_time])
            constraintList.Add(PO_DTj.down_to_stop[time] >= PO_DTj.STOP[time] + PO_DTj.ON_DOWN[prev_time] - 1)

            # B. CONSTRAINTS ON THE STATE VARIABLES

            # Mutual exclusion constraint
            # Enforces eq. (11)
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.OFF[time]
                    + PO_DTj.ON_UP[time]
                    + PO_DTj.ON_DOWN[time]
                    + PO_DTj.STOP[time]
                    + PO_DTj.START[time]
                    == 1,
                    "mutual_exclusion_at_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # Transitions:
            # Transitions from OFF to STOP and STOP to ON_DOWN and ON_UP are forbidden
            # Direct transitions from ON_UP and ON_DOWN to OFF are forbidden.
            # Transitions from ON_UP and ON_DOWN to START and START to OFF are forbidden
            # Direct transitions from OFF to ON_UP and ON_DOWN are forbidden.
            constraintList.Add(PO_DTj.STOP[prev_time] + PO_DTj.ON_UP[time] <= 1)  # Eq. (15)
            constraintList.Add(PO_DTj.STOP[prev_time] + PO_DTj.ON_DOWN[time] <= 1)  # Eq. (15)
            constraintList.Add(PO_DTj.OFF[prev_time] + PO_DTj.STOP[time] <= 1)  # Eq. (14)
            constraintList.Add(PO_DTj.ON_UP[prev_time] + PO_DTj.OFF[time] <= 1)  # Eq. (19)
            constraintList.Add(PO_DTj.ON_DOWN[prev_time] + PO_DTj.OFF[time] <= 1)  # Eq. (19)
            constraintList.Add(PO_DTj.ON_UP[prev_time] + PO_DTj.START[time] <= 1)  # Eq. (12)
            constraintList.Add(PO_DTj.ON_DOWN[prev_time] + PO_DTj.START[time] <= 1)  # Eq. (12)
            constraintList.Add(PO_DTj.START[prev_time] + PO_DTj.OFF[time] <= 1)  # Eq. (13)
            constraintList.Add(PO_DTj.START[prev_time] + PO_DTj.STOP[time] <= 1)  # Eq. (16)
            constraintList.Add(PO_DTj.STOP[prev_time] + PO_DTj.START[time] <= 1)  # Eq. (16)
            constraintList.Add(PO_DTj.OFF[prev_time] + PO_DTj.ON_UP[time] <= 1)  # Eq. (17)
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.OFF[prev_time] + PO_DTj.ON_DOWN[time] <= 1,
                    "transitions_constraints_at_%s_for_%s" % (time_str, equipment_name),
                )
            )  # Eq. (17)

            # Eviction constraints.
            # Implements equation (16)
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.turned_on[time.AddMinutes(-p.time_step * (PO_DTj.T_start - 1))] + PO_DTj.START[time] <= 1,
                    "START_eviction_constraint_at_%s_for_%s" % (time_str, equipment_name),
                )
            )
            # Implements equation (19)
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.turned_off[time.AddMinutes(-p.time_step * (PO_DTj.T_stop - 1))] + PO_DTj.STOP[time] <= 1,
                    "STOP_eviction_constraint_at_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # Mininum time on and minimum time off constraints:
            # if T_on >= 2, T_off >= 2 or T_stop >= 2, lock the unit in this state.
            if PO_DTj.T_on >= 2:
                timeSteps = range(1, PO_DTj.T_on)
                for s in timeSteps:
                    # Enforces eq. (27) with T_start > 0
                    local_time = time.AddMinutes(-(s + PO_DTj.T_start) * p.time_step)
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.turned_on[local_time] <= PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time],
                            "minimum_time_ON_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )
            if PO_DTj.T_off >= 2:
                timeSteps = range(1, PO_DTj.T_off)
                for s in timeSteps:
                    # Enforces eq. (28) with T_stop > 0
                    local_time = time.AddMinutes(
                        -(s + PO_DTj.T_stop) * p.time_step
                    )  # Shift the index because the OFF is formally considered when entering the STOP state.
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.turned_off[local_time] <= PO_DTj.OFF[time],
                            "minimum_time_OFF_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )
            if PO_DTj.T_stop >= 2:
                for s in stopTimeSteps:
                    # Enforces eq. (19)
                    local_time = time.AddMinutes(-s * p.time_step)
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.turned_off[local_time] <= PO_DTj.STOP[time],
                            "shutdown_ramp_of_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )
            if PO_DTj.T_start >= 2:
                for s in startTimeSteps:
                    # Enforces eq. (18)
                    local_time = time.AddMinutes(-s * p.time_step)
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.turned_on[local_time] <= PO_DTj.START[time],
                            "shutdown_ramp_of_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )

            # C. CONSTRAINTS ON THE CONTROL VARIABLE

            # Shutdown gradient
            q_min = max(PO_DTj.MinimumPower.values())  # Get the minimumPower without the reserve requirements

            # q_step_up = q_min / (PO_DTj.T_start + 1)
            q_step_up = q_min / (PO_DTj.T_start)

            # q_step_down = q_min / (PO_DTj.T_stop +1)
            q_step_down = q_min / (PO_DTj.T_stop)

            # Reserves requirements
            # We are in a case where there is no FLAT state, so manual reserves can be provided
            # as long as the unit is online.

            # Constraints on contractedDifference (eq. (40))
            # and on automatedContractedDifference (eq. (39))

            # Upward and downward "fill up" constraints.
            constraintList.Add(
                PO_DTj.PowerLevel[time]
                + PO_DTj.reservesUp[time]
                + PO_DTj.automatedReservesUp[time]
                + PO_DTj.unprovidedReservesUp[time]
                <= PO_DTj.q_upper[time] + p.allowed_round_off_error
            )  # Upward constraint - eq. (41)

            constraintList.Add(
                PO_DTj.PowerLevel[time]
                + PO_DTj.reservesUp[time]
                + PO_DTj.automatedReservesUp[time]
                + PO_DTj.unprovidedReservesUp[time]
                >= PO_DTj.q_upper[time] - p.allowed_round_off_error
            )  # Upward constraint - eq. (41)

            constraintList.Add(
                PO_DTj.PowerLevel[time]
                - PO_DTj.reservesDown[time]
                - PO_DTj.automatedReservesDown[time]
                - PO_DTj.unprovidedReservesDown[time]
                + PO_DTj.relaxedReserves[time]
                <= PO_DTj.q_lower[time] + p.allowed_round_off_error
            )  # Downward constraint - eq. (42)

            constraintList.Add(
                PO_DTj.PowerLevel[time]
                - PO_DTj.reservesDown[time]
                - PO_DTj.automatedReservesDown[time]
                - PO_DTj.unprovidedReservesDown[time]
                + PO_DTj.relaxedReserves[time]
                >= PO_DTj.q_lower[time] - p.allowed_round_off_error
            )  # Downward constraint - eq. (42)

            # relaxedReserve disabling condition (eq. (43))
            constraintList.Add(
                PO_DTj.relaxedReserves[time] <= PO_DTj.q_lower[time] * (1 - PO_DTj.ON_UP[time] - PO_DTj.ON_DOWN[time])
            )

            # impossible commitment and stable reserves constraints (eq. (44))
            constraintList.Add(
                PO_DTj.automatedReservesUp[time]
                <= PO_DTj.maximumAutomated * (1 - PO_DTj.OFF[time] - PO_DTj.START[time] - PO_DTj.STOP[time])
            )
            constraintList.Add(
                PO_DTj.automatedReservesDown[time]
                <= PO_DTj.maximumAutomated * (1 - PO_DTj.OFF[time] - PO_DTj.START[time] - PO_DTj.STOP[time])
            )
            constraintList.Add(
                PO_DTj.reservesUp[time]
                <= PO_DTj.q_upper[time] * (1 - PO_DTj.OFF[time] - PO_DTj.START[time] - PO_DTj.STOP[time])
            )
            constraintList.Add(
                PO_DTj.reservesDown[time]
                <= PO_DTj.q_upper[time] * (1 - PO_DTj.OFF[time] - PO_DTj.START[time] - PO_DTj.STOP[time])
            )

            # Power output
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.PowerLevel[time]
                    >= (
                        PO_DTj.q_lower[time] * (PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time])
                        + PO_DTj.turned_off[time] * (q_min - q_step_down)
                    ),
                    "lower_bound_of_%s_at_%s" % (equipment_name, time_str),
                )
            )  # Lower bound (eq. (29))

            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.PowerLevel[time]
                    <= (
                        PO_DTj.q_upper[time] * (PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time])
                        + PO_DTj.STOP[time] * q_min
                        + PO_DTj.START[time] * q_min
                        - PO_DTj.turned_off[time] * q_step_down
                    ),
                    "upper_bound_of_%s_at_%s" % (equipment_name, time_str),
                )
            )  # Upper bound (eq. (30))

            # Power gradients
            # Definition of the gradientsTimeFrame: starts at startDate - p.time_stepime and goes until T-1
            # Gradients are defined on a "shifted" time frame.
            if time in optimes[: len(optimes) - 2]:
                if PO_DTj.Delta_Q > 0:  # Case where the gradient is finite.
                    # NB. The downward gradient implemented here requires the unit to be at most at deltaQ in order to be able to enter the stop state.
                    # The resulting constraint set is considerably more constraining than if the gradient was relaxed.

                    # Upward constrained gradient (eq. (33))
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            <= (
                                PO_DTj.Delta_Q * PO_DTj.ON_UP[prev_time]
                                - PO_DTj.turned_off[time] * q_step_down
                                - PO_DTj.STOP[prev_time] * q_step_down
                                + PO_DTj.turned_on[time] * q_step_up
                                + PO_DTj.START[prev_time] * q_step_up
                            ),
                            "upward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Upward gradient

                    # Downward constrained gradient (eq. (35))
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            >= (
                                -PO_DTj.Delta_Q * PO_DTj.ON_DOWN[prev_time]
                                - PO_DTj.turned_off[time] * q_step_down
                                - PO_DTj.STOP[prev_time] * q_step_down
                                + PO_DTj.down_to_stop[time] * PO_DTj.Delta_Q
                                + PO_DTj.turned_on[time] * q_step_up
                                + PO_DTj.START[prev_time] * q_step_up
                            ),
                            "downward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Downward gradient

                elif PO_DTj.Delta_Q == 0:  # Case where the gradient is 'infinite'
                    # Upward unconstrained gradient (eq. (34))
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            <= (
                                PO_DTj.Delta_Q_unconstrained * PO_DTj.ON_UP[prev_time]
                                - PO_DTj.turned_off[time] * q_step_down
                                - PO_DTj.STOP[prev_time] * q_step_down
                                + PO_DTj.turned_on[time] * q_step_up
                                + PO_DTj.START[prev_time] * q_step_up
                            ),
                            "unconstrained_upward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Upward gradient

                    # Downward unconstrained gradient (eq. (36))
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            >= (
                                -PO_DTj.Delta_Q_unconstrained * PO_DTj.ON_DOWN[prev_time]
                                - PO_DTj.turned_off[time] * q_step_down
                                - PO_DTj.STOP[prev_time] * q_step_down
                                + PO_DTj.down_to_stop[time] * PO_DTj.Delta_Q_unconstrained
                                + PO_DTj.turned_on[time] * q_step_up
                                + PO_DTj.START[prev_time] * q_step_up
                            ),
                            "unconstrained_downward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Downward gradient
                else:  # Raise an error since no gradients have been detected.
                    API.IO.Trace.Log(
                        "*** WARNING ***\n No gradients have been defined for equipment%s. \n "
                        "Please check the value of `MaximumGradient`." % equipment_name,
                        API.IO.LogTypeInfo,
                    )
                    raise ValueError("Missing gradients for thermic units.")

            # Energy limits
            if PO_DTj.hasDailyEnergyConstraint:
                days_in_optimes = []

                for op_time in optimes:
                    if DateTime(op_time.Year, op_time.Month, op_time.Day, 0, 0, 0) not in days_in_optimes:
                        days_in_optimes.append(DateTime(op_time.Year, op_time.Month, op_time.Day, 0, 0, 0))

                for date in days_in_optimes:
                    upper_bound = PO_DTj.maximumDailyEnergy.GetValue(date)

                    matching_steps = []
                    for local_op_time in optimes:
                        if (
                            (local_op_time.Year == date.Year)
                            and (local_op_time.Month == date.Month)
                            and (local_op_time.Day == date.Day)
                        ):
                            matching_steps.append(local_op_time)

                    if matching_steps:  # Add a constraint only if the list of filtered dates is not empty.
                        # Enforce eq. (37)
                        constraintList.Add(
                            API.Solver.NewOpConstraint(
                                sum([PO_DTj.PowerLevel[t] for t in matching_steps])
                                <= upper_bound * p.time_step / 1440 * len(matching_steps),
                                "energy_limit_of_%s_at_%s" % (str(equipment_name), time_str),
                            )
                        )
                        # p.time_stepime / 1440 * len(matching_steps) is a converting factor

        # -------------------------------------------------------------#
        #                                                             #
        ####   Combination 8 : T_start = T_stable = T_stop >= 1    ####
        #                                                             #
        # -------------------------------------------------------------#

        if PO_DTj.T_stop >= 1 and PO_DTj.T_start >= 1 and PO_DTj.T_stable >= 1:
            if p.debug and time == p.start_date:
                API.IO.Trace.Log(f"Equipment : {equipment_name}", API.IO.LogTypeInfo)
                API.IO.Trace.Log("Combination 8 for optimization constraints", API.IO.LogTypeInfo)
            # In this case, there are six state variables and the following auxiliary variables:
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

            # B. CONSTRAINTS ON THE AUXILIARY VARIABLES

            # These constraints define the auxiliary variables. In the first case, there are only two
            # of them: turned_on and turned_off.

            # Constraints on the indicator that the unit has started on t
            # Enforces eq. (3)
            constraintList.Add(PO_DTj.turned_on[time] <= 1 - PO_DTj.OFF[time])
            constraintList.Add(PO_DTj.turned_on[time] <= PO_DTj.OFF[prev_time])
            constraintList.Add(PO_DTj.turned_on[time] >= PO_DTj.OFF[prev_time] - PO_DTj.OFF[time])

            # Constraints on turned_off
            # FC: according to the doc, either (4) or (5) should be implemented but not both
            # In that combination, it should be (5) since the STOP state is defined.
            # However, I don't understand what's happening after this correction. Weird results
            """
            # Enforces eq. (4)
            constraintList.Add(PO_DTj.turned_off[time] <= 1 - PO_DTj.OFF[prev_time])
            constraintList.Add(PO_DTj.turned_off[time] <= PO_DTj.OFF[time])
            constraintList.Add(PO_DTj.turned_off[time] >= PO_DTj.OFF[time] - PO_DTj.OFF[prev_time])
            """

            # Enforces eq. (5)
            constraintList.Add(PO_DTj.turned_off[time] <= 1 - PO_DTj.STOP[prev_time])
            constraintList.Add(PO_DTj.turned_off[time] <= PO_DTj.STOP[time])
            constraintList.Add(PO_DTj.turned_off[time] >= PO_DTj.STOP[time] - PO_DTj.STOP[prev_time])

            # stable auxiliary variable
            # Enforces eq. (6)
            constraintList.Add(PO_DTj.stable[time] <= 1 - PO_DTj.ON_FLAT[prev_time])
            constraintList.Add(PO_DTj.stable[time] <= PO_DTj.ON_FLAT[time])
            constraintList.Add(PO_DTj.stable[time] >= PO_DTj.ON_FLAT[time] - PO_DTj.ON_FLAT[prev_time])
            if time == p.start_date:  # time_frame_union_minus_one
                constraintList.Add(PO_DTj.stable[prev_time] <= 1 - PO_DTj.ON_FLAT[time.AddMinutes(-2 * p.time_step)])
                constraintList.Add(PO_DTj.stable[prev_time] <= PO_DTj.ON_FLAT[prev_time])
                constraintList.Add(
                    PO_DTj.stable[prev_time]
                    >= PO_DTj.ON_FLAT[prev_time] - PO_DTj.ON_FLAT[time.AddMinutes(-2 * p.time_step)]
                )

            # flat_down_stop auxiliary (eq. (22))
            constraintList.Add(PO_DTj.flat_down_stop[time] <= PO_DTj.STOP[time])
            constraintList.Add(PO_DTj.flat_down_stop[time] <= PO_DTj.ON_DOWN[prev_time])
            constraintList.Add(PO_DTj.flat_down_stop[time] <= PO_DTj.ON_FLAT[time.AddMinutes(-2 * p.time_step)])
            constraintList.Add(
                PO_DTj.flat_down_stop[time]
                >= PO_DTj.STOP[time] + PO_DTj.ON_DOWN[prev_time] + PO_DTj.ON_FLAT[time.AddMinutes(-2 * p.time_step)] - 2
            )

            # entered_up and entered_down auxiliaries (defined in sections 6.1.4 and 6.1.5)
            # entered_up (eq. (7))
            constraintList.Add(PO_DTj.entered_up[time] <= 1 - PO_DTj.ON_UP[prev_time])
            constraintList.Add(PO_DTj.entered_up[time] <= PO_DTj.ON_UP[time])
            constraintList.Add(PO_DTj.entered_up[time] >= PO_DTj.ON_UP[time] - PO_DTj.ON_UP[prev_time])

            # entered_down (eq. (8))
            constraintList.Add(PO_DTj.entered_down[time] <= 1 - PO_DTj.ON_DOWN[prev_time])
            constraintList.Add(PO_DTj.entered_down[time] <= PO_DTj.ON_DOWN[time])
            constraintList.Add(PO_DTj.entered_down[time] >= PO_DTj.ON_DOWN[time] - PO_DTj.ON_DOWN[prev_time])
            if time == p.start_date:  # time_frame_union_minus_one
                constraintList.Add(PO_DTj.entered_up[prev_time] <= 1 - PO_DTj.ON_UP[time.AddMinutes(-2 * p.time_step)])
                constraintList.Add(PO_DTj.entered_up[prev_time] <= PO_DTj.ON_UP[prev_time])
                constraintList.Add(
                    PO_DTj.entered_up[prev_time]
                    >= PO_DTj.ON_UP[prev_time] - PO_DTj.ON_UP[time.AddMinutes(-2 * p.time_step)]
                )
                constraintList.Add(
                    PO_DTj.entered_down[prev_time] <= 1 - PO_DTj.ON_DOWN[time.AddMinutes(-2 * p.time_step)]
                )
                constraintList.Add(PO_DTj.entered_down[prev_time] <= PO_DTj.ON_DOWN[prev_time])
                constraintList.Add(
                    PO_DTj.entered_down[prev_time]
                    >= PO_DTj.ON_DOWN[prev_time] - PO_DTj.ON_DOWN[time.AddMinutes(-2 * p.time_step)]
                )

            # UP and DOWN auxiliary variables for the gradient.
            # These auxiliary variables model the fact that if the unit is increasing (decreasing) its
            # power output twice in a row, then the second time the gradient is locked.
            # In practice, these variables are defined in two stages

            # First stage: tilde_U and tilde_D
            # tilde_U (eq. (28))
            constraintList.Add(PO_DTj.tilde_U[time] <= PO_DTj.Q_max * PO_DTj.ON_UP[prev_time])
            constraintList.Add(PO_DTj.tilde_U[time] >= PO_DTj.Q_min * PO_DTj.ON_UP[prev_time])
            constraintList.Add(
                PO_DTj.tilde_U[time]
                <= PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time] - PO_DTj.Q_min * (1 - PO_DTj.ON_UP[prev_time])
            )
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.tilde_U[time]
                    >= (
                        PO_DTj.PowerLevel[time]
                        - PO_DTj.PowerLevel[prev_time]
                        - PO_DTj.Q_max * (1 - PO_DTj.ON_UP[prev_time])
                    ),
                    "VALUE_of_tilde_UP_at_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # tilde_D (eq. (30))
            constraintList.Add(PO_DTj.tilde_D[time] <= PO_DTj.Q_max * PO_DTj.ON_DOWN[prev_time])
            constraintList.Add(PO_DTj.tilde_D[time] >= PO_DTj.Q_min * PO_DTj.ON_DOWN[prev_time])
            constraintList.Add(
                PO_DTj.tilde_D[time]
                <= PO_DTj.PowerLevel[time]
                - PO_DTj.PowerLevel[prev_time]
                - PO_DTj.Q_min * (1 - PO_DTj.ON_DOWN[prev_time])
            )
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.tilde_D[time]
                    >= (
                        PO_DTj.PowerLevel[time]
                        - PO_DTj.PowerLevel[prev_time]
                        - PO_DTj.Q_max * (1 - PO_DTj.ON_DOWN[prev_time])
                    ),
                    "VALUE_of_tilde_DOWN_at_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # Second stage: U and D
            # These variables wil be added to the gradient constraints.
            # U (eq. (27))
            constraintList.Add(PO_DTj.U[time] <= PO_DTj.Q_max * PO_DTj.ON_UP[time])
            constraintList.Add(PO_DTj.U[time] >= PO_DTj.Q_min * PO_DTj.ON_UP[time])
            constraintList.Add(PO_DTj.U[time] <= PO_DTj.tilde_U[time] - PO_DTj.Q_min * (1 - PO_DTj.ON_UP[time]))
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.U[time] >= PO_DTj.tilde_U[time] - PO_DTj.Q_max * (1 - PO_DTj.ON_UP[time]),
                    "VALUE_of_UP_at_%s_for_%s" % (time_str, equipment_name),
                )
            )
            # D (eq. (29))
            constraintList.Add(PO_DTj.D[time] <= PO_DTj.Q_max * PO_DTj.ON_DOWN[time])
            constraintList.Add(PO_DTj.D[time] >= PO_DTj.Q_min * PO_DTj.ON_DOWN[time])
            constraintList.Add(PO_DTj.D[time] <= PO_DTj.tilde_D[time] - PO_DTj.Q_min * (1 - PO_DTj.ON_DOWN[time]))
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.D[time] >= PO_DTj.tilde_D[time] - PO_DTj.Q_max * (1 - PO_DTj.ON_DOWN[time]),
                    "VALUE_of_DOWN_at_%s_for_%s" % (time_str, equipment_name),
                )
            )

            # DD Gradient auxiliary (eq. (23))PO_DTj
            if time in optimes[: len(optimes) - 2]:  # gradientsTimeFrame
                constraintList.Add(PO_DTj.DD[prev_time] <= PO_DTj.Q_max * PO_DTj.STOP[time])
                constraintList.Add(PO_DTj.DD[prev_time] >= PO_DTj.Q_min * PO_DTj.STOP[time])
                constraintList.Add(PO_DTj.DD[prev_time] <= PO_DTj.D[prev_time] - PO_DTj.Q_min * (1 - PO_DTj.STOP[time]))
                constraintList.Add(
                    API.Solver.NewOpConstraint(
                        PO_DTj.DD[prev_time] >= PO_DTj.D[prev_time] - PO_DTj.Q_max * (1 - PO_DTj.STOP[time]),
                        "DD_gradient_auxiliary_at_%s_for_%s" % (time_str, equipment_name),
                    )
                )

            # C. CONSTRAINTS ON THE STATE VARIABLES

            # Mutual exclusion constraint
            # Enforces eq. (9)
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.OFF[time]
                    + PO_DTj.ON_UP[time]
                    + PO_DTj.ON_DOWN[time]
                    + PO_DTj.ON_FLAT[time]
                    + PO_DTj.STOP[time]
                    + PO_DTj.START[time]
                    == 1,
                    "mutual_exclusion_at_%s_for_%s" % (time_str, equipment_name),
                )
            )
            if time == p.start_date:  # time_frame_union_minus_one
                constraintList.Add(
                    API.Solver.NewOpConstraint(
                        PO_DTj.OFF[prev_time]
                        + PO_DTj.ON_UP[prev_time]
                        + PO_DTj.ON_DOWN[prev_time]
                        + PO_DTj.ON_FLAT[prev_time]
                        + PO_DTj.STOP[prev_time]
                        + PO_DTj.START[prev_time]
                        == 1,
                        "mutual_exclusion_at_%s_for_%s" % (get_date_to_clean_string(prev_time), equipment_name),
                    )
                )

            # Transitions:
            # UP-DOWN and DOWN-UP transitions are forbidden.
            # STOP to ON transitions are also forbidden
            # OFF to STOP transitions
            # START to OFF
            # ON to START
            # START to STOP and STOP to START
            # OFF to ON
            # FC: Added ON to OFF
            # Finally, we forbid ON_UP to STOP (which never happens in practice) in order
            # to avoid defining a UU auxiliary analoguous to DD.
            # Implement eq. (25).
            constraintList.Add(PO_DTj.ON_UP[prev_time] + PO_DTj.ON_DOWN[time] <= 1)
            constraintList.Add(PO_DTj.ON_DOWN[prev_time] + PO_DTj.ON_UP[time] <= 1)
            # constraintList.Add(PO_DTj.ON_DOWN[prev_time] + PO_DTj.OFF[time] <= 1)

            # STOP to ON (eq. (13))
            constraintList.Add(PO_DTj.STOP[prev_time] + PO_DTj.ON_FLAT[time] <= 1)
            constraintList.Add(PO_DTj.STOP[prev_time] + PO_DTj.ON_DOWN[time] <= 1)
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.STOP[prev_time] + PO_DTj.ON_UP[time] <= 1,
                    "transitions_constraints_on_timeFrame_union_minus_one_at_%s_for_%s" % (time_str, equipment_name),
                )
            )
            if time == p.start_date:  # time_frame_union_minus_one
                constraintList.Add(PO_DTj.ON_UP[time.AddMinutes(-2 * p.time_step)] + PO_DTj.ON_DOWN[prev_time] <= 1)
                constraintList.Add(PO_DTj.ON_DOWN[time.AddMinutes(-2 * p.time_step)] + PO_DTj.ON_UP[prev_time] <= 1)

                # STOP to ON (eq. (13))
                constraintList.Add(PO_DTj.STOP[time.AddMinutes(-2 * p.time_step)] + PO_DTj.ON_FLAT[prev_time] <= 1)
                constraintList.Add(PO_DTj.STOP[time.AddMinutes(-2 * p.time_step)] + PO_DTj.ON_DOWN[prev_time] <= 1)
                constraintList.Add(
                    API.Solver.NewOpConstraint(
                        PO_DTj.STOP[time.AddMinutes(-2 * p.time_step)] + PO_DTj.ON_UP[prev_time] <= 1,
                        "transitions_constraints_on_timeFrame_union_minus_one_at_%s_for_%s"
                        % (get_date_to_clean_string(prev_time), equipment_name),
                    )
                )

                # ON to START (eq (10))
                constraintList.Add(PO_DTj.ON_UP[prev_time] + PO_DTj.START[time] <= 1)
                constraintList.Add(PO_DTj.ON_DOWN[prev_time] + PO_DTj.START[time] <= 1)
                constraintList.Add(PO_DTj.ON_FLAT[prev_time] + PO_DTj.START[time] <= 1)

                # ON to OFF
                constraintList.Add(PO_DTj.ON_UP[prev_time] + PO_DTj.OFF[time] <= 1)
                constraintList.Add(PO_DTj.ON_DOWN[prev_time] + PO_DTj.OFF[time] <= 1)
                constraintList.Add(PO_DTj.ON_FLAT[prev_time] + PO_DTj.OFF[time] <= 1)

            # ON_UP to STOP transition (eq. (21))
            constraintList.Add(PO_DTj.ON_UP[prev_time] + PO_DTj.STOP[time] <= 1)

            # OFF to STOP (eq. (12)).
            constraintList.Add(PO_DTj.OFF[prev_time] + PO_DTj.STOP[time] <= 1)

            # ON to START (eq. (10))
            constraintList.Add(PO_DTj.ON_UP[prev_time] + PO_DTj.START[time] <= 1)
            constraintList.Add(PO_DTj.ON_DOWN[prev_time] + PO_DTj.START[time] <= 1)
            constraintList.Add(PO_DTj.ON_FLAT[prev_time] + PO_DTj.START[time] <= 1)

            # ON to OFF
            constraintList.Add(PO_DTj.ON_UP[prev_time] + PO_DTj.OFF[time] <= 1)
            constraintList.Add(PO_DTj.ON_DOWN[prev_time] + PO_DTj.OFF[time] <= 1)
            constraintList.Add(PO_DTj.ON_FLAT[prev_time] + PO_DTj.OFF[time] <= 1)

            # START to OFF (eq. (11))
            constraintList.Add(PO_DTj.START[prev_time] + PO_DTj.OFF[time] <= 1)

            # START to STOP and STOP to START (eq. (14))
            constraintList.Add(PO_DTj.START[prev_time] + PO_DTj.STOP[time] <= 1)
            constraintList.Add(PO_DTj.STOP[prev_time] + PO_DTj.START[time] <= 1)
            # OFF to ON (eq. (15))
            constraintList.Add(PO_DTj.OFF[prev_time] + PO_DTj.ON_UP[time] <= 1)
            constraintList.Add(PO_DTj.OFF[prev_time] + PO_DTj.ON_FLAT[time] <= 1)
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.OFF[prev_time] + PO_DTj.ON_DOWN[time] <= 1,
                    "transitions_constraints_at_%s_for_%s" % (time_str, equipment_name),
                )
            )
            # The latter constraints are only defined on the timeFrame because it does not involve ON variables at the t index.

            # Eviction constraints
            # The unit must leave the STOP state after T_stop time steps.
            # and the START state after T_start time steps.
            # Implements equation (19)
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.turned_off[time.AddMinutes(-p.time_step * (PO_DTj.T_stop - 1))] + PO_DTj.STOP[time] <= 1,
                    "STOP_eviction_constraint_at_%s" % time_str,
                )
            )
            # Implements equation (16)
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.turned_on[time.AddMinutes(-p.time_step * (PO_DTj.T_start - 1))] + PO_DTj.START[time] <= 1,
                    "START_eviction_constraint_at_%s" % time_str,
                )
            )

            # Mininum time on and minimum time off constraints:
            # if T_on >= 2 or T_off >= 2 or T_stable >= 2, lock the unit in this state.
            if PO_DTj.T_on >= 2:
                timeSteps = range(1, PO_DTj.T_on)  # Corresponds to the set {1,..., T_on - 1}
                for s in timeSteps:
                    # Enforces eq. (31), with T_start > 0
                    local_time = time.AddMinutes(-(s + PO_DTj.T_start) * p.time_step)
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.turned_on[local_time]
                            <= (PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time] + PO_DTj.ON_FLAT[time]),
                            "minimum_time_ON_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )

                    if time == p.start_date:  # time_frame_union_minus_one
                        local_time = time.AddMinutes(-(s + PO_DTj.T_start + 1) * p.time_step)
                        constraintList.Add(
                            API.Solver.NewOpConstraint(
                                PO_DTj.turned_on[local_time]
                                <= (PO_DTj.ON_UP[prev_time] + PO_DTj.ON_DOWN[prev_time] + PO_DTj.ON_FLAT[prev_time]),
                                "minimum_time_ON_%s_at_%s_for_%s"
                                % (
                                    equipment_name,
                                    get_date_to_clean_string(local_time),
                                    get_date_to_clean_string(prev_time),
                                ),
                            )
                        )
            if PO_DTj.T_off >= 2:
                timeSteps = range(1, PO_DTj.T_off)  # Corresponds to the set {1,..., T_off - 1}
                for s in timeSteps:
                    # Enforces eq. (32) with T_stop > 0
                    local_time = time.AddMinutes(-(s + PO_DTj.T_stop) * p.time_step)
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.turned_off[local_time] <= PO_DTj.OFF[time],
                            "minimum_time_OFF_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )

            if PO_DTj.T_stable >= 2:
                timeSteps = range(1, PO_DTj.T_stable - 1)  # Corresponds to the set {1,..., T_stable - 2}
                for s in timeSteps:
                    # Enforces eq. (26)
                    local_time = time.AddMinutes(-s * p.time_step)
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.stable[local_time] <= PO_DTj.ON_FLAT[time],
                            "minimum_time_STABLE_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )
                    if time == p.start_date:  # time_frame_union_minus_one
                        local_time = time.AddMinutes(-(s + 1) * p.time_step)
                        constraintList.Add(
                            API.Solver.NewOpConstraint(
                                PO_DTj.stable[local_time] <= PO_DTj.ON_FLAT[prev_time],
                                "minimum_time_STABLE_%s_at_%s_for_%s"
                                % (
                                    equipment_name,
                                    get_date_to_clean_string(local_time),
                                    get_date_to_clean_string(prev_time),
                                ),
                            )
                        )

            if PO_DTj.T_stop >= 2:
                for s in stopTimeSteps:
                    # Enforces eq. (24)
                    local_time = time.AddMinutes(-s * p.time_step)
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.turned_off[local_time] <= PO_DTj.STOP[time],
                            "shutdown_ramp_of_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )

            if PO_DTj.T_start >= 2:
                for s in startTimeSteps:
                    # Enforces eq. (17)
                    local_time = time.AddMinutes(-s * p.time_step)
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.turned_on[local_time] <= PO_DTj.START[time],
                            "start_up_ramp_of_%s_at_%s_for_%s"
                            % (equipment_name, get_date_to_clean_string(local_time), time_str),
                        )
                    )

            # C. CONSTRAINTS ON THE CONTROL VARIABLE

            # Shutdown gradient
            q_min = max(PO_DTj.MinimumPower.values())  # Get the minimumPower without the reserve requirements

            # q_step_up = q_min / (PO_DTj.T_start + 1)
            q_step_up = q_min / (PO_DTj.T_start)

            # q_step_down = q_min / (PO_DTj.T_stop + 1)
            q_step_down = q_min / (PO_DTj.T_stop)

            # Reserves requirements
            # We are in a case where there is no FLAT state, so manual reserves can be provided
            # as long as the unit is online.

            # Constraints on contractedDifference (eq. (40))
            # and on automatedContractedDifference (eq. (39))

            # Upward and downward "fill up" constraints.
            constraintList.Add(
                PO_DTj.PowerLevel[time]
                + PO_DTj.reservesUp[time]
                + PO_DTj.automatedReservesUp[time]
                + PO_DTj.unprovidedReservesUp[time]
                <= PO_DTj.q_upper[time] + p.allowed_round_off_error
            )  # Upward constraint - eq. (41)

            constraintList.Add(
                PO_DTj.PowerLevel[time]
                + PO_DTj.reservesUp[time]
                + PO_DTj.automatedReservesUp[time]
                + PO_DTj.unprovidedReservesUp[time]
                >= PO_DTj.q_upper[time] - p.allowed_round_off_error
            )  # Upward constraint - eq. (41)

            constraintList.Add(
                PO_DTj.PowerLevel[time]
                - PO_DTj.reservesDown[time]
                - PO_DTj.automatedReservesDown[time]
                - PO_DTj.unprovidedReservesDown[time]
                + PO_DTj.relaxedReserves[time]
                <= PO_DTj.q_lower[time] + p.allowed_round_off_error
            )  # Downward constraint - eq. (42)

            constraintList.Add(
                PO_DTj.PowerLevel[time]
                - PO_DTj.reservesDown[time]
                - PO_DTj.automatedReservesDown[time]
                - PO_DTj.unprovidedReservesDown[time]
                + PO_DTj.relaxedReserves[time]
                >= PO_DTj.q_lower[time] - p.allowed_round_off_error
            )  # Downward constraint - eq. (42)

            # relaxedReserve disabling condition (eq. (43))
            constraintList.Add(
                PO_DTj.relaxedReserves[time]
                <= PO_DTj.q_lower[time] * (1 - PO_DTj.ON_UP[time] - PO_DTj.ON_FLAT[time] - PO_DTj.ON_DOWN[time])
            )

            # impossible commitment and stable reserves constraints (eq. (44))
            constraintList.Add(
                PO_DTj.automatedReservesUp[time]
                <= PO_DTj.maximumAutomated * (1 - PO_DTj.OFF[time] - PO_DTj.START[time] - PO_DTj.STOP[time])
            )
            constraintList.Add(
                PO_DTj.automatedReservesDown[time]
                <= PO_DTj.maximumAutomated * (1 - PO_DTj.OFF[time] - PO_DTj.START[time] - PO_DTj.STOP[time])
            )

            constraintList.Add(
                PO_DTj.reservesUp[time]
                <= PO_DTj.q_upper[time]
                * (
                    1
                    - PO_DTj.ON_UP[time]
                    - PO_DTj.ON_DOWN[time]
                    - PO_DTj.OFF[time]
                    - PO_DTj.START[time]
                    - PO_DTj.STOP[time]
                )
            )
            constraintList.Add(
                PO_DTj.reservesDown[time]
                <= PO_DTj.q_upper[time]
                * (
                    1
                    - PO_DTj.ON_UP[time]
                    - PO_DTj.ON_DOWN[time]
                    - PO_DTj.OFF[time]
                    - PO_DTj.START[time]
                    - PO_DTj.STOP[time]
                )
            )

            # Power output
            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.PowerLevel[time]
                    >= (
                        PO_DTj.q_lower[time] * (PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time] + PO_DTj.ON_FLAT[time])
                        + PO_DTj.turned_off[time] * (q_min - q_step_down)
                    ),
                    "lower_bound_of_%s_at_%s" % (equipment_name, time_str),
                )
            )  # Lower bound (eq. (29))

            constraintList.Add(
                API.Solver.NewOpConstraint(
                    PO_DTj.PowerLevel[time]
                    <= (
                        PO_DTj.q_upper[time] * (PO_DTj.ON_UP[time] + PO_DTj.ON_DOWN[time] + PO_DTj.ON_FLAT[time])
                        + (PO_DTj.STOP[time] + PO_DTj.START[time]) * q_min
                        - PO_DTj.turned_off[time] * q_step_down
                    ),
                    "upper_bound_of_%s_at_%s" % (equipment_name, time_str),
                )
            )  # Upper bound (eq. (30))

            # Power gradients
            # Definition of the gradientsTimeFrame: starts at startDate - p.time_stepime and goes until T-1
            # Gradients are defined on a "shifted" time frame
            if time in optimes[: len(optimes) - 2]:
                if PO_DTj.Delta_Q > 0:  # Case where the gradient is finite.
                    # NB. The downward gradient implemented here requires the unit to be at most at deltaQ in order to be able to enter the stop state.
                    # The resulting constraint set is considerably more constraining than if the gradient was relaxed.

                    # Upward constrained gradient (eq. (33))
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            <= (
                                PO_DTj.Delta_Q * PO_DTj.entered_up[prev_time]
                                + PO_DTj.U[prev_time]
                                + PO_DTj.D[prev_time]
                                - PO_DTj.turned_off[time] * q_step_down
                                - PO_DTj.STOP[prev_time] * q_step_down
                                + PO_DTj.turned_on[time] * q_step_up
                                + PO_DTj.START[prev_time] * q_step_up
                                - PO_DTj.DD[prev_time]
                            ),
                            "upward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Upward gradient

                    # Downward constrained gradient (eq. (35))
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            >= (
                                -PO_DTj.Delta_Q * PO_DTj.entered_down[prev_time]
                                + PO_DTj.U[prev_time]
                                + PO_DTj.D[prev_time]
                                - PO_DTj.turned_off[time] * q_step_down
                                - PO_DTj.STOP[prev_time] * q_step_down
                                + PO_DTj.flat_down_stop[time] * PO_DTj.Delta_Q
                                - PO_DTj.DD[prev_time]
                                + PO_DTj.turned_on[time] * q_step_up
                                + PO_DTj.START[prev_time] * q_step_up
                            ),
                            "downward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Downward gradient

                elif PO_DTj.Delta_Q == 0:  # Case where the gradient is 'infinite'
                    # Upward unconstrained gradient (eq. (34))
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            <= (
                                PO_DTj.Delta_Q_unconstrained * PO_DTj.entered_up[prev_time]
                                + PO_DTj.U[prev_time]
                                + PO_DTj.D[prev_time]
                                - PO_DTj.turned_off[time] * q_step_down
                                - PO_DTj.STOP[prev_time] * q_step_down
                                + PO_DTj.turned_on[time] * q_step_up
                                + PO_DTj.START[prev_time] * q_step_up
                                - PO_DTj.DD[prev_time]
                            ),
                            "unconstrained_upward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Upward gradient

                    # Downward unconstrained gradient (eq. (36))
                    constraintList.Add(
                        API.Solver.NewOpConstraint(
                            PO_DTj.PowerLevel[time] - PO_DTj.PowerLevel[prev_time]
                            >= (
                                -PO_DTj.Delta_Q_unconstrained * PO_DTj.entered_down[prev_time]
                                + PO_DTj.U[prev_time]
                                + PO_DTj.D[prev_time]
                                - PO_DTj.turned_off[time] * q_step_down
                                - PO_DTj.STOP[prev_time] * q_step_down
                                + PO_DTj.flat_down_stop[time] * PO_DTj.Delta_Q_unconstrained
                                - PO_DTj.DD[prev_time]
                                + PO_DTj.turned_on[time] * q_step_up
                                + PO_DTj.START[prev_time] * q_step_up
                            ),
                            "unconstrained_downward_gradient_of_%s_at_%s" % (equipment_name, time_str),
                        )
                    )  # Downward gradient

                else:  # Raise an error since no gradients have been detected.
                    API.IO.Trace.Log(
                        "*** WARNING ***\n No gradients have been defined for equipment%s. \n "
                        "Please check the value of `MaximumGradient`." % equipment_name,
                        API.IO.LogTypeInfo,
                    )
                    raise ValueError("Missing gradients for thermic units.")

            # Energy limits
            if PO_DTj.hasDailyEnergyConstraint:
                days_in_optimes = []

                for op_time in optimes:
                    if DateTime(op_time.Year, op_time.Month, op_time.Day, 0, 0, 0) not in days_in_optimes:
                        days_in_optimes.append(DateTime(op_time.Year, op_time.Month, op_time.Day, 0, 0, 0))

                for date in days_in_optimes:
                    upper_bound = PO_DTj.maximumDailyEnergy.GetValue(date)

                    matching_steps = []
                    for local_op_time in optimes:
                        if (
                            (local_op_time.Year == date.Year)
                            and (local_op_time.Month == date.Month)
                            and (local_op_time.Day == date.Day)
                        ):
                            matching_steps.append(local_op_time)

                    if matching_steps:  # Add a constraint only if the list of filtered dates is not empty.
                        # Enforce eq. (37)
                        constraintList.Add(
                            API.Solver.NewOpConstraint(
                                sum([PO_DTj.PowerLevel[t] for t in matching_steps])
                                <= upper_bound * p.time_step / 1440 * len(matching_steps),
                                "energy_limit_of_%s_at_%s" % (str(equipment_name), time_str),
                            )
                        )
                        # p.time_stepime / 1440 * len(matching_steps) is a converting factor
