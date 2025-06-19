import math

import API
from PO_functions import get_date_to_clean_string
from System import DateTime


class PO_Thermic:
    """
    This class is used to feed a PO_Thermic from a thermal equipment
    """

    def __init__(self, name, th_id):
        self.name = name
        self.id = "th_" + str(th_id)
        self.PowerLevel = {}
        self.Additionnal_power = {}
        self.Additionnal_power_below = {}

        # time constraintes
        self.minimumTimeOn = 0
        self.minimumTimeOff = 0
        self.minimumStablePowerDuration = 0
        self.startupDuration = 0
        self.shutdownDuration = 0

        self.T_on = 0
        self.T_off = 0
        self.T_start = 0
        self.T_stop = 0
        self.T_stable = 0
        self.T_traceback = 0

        # reserve requirements
        self.aFRRUpProcured = {}
        self.aFRRDownProcured = {}
        self.mFRRUpProcured = {}
        self.mFRRDownProcured = {}
        self.rRUpProcured = {}
        self.rRDownProcured = {}
        self.fCRUpProcured = {}
        self.fCRDownProcured = {}
        self.automatedUnsuppliedReserves = 0

        # technical features
        self.VariableCost = {}
        self.StartupCost = {}
        self.MinimumPower = {}
        self.MaximumPower = {}
        self.hasDailyEnergyConstraint = 0
        self.maximumDailyEnergy = 0
        self.maximumAFRR = 0
        self.maximumFCR = 0
        self.maximumAutomated = 0

        # modified max/min power
        self.q_lower = {}
        self.q_upper = {}

        # total reserve requirements
        self.rr_up = {}
        self.rr_down = {}

        # gradient
        self.Delta_Q = 0
        self.Delta_Q_unconstrained = 0
        self.Q_max = 0
        self.Q_min = 0

        # state variables
        self.OFF = {}
        self.ON_DOWN = {}
        self.ON_UP = {}
        self.STOP = {}
        self.ON_FLAT = {}
        self.START = {}

        # auxiliary variables
        self.turned_on = {}  # Corresponding to the variable defined in sec. 6.1.1
        self.turned_off = {}  # Corresponding to the variable defined in sec. 6.1.2
        self.stable = {}  # This auxiliary variable indicates when the unit enters the FLAT state
        self.entered_up = {}  # This variable replaces ON_UP in the definition of the gradient and
        # will bound the gradient for only one time step
        self.entered_down = {}  # Same as single_on_up but for on down
        self.down_to_stop = {}
        self.flat_down_stop = {}
        self.down_to_stop = {}

        # reserve variables
        self.reservesUp = {}
        self.reservesDown = {}
        self.unprovidedReservesUp = {}
        self.unprovidedReservesDown = {}
        self.relaxedReserves = {}
        self.automatedReservesUp = {}
        self.automatedReservesDown = {}

        # binding the gradient in stable cases
        self.U = {}
        self.tilde_U = {}
        self.D = {}
        self.tilde_D = {}
        self.DD = {}

    def fill_model(self, opt_thermic, p):
        # get data from optimate equipment
        self.minimumTimeOn = opt_thermic.MinimumTimeOn
        self.minimumTimeOff = opt_thermic.MinimumTimeOff
        self.minimumStablePowerDuration = opt_thermic.MinimumStablePowerDuration
        self.startupDuration = opt_thermic.StartupDuration
        self.shutdownDuration = opt_thermic.ShutdownDuration

        self.hasDailyEnergyConstraint = opt_thermic.HasDailyEnergyConstraint
        self.maximumDailyEnergy = opt_thermic.MaximumDailyEnergy  # peut etre mettre sous forme de doubleList?
        self.maximumAFRR = opt_thermic.MaximumAFRR
        self.maximumFCR = opt_thermic.MaximumFCR

        if p.debug:
            self.name = self.id

        # Check that the minimumStablePowerDuration is smaller than the minimumTimeOn

        if self.minimumStablePowerDuration > self.minimumTimeOn:
            # Warn the user
            API.IO.Trace.Log(
                f"""
                *** WARNING *** \n
                the MinimumStablePowerDuration of equipment {self.name} is greater than
                its MinimumTimeOn.\n
                MinimumStablePowerDuration has been modified and is now considered equal to MinimumTimeOn.
                """
            )
            self.minimumStablePowerDuration = self.minimumTimeOn

        # Conversion of the equipment-specific parameters in terms of time step.
        # All T_.'s are integers (by definition).
        # FC: Testing the extension of all "constant" periods (i.e. T_stable, T_on, T_off)
        # to take into account ramping
        if self.minimumTimeOn != 0:
            self.T_on = int(max(1, math.ceil(self.minimumTimeOn * 60.0 / p.time_step))) + 1
        else:
            self.T_on = 0

        if self.minimumTimeOff != 0:
            self.T_off = int(max(1, math.ceil(self.minimumTimeOff * 60.0 / p.time_step))) + 1
        else:
            self.T_off = 0

        self.T_start = int(math.floor(self.startupDuration * 60.0 / p.time_step))
        self.T_stop = int(math.floor(self.shutdownDuration * 60.0 / p.time_step))

        if self.minimumStablePowerDuration * 60.0 < p.time_step:
            self.T_stable = 0
        else:
            self.T_stable = int(math.ceil(self.minimumStablePowerDuration * 60.0 / p.time_step)) + 1

        # Rescale T_stable so that it is either equal to 0 or >= 2:
        self.T_stable = self.T_stable if self.T_stable >= 2 else 0

        # Creating the necessary time frames
        self.T_traceback = int(max(self.T_on + self.T_start, self.T_off + self.T_stop))

        initialCondTimeFame = []
        stableInitialCondTimeFame = []

        for k in range(self.T_traceback, 1, -1):
            stableInitialCondTimeFame.append(
                p.start_date.AddMinutes(-k * p.time_step)
            )  # Corresponds to [T_traceback; StartDate - 2]

        if self.T_traceback > 0:
            for k in range(self.T_traceback, 0, -1):
                initialCondTimeFame.append(
                    p.start_date.AddMinutes(-k * p.time_step)
                )  # Corresponds to [T_traceback; StartDate - 1]
        else:
            initialCondTimeFame.append(p.start_date.AddMinutes(-p.time_step))

        # Free Power Values TimeFrame:
        optimTimeFrame = API.DatetimeIndex.NewIndex(
            p.start_date, (p.thermal_optimization_period + self.T_traceback), p.time_step_str
        )  # Corresponds to [StartDate; EndDate + AddHours]

        # Free States TimeFrame:
        stableOptimTimeFrame = API.DatetimeIndex.NewIndex(
            p.start_date.AddMinutes(-p.time_step),
            (p.thermal_optimization_period + self.T_traceback),
            p.time_step_str,
        )  # Corresponds to [StartDate-1; EndDate + AddHours]

        # Exentend Time Frame:
        if self.T_traceback > 0:
            extendedTimeFrame = API.DatetimeIndex.NewIndex(
                p.start_date.AddMinutes(-self.T_traceback * p.time_step),
                optimTimeFrame[-1],
                p.time_step_str,
            )
        else:
            extendedTimeFrame = API.DatetimeIndex.NewIndex(
                p.start_date.AddMinutes(-p.time_step), optimTimeFrame[-1], p.time_step_str
            )
        extendedStartDate = extendedTimeFrame[0]

        startDate_minus_one = p.start_date.AddMinutes(-p.time_step)  # SD-1
        startDate_minus_two = p.start_date.AddMinutes(-2 * p.time_step)  # SD-2
        startDate_minus_three = p.start_date.AddMinutes(-3 * p.time_step)  # SD-3

        for time in extendedTimeFrame:
            self.MaximumPower[time] = opt_thermic.MaximumPower.GetValue(time)
            self.MinimumPower[time] = opt_thermic.MinimumPower.GetValue(time)
            self.q_lower[time] = opt_thermic.MinimumPower.GetValue(time)
            self.q_upper[time] = opt_thermic.MaximumPower.GetValue(time)
            self.aFRRUpProcured[time] = opt_thermic.AFRRUpProcured.GetForecast(p.execution_date, time, time).GetValue(
                time
            )
            self.aFRRDownProcured[time] = opt_thermic.AFRRDownProcured.GetForecast(
                p.execution_date, time, time
            ).GetValue(time)
            self.mFRRUpProcured[time] = opt_thermic.MFRRUpProcured.GetForecast(p.execution_date, time, time).GetValue(
                time
            )
            self.mFRRDownProcured[time] = opt_thermic.MFRRDownProcured.GetForecast(
                p.execution_date, time, time
            ).GetValue(time)
            self.rRUpProcured[time] = opt_thermic.RRUpProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            self.rRDownProcured[time] = opt_thermic.RRDownProcured.GetForecast(p.execution_date, time, time).GetValue(
                time
            )
            self.fCRUpProcured[time] = opt_thermic.FCRUpProcured.GetForecast(p.execution_date, time, time).GetValue(
                time
            )
            self.fCRDownProcured[time] = opt_thermic.FCRDownProcured.GetForecast(p.execution_date, time, time).GetValue(
                time
            )
            self.StartupCost[time] = opt_thermic.StartupCost.GetValue(time)
            self.VariableCost[time] = opt_thermic.VariableCost.GetValue(time)

            # Set-up the reserve requirements
            self.automatedUnsuppliedReserves += (
                max(self.aFRRUpProcured[time] - self.maximumAFRR, 0)
                + max(self.fCRUpProcured[time] - self.maximumFCR, 0)
                + max(self.aFRRDownProcured[time] - self.maximumAFRR, 0)
                + max(self.fCRDownProcured[time] - self.maximumFCR, 0)
            )

            self.maximumAutomated = self.maximumAFRR + self.maximumFCR

            # Set-up the power gradients
            self.Delta_Q = opt_thermic.MaximumGradient * p.time_step
            self.Delta_Q_unconstrained = max(self.MaximumPower.values())

            # Define dummy bounds for the gradient auxiliaries
            self.Q_max = max(self.MaximumPower.values())
            self.Q_min = -self.Q_max

        # 1:Creation of optim states variables:
        for time_enum, time in enumerate(optimTimeFrame):
            # Always defined Variables:
            self.OFF[time] = API.Solver.NewOpVariable(
                "OFF_var_e_%s_at_%s" % (self.name, str(time_enum)), API.Solver.OpCategoryBinary
            )
            self.ON_UP[time] = API.Solver.NewOpVariable(
                "ON_UP_var_e_%s_at_%s" % (self.name, str(time_enum)), API.Solver.OpCategoryBinary
            )
            self.ON_DOWN[time] = API.Solver.NewOpVariable(
                "ON_DOWN_var_e_%s_at_%s" % (self.name, str(time_enum)), API.Solver.OpCategoryBinary
            )

            self.turned_on[time] = API.Solver.NewOpVariable(
                "t_on_of_e_%s_at_%s" % (self.name, str(time_enum)), API.Solver.OpCategoryBinary
            )
            self.turned_off[time] = API.Solver.NewOpVariable(
                "t_off_of_e_%s_at_%s" % (self.name, str(time_enum)), API.Solver.OpCategoryBinary
            )

        # 'Conditional' state variables:defined only if a certain criteria on T is met.
        if self.T_start >= 1:
            for time_enum, time in enumerate(optimTimeFrame):
                self.START[time] = API.Solver.NewOpVariable(
                    "ON_START_e_%s_at_%s" % (self.name, str(time_enum)), API.Solver.OpCategoryBinary
                )

        if self.T_stop >= 1:
            for time_enum, time in enumerate(optimTimeFrame):
                self.STOP[time] = API.Solver.NewOpVariable(
                    "STOP_e_%s_at_%s" % (self.name, time_enum), API.Solver.OpCategoryBinary
                )

        if self.T_stable >= 1:
            for time_enum, time in enumerate(stableOptimTimeFrame):
                # Variables proper to T_STABLE >= 1:
                self.ON_FLAT[time] = API.Solver.NewOpVariable(
                    "ON_FLAT_e_%s_at_%s" % (self.name, str(time_enum)), API.Solver.OpCategoryBinary
                )
                self.stable[time] = API.Solver.NewOpVariable(
                    "stable_at_%s_e_%s" % (str(time_enum), self.name), API.Solver.OpCategoryBinary
                )
                self.entered_up[time] = API.Solver.NewOpVariable(
                    "entered_up_at_%s_e_%s" % (str(time_enum), self.name),
                    API.Solver.OpCategoryBinary,
                )
                self.entered_down[time] = API.Solver.NewOpVariable(
                    "entered_down_at_%s_e_%s" % (str(time_enum), self.name),
                    API.Solver.OpCategoryBinary,
                )
            # Extra optim TimeStep proper to T_STABLE >= 1:
            self.ON_UP[startDate_minus_one] = API.Solver.NewOpVariable(
                "ON_UP_var_e_%s_at_%s" % (self.name, get_date_to_clean_string(startDate_minus_one)),
                API.Solver.OpCategoryBinary,
            )
            self.ON_DOWN[startDate_minus_one] = API.Solver.NewOpVariable(
                "ON_DOWN_var_e_%s_at_%s" % (self.name, get_date_to_clean_string(startDate_minus_one)),
                API.Solver.OpCategoryBinary,
            )

            for time_enum, time in enumerate(optimTimeFrame):
                # Initialize the gradient auxiliaries.
                self.U[time] = API.Solver.NewOpVariable(
                    "UP_grad_at_%s_for_e_%s" % (str(time_enum), self.name), self.Q_min, self.Q_max
                )
                self.tilde_U[time] = API.Solver.NewOpVariable(
                    "aux_up_grad_at_%s_e_%s" % (str(time_enum), self.name), self.Q_min, self.Q_max
                )
                self.D[time] = API.Solver.NewOpVariable(
                    "DOWN_grad_at_%s_e_%s" % (str(time_enum), self.name), self.Q_min, self.Q_max
                )
                self.tilde_D[time] = API.Solver.NewOpVariable(
                    "aux_down_grad_at_%s_e_%s" % (str(time_enum), self.name), self.Q_min, self.Q_max
                )

        if self.T_stop >= 1 and self.T_start == 0 and self.T_stable == 0:
            for time_enum, time in enumerate(optimTimeFrame):
                self.down_to_stop[time] = API.Solver.NewOpVariable(
                    "down_to_stop_grad_at_%s_e_%s" % (str(time_enum), self.name),
                    API.Solver.OpCategoryBinary,
                )

        if self.T_stop >= 1 and self.T_stable >= 1:
            for time_enum, time in enumerate(optimTimeFrame):
                self.flat_down_stop[time] = API.Solver.NewOpVariable(
                    "flat_down_stop_at_%s_e_%s" % (str(time_enum), self.name),
                    API.Solver.OpCategoryBinary,
                )

        if self.T_stable >= 1 and (self.T_start >= 1 or self.T_stop >= 1):
            for time_enum, time in enumerate(optimTimeFrame):
                self.DD[time] = API.Solver.NewOpVariable(
                    "DD_grad_at_%s_e_%s" % (str(time_enum), self.name), self.Q_min, self.Q_max
                )

            # Add the time step before start_date
            self.DD[p.start_date.AddMinutes(-p.time_step)] = API.Solver.NewOpVariable(
                "DD_grad_at_%s_e_%s" % ("-1", self.name), self.Q_min, self.Q_max
            )

        if self.T_stop >= 1 and self.T_start >= 1 and self.T_stable == 0:
            for time_enum, time in enumerate(optimTimeFrame):
                self.down_to_stop[time] = API.Solver.NewOpVariable(
                    "down_to_stop_grad_at_%s_e_%s" % (str(time_enum), self.name),
                    API.Solver.OpCategoryBinary,
                )

        # 2:Creation of Power Optim Variables:
        for time_enum, time in enumerate(optimTimeFrame):
            # Create optimisation variables
            if time in p.thermal_op_times:
                # Power levels (only in thermal_op_timeframe)
                self.PowerLevel[time] = API.Solver.NewOpVariable(
                    f"{self.name}_p_lev_{str(time_enum)}",
                    0,
                    self.q_upper[time],
                    API.Solver.OpCategoryReal,
                )
                self.Additionnal_power[time] = API.Solver.NewOpVariable(
                    f"{self.name}_p_lev_above_maxAvail_{str(time_enum)}",
                    0,
                    self.q_upper[time],
                    API.Solver.OpCategoryReal,
                )
                self.Additionnal_power_below[time] = API.Solver.NewOpVariable(
                    f"{self.name}_p_lev_below_minAvail_{str(time_enum)}",
                    0,
                    self.q_upper[time],
                    API.Solver.OpCategoryReal,
                )

            else:
                # Initialize with a specific case for Base strategy
                if opt_thermic.Strategy == "Base":
                    if self.MaximumPower[time] >= self.MinimumPower[time]:
                        self.PowerLevel[time] = (
                            self.MinimumPower[time] + (self.MaximumPower[time] - self.MinimumPower[time]) / 2
                        )
                    else:
                        self.PowerLevel[time] = 0

                else:
                    self.PowerLevel[time] = opt_thermic.Power.GetForecast(p.execution_date, time, time).GetValue(time)

                self.Additionnal_power[time] = 0
                self.Additionnal_power_below[time] = 0

            # Optimisation Variables related tp,
            self.reservesUp[time] = API.Solver.NewOpVariable(
                "resUp_e_%s_at_%s" % (self.name, str(time_enum)),
                0,
                self.q_upper[time],
                API.Solver.OpCategoryReal,
            )

            self.reservesDown[time] = API.Solver.NewOpVariable(
                "resDown_e_%s_at_%s" % (self.name, str(time_enum)),
                0,
                self.q_upper[time],
                API.Solver.OpCategoryReal,
            )
            self.unprovidedReservesUp[time] = API.Solver.NewOpVariable(
                "unpResUp_e_%s_at_%s" % (self.name, str(time_enum)),
                0,
                self.q_upper[time],
                API.Solver.OpCategoryReal,
            )
            self.unprovidedReservesDown[time] = API.Solver.NewOpVariable(
                "unpResDown_e_%s_at_%s" % (self.name, str(time_enum)),
                0,
                self.q_upper[time],
                API.Solver.OpCategoryReal,
            )
            self.relaxedReserves[time] = API.Solver.NewOpVariable(
                "relRes_e_%s_at_%s" % (self.name, str(time_enum)),
                0,
                self.q_lower[time],
                API.Solver.OpCategoryReal,
            )
            self.automatedReservesUp[time] = API.Solver.NewOpVariable(
                "autoResUp_e_%s_at_%s" % (self.name, str(time_enum)),
                0,
                self.maximumAutomated,
                API.Solver.OpCategoryReal,
            )
            self.automatedReservesDown[time] = API.Solver.NewOpVariable(
                "autoResDown_e_%s_at_%s" % (self.name, str(time_enum)),
                0,
                self.maximumAutomated,
                API.Solver.OpCategoryReal,
            )

        # INTIAL CONDITIONS
        # Extraction of the Past power:
        lastPower = opt_thermic.Power.GetForecast(p.execution_date, initialCondTimeFame[0], initialCondTimeFame[-1])

        # Extraction of the last fixed power value (corresponding to SD-1):
        lastDate = lastPower.LastDate

        # See if the program needs to be initialized as DayZero or not
        if lastDate is None:
            # Initialization of the program as DayZero and warn the user
            API.IO.Trace.Log("***WARNING***\n The program is initialized for the first time.")

            dayZero = True  # Boolean to keep track of the status

        elif DateTime.Compare(lastDate, p.start_date.AddMinutes(-p.time_step)) != 0:
            # lastDate doesn't match startDate - DeltaT (i.e. t_{-1},
            # so we will initialize as DayZero and send a warning message
            API.IO.Trace.Log(
                "***WARNING***\n The lastDate found in Power of equipement %s "
                "does not match the startDate of the current program. \n "
                "The program will be initialized as DayZero." % self.name
            )
            dayZero = True

        else:
            dayZero = False

        # 3:Initialization of Past Power Variables:
        # 3.1:Initialize variables in the dayZero case
        if dayZero:
            for time in initialCondTimeFame:
                API.IO.Trace.Log(
                    "Initial conditions of unit %s have been set as follows:\n "
                    "for"
                    " all t in previousTimeFrame \n q_t = 0 \n OFF_t = 1, "
                    "ON_UP = ON_DOWN = 0 \n delta_start = delta_stop = 0" % self.name
                )

                # Initial conditions on the power output
                self.PowerLevel[time] = 0
                self.OFF[time] = 1

                self.turned_off[time] = 0
                self.turned_on[time] = 0

            if self.T_stop >= 1:
                for time in initialCondTimeFame:
                    self.STOP[time] = 0

                if self.T_stable >= 1:
                    for time in initialCondTimeFame:
                        self.flat_down_stop[time] = 0

                else:
                    for time in initialCondTimeFame:
                        self.down_to_stop[time] = 0

            if self.T_start >= 1:
                for time in initialCondTimeFame:
                    self.START[time] = 0

            if self.T_stable == 0:
                for time in initialCondTimeFame:
                    self.ON_UP[time] = 0
                    self.ON_DOWN[time] = 0

            else:
                for time in stableInitialCondTimeFame:
                    self.ON_FLAT[time] = 0
                    self.ON_UP[time] = 0
                    self.ON_DOWN[time] = 0

                    self.stable[time] = 0
                    self.entered_up[time] = 0
                    self.entered_down[time] = 0

                for time in initialCondTimeFame:
                    self.U[time] = 0
                    self.D[time] = 0
                    self.tilde_U[time] = 0
                    self.tilde_D[time] = 0

                    self.U[startDate_minus_one] = (
                        self.ON_UP[startDate_minus_one]
                        * self.ON_UP[startDate_minus_two]
                        * (self.PowerLevel[startDate_minus_one] - self.PowerLevel[startDate_minus_two])
                    )

                    self.D[startDate_minus_one] = (
                        self.ON_DOWN[startDate_minus_one]
                        * self.ON_DOWN[startDate_minus_two]
                        * (self.PowerLevel[startDate_minus_one] - self.PowerLevel[startDate_minus_two])
                    )

            API.IO.Trace.Log(
                "Initial conditions of unit %s have been set as follows:\n "
                "for"
                " all t in previousTimeFrame \n q_t = 0 \n OFF_t = 1, "
                " ON_UP = ON_DOWN = 0 \n delta_start = delta_stop = 0" % self.name
            )

        # 3.2:If not dayZero, initializes the power output as the past Program
        else:
            for time in initialCondTimeFame:
                self.PowerLevel[time] = lastPower.GetValue(time)

            # COMBINATION 1

            if self.T_stop == 0 and self.T_start == 0 and self.T_stable == 0:
                for time in initialCondTimeFame:
                    if lastPower.GetValue(time) > 0:
                        self.OFF[time] = 0
                        self.ON_DOWN[time] = 1
                        self.ON_UP[time] = 1

                    else:
                        self.OFF[time] = 1
                        self.ON_UP[time] = 0
                        self.ON_DOWN[time] = 0

                    # Initialize all the values to 0
                    self.turned_on[time] = 0
                    self.turned_off[time] = 0

                    if not time == extendedStartDate:
                        # Reconstruct potential switches using the state variables
                        # See if the unit has been turned off
                        if self.OFF[time] - self.OFF[time.AddMinutes(-p.time_step)] == 1:
                            self.turned_off[time] = 1

                        # Or turned on
                        elif self.OFF[time] - self.OFF[time.AddMinutes(-p.time_step)] == -1:
                            self.turned_on[time] = 1

                        else:
                            self.turned_on[time] = 0
                            self.turned_off[time] = 0

            # COMBINATION 2
            if self.T_stop >= 1 and self.T_start == 0 and self.T_stable == 0:
                for time in initialCondTimeFame:
                    if lastPower.GetValue(time) >= self.MinimumPower[time]:
                        self.OFF[time] = 0
                        self.STOP[time] = 0
                        self.ON_UP[time] = 1
                        self.ON_DOWN[time] = 1

                    elif lastPower.GetValue(time) > 0:
                        self.OFF[time] = 0
                        self.STOP[time] = 1
                        self.ON_UP[time] = 0
                        self.ON_DOWN[time] = 0

                    else:
                        self.OFF[time] = 1
                        self.STOP[time] = 0
                        self.ON_UP[time] = 0
                        self.ON_DOWN[time] = 0

                    # Initial conditions on the auxiliary variables
                    # Initialize all the values to 0
                    self.turned_on[time] = 0
                    self.turned_off[time] = 0
                    self.down_to_stop[time] = 0

                    # Reconstruction of the shutdown phase
                    if not time == extendedStartDate:
                        # Reconstruct potential switches using the state variables
                        if self.STOP[time] - self.STOP[time.AddMinutes(-p.time_step)] == 1:
                            self.turned_off[time] = 1

                        # Or turned on
                        elif self.OFF[time] - self.OFF[time.AddMinutes(-p.time_step)] == -1:
                            self.turned_on[time] = 1

                        elif self.STOP[time] - self.ON_DOWN[time.AddMinutes(-p.time_step)] == 0:
                            self.down_to_stop[time] = 1

            # COMBINATION 3
            if self.T_stop == 0 and self.T_start == 0 and self.T_stable >= 1:
                for time in initialCondTimeFame:
                    if lastPower.GetValue(time) > 0:
                        self.OFF[time] = 0

                    else:
                        self.OFF[time] = 1

                    # Initialize all the values to 0
                    self.turned_on[time] = 0
                    self.turned_off[time] = 0

                    if not time == extendedStartDate:
                        # Reconstruct potential switches using the state variables
                        # See if the unit has been turned off
                        if self.OFF[time] - self.OFF[time.AddMinutes(-p.time_step)] == 1:
                            self.turned_off[time] = 1

                        # Or turned on
                        elif self.OFF[time] - self.OFF[time.AddMinutes(-p.time_step)] == -1:
                            self.turned_on[time] = 1

                    else:
                        self.turned_on[time] = 0
                        self.turned_off[time] = 0

                for time in stableInitialCondTimeFame:
                    if self.OFF[time] == 0:
                        if self.PowerLevel[time] < self.PowerLevel[time.AddMinutes(p.time_step)]:
                            self.ON_UP[time] = 1
                            self.ON_DOWN[time] = 0
                            self.ON_FLAT[time] = 0

                        if self.PowerLevel[time] > self.PowerLevel[time.AddMinutes(p.time_step)]:
                            self.ON_UP[time] = 0
                            self.ON_DOWN[time] = 1
                            self.ON_FLAT[time] = 0

                        if self.PowerLevel[time] == self.PowerLevel[time.AddMinutes(p.time_step)]:
                            self.ON_UP[time] = 0
                            self.ON_DOWN[time] = 0
                            self.ON_FLAT[time] = 1

                    # Initialize the auxiliary variable
                    # Default value set to 0
                    self.stable[time] = 0
                    self.entered_up[time] = 0
                    self.entered_down[time] = 0

                    if not time == extendedStartDate:
                        # See which state the unit has entered
                        if self.ON_FLAT[time] - self.ON_FLAT[time.AddMinutes(-p.time_step)] == 1:
                            self.stable[time] = 1

                        if self.ON_UP[time] - self.ON_UP[time.AddMinutes(-p.time_step)] == 1:
                            self.entered_up[time] = 1

                        if self.ON_DOWN[time] - self.ON_DOWN[time.AddMinutes(-p.time_step)] == 1:
                            self.entered_down[time] = 1

                # Initialize the gradient auxiliaries. This is only required for the last time step of the
                # previousTimeFrame. Only ON_UP[startDate_minus_one] and ON_DOWN[startDate_minus_one] are decision variables
                # in the expressions below.
                self.U[startDate_minus_one] = (
                    self.ON_UP[startDate_minus_one]
                    * self.ON_UP[startDate_minus_two]
                    * (self.PowerLevel[startDate_minus_one] - self.PowerLevel[startDate_minus_two])
                )

                self.D[startDate_minus_one] = (
                    self.ON_DOWN[startDate_minus_one]
                    * self.ON_DOWN[startDate_minus_two]
                    * (self.PowerLevel[startDate_minus_one] - self.PowerLevel[startDate_minus_two])
                )

            # COMBINATION 4
            if self.T_start >= 1 and self.T_stop == 0 and self.T_stable == 0:
                for time in initialCondTimeFame:
                    if lastPower.GetValue(time) >= self.MinimumPower[time]:
                        self.OFF[time] = 0
                        self.START[time] = 0
                        self.ON_UP[time] = 1
                        self.ON_DOWN[time] = 1

                    elif lastPower.GetValue(time) > 0:
                        self.OFF[time] = 0
                        self.START[time] = 1
                        self.ON_UP[time] = 0
                        self.ON_DOWN[time] = 0

                    else:
                        self.OFF[time] = 1
                        self.START[time] = 0
                        self.ON_UP[time] = 0
                        self.ON_DOWN[time] = 0

                    # Initial conditions on the auxiliary variables
                    # Initialize all the values to 0
                    self.turned_on[time] = 0
                    self.turned_off[time] = 0

                    if not time == extendedStartDate:
                        if self.OFF[time] - self.OFF[time.AddMinutes(-p.time_step)] == 1:
                            self.turned_off[time] = 1

                        elif self.START[time] - self.START[time.AddMinutes(-p.time_step)] == 1:
                            self.turned_on[time] = 1

            # COMBINATION 5
            if self.T_stop >= 1 and self.T_start == 0 and self.T_stable >= 1:
                for time in initialCondTimeFame:
                    if lastPower.GetValue(time) >= self.MinimumPower[time]:
                        self.OFF[time] = 0
                        self.STOP[time] = 0

                    elif lastPower.GetValue(time) >= self.MinimumPower[time]:
                        self.OFF[time] = 0
                        self.STOP[time] = 1

                    else:
                        self.OFF[time] = 1
                        self.STOP[time] = 0

                    # Initial conditions on the auxiliary variables turned_on turned_off and flat_down_stop
                    # Initialize all the values to 0
                    self.turned_on[time] = 0
                    self.turned_off[time] = 0
                    self.flat_down_stop[time] = 0

                    if not time == extendedStartDate:
                        # Reconstruct potential switches using the state variables
                        # See if the unit has been turned off
                        if self.STOP[time] - self.STOP[time.AddMinutes(-p.time_step)] == 1:
                            self.turned_off[time] = 1

                        # Or turned on
                        elif self.OFF[time] - self.OFF[time.AddMinutes(-p.time_step)] == -1:
                            self.turned_on[time] = 1

                for time_enum, time in enumerate(stableInitialCondTimeFame):
                    if self.OFF[time] == 0:
                        # OFF = 0 and STOP = 1:
                        if self.STOP[time] == 1:
                            self.ON_UP[time] = 0
                            self.ON_DOWN[time] = 0
                            self.ON_FLAT[time] = 0

                        # OFF = 0 and STOP = 0:
                        else:
                            # See if the power output was stable, increasing or decreasing:
                            if self.PowerLevel[time] < self.PowerLevel[time.AddMinutes(p.time_step)]:
                                self.ON_UP[time] = 1
                                self.ON_DOWN[time] = 0
                                self.ON_FLAT[time] = 0

                            elif self.PowerLevel[time] > self.PowerLevel[time.AddMinutes(p.time_step)]:
                                self.ON_UP[time] = 0
                                self.ON_DOWN[time] = 1
                                self.ON_FLAT[time] = 0

                            elif self.PowerLevel[time] == self.PowerLevel[time.AddMinutes(p.time_step)]:
                                self.ON_UP[time] = 0
                                self.ON_DOWN[time] = 0
                                self.ON_FLAT[time] = 1
                    # OFF = 1
                    else:
                        self.ON_UP[time] = 0
                        self.ON_DOWN[time] = 0
                        self.ON_FLAT[time] = 0

                    # Initialize the auxiliary variables
                    # Default value set to 0
                    self.stable[time] = 0
                    self.entered_up[time] = 0
                    self.entered_down[time] = 0

                    if (not time == extendedStartDate) and (not self.OFF[time] == 1):
                        if self.ON_FLAT[time] - self.ON_FLAT[time.AddMinutes(-p.time_step)] == 1:
                            self.stable[time] = 1

                        if self.ON_UP[time] - self.ON_UP[time.AddMinutes(-p.time_step)] == 1:
                            self.entered_up[time] = 1

                        if self.ON_DOWN[time] - self.ON_DOWN[time.AddMinutes(-p.time_step)] == 1:
                            self.entered_down[time] = 1

                    # Initialize flat_down_stop.
                    if time_enum >= 2:
                        # Moreover, if we are after extendedStartDate + deltaTime
                        # initialize flat_down_stop (which traces back up to two time index before)
                        self.flat_down_stop[time] = int(
                            math.floor(
                                (
                                    self.STOP[time]
                                    + self.ON_DOWN[time.AddMinutes(-p.time_step)]
                                    + self.ON_FLAT[time.AddMinutes(-2 * p.time_step)]
                                )
                                / 3
                            )
                        )

                self.U[startDate_minus_one] = (
                    self.ON_UP[startDate_minus_one]
                    * self.ON_UP[startDate_minus_two]
                    * (self.PowerLevel[startDate_minus_one] - self.PowerLevel[startDate_minus_two])
                )

                self.D[startDate_minus_one] = (
                    self.ON_DOWN[startDate_minus_one]
                    * self.ON_DOWN[startDate_minus_two]
                    * (self.PowerLevel[startDate_minus_one] - self.PowerLevel[startDate_minus_two])
                )

                self.flat_down_stop[startDate_minus_one] = int(
                    math.floor(
                        (
                            self.STOP[startDate_minus_one]
                            + self.ON_DOWN[startDate_minus_two]
                            + self.ON_FLAT[startDate_minus_three]
                        )
                        / 3
                    )
                )

            # COMBINATION 6
            if self.T_stop == 0 and self.T_start >= 1 and self.T_stable >= 1:
                for time in initialCondTimeFame:
                    if lastPower.GetValue(time) >= self.MinimumPower[time]:
                        self.OFF[time] = 0
                        self.START[time] = 0

                    elif lastPower.GetValue(time) >= self.MinimumPower[time]:
                        self.OFF[time] = 0
                        self.START[time] = 1

                    else:
                        self.OFF[time] = 1
                        self.START[time] = 0

                    # Initial conditions on the auxiliary variables turned_on and turned_off.
                    # Initialize all the values to 0
                    self.turned_on[time] = 0
                    self.turned_off[time] = 0

                    if not time == extendedStartDate:
                        # Reconstruct potential switches using the state variables

                        # See if the unit has been turned off
                        if self.OFF[time] - self.OFF[time.AddMinutes(-p.time_step)] == 1:
                            self.turned_off[time] = 1

                        # Or turned on
                        elif self.START[time] - self.START[time.AddMinutes(-p.time_step)] == 1:
                            self.turned_on[time] = 1

                for time in stableInitialCondTimeFame:
                    if self.OFF[time] == 0:
                        # OFF = 0 and START = 1:
                        if self.START[time] == 1:
                            self.ON_UP[time] = 0
                            self.ON_DOWN[time] = 0
                            self.ON_FLAT[time] = 0

                        # OFF = 0 and START = 0:
                        else:
                            # See if the power output was stable, increasing or decreasing:
                            if self.PowerLevel[time] < self.PowerLevel[time.AddMinutes(p.time_step)]:
                                self.ON_UP[time] = 1
                                self.ON_DOWN[time] = 0
                                self.ON_FLAT[time] = 0

                            elif self.PowerLevel[time] > self.PowerLevel[time.AddMinutes(p.time_step)]:
                                self.ON_UP[time] = 0
                                self.ON_DOWN[time] = 1
                                self.ON_FLAT[time] = 0

                            elif self.PowerLevel[time] == self.PowerLevel[time.AddMinutes(p.time_step)]:
                                self.ON_UP[time] = 0
                                self.ON_DOWN[time] = 0
                                self.ON_FLAT[time] = 1
                    # OFF = 1
                    else:
                        self.ON_UP[time] = 0
                        self.ON_DOWN[time] = 0
                        self.ON_FLAT[time] = 0

                    # Initialize the auxiliary variables
                    # Default value set to 0
                    self.stable[time] = 0
                    self.entered_up[time] = 0
                    self.entered_down[time] = 0

                    if (not self.OFF[time] == 1) and (not time == extendedStartDate):
                        if self.ON_FLAT[time] - self.ON_FLAT[time.AddMinutes(-p.time_step)] == 1:
                            self.stable[time] = 1

                        if self.ON_UP[time] - self.ON_UP[time.AddMinutes(-p.time_step)] == 1:
                            self.entered_up[time] = 1

                        if self.ON_DOWN[time] - self.ON_DOWN[time.AddMinutes(-p.time_step)] == 1:
                            self.entered_down[time] = 1

                self.U[startDate_minus_one] = (
                    self.ON_UP[startDate_minus_one]
                    * self.ON_UP[startDate_minus_two]
                    * (self.PowerLevel[startDate_minus_one] - self.PowerLevel[startDate_minus_two])
                )

                self.D[startDate_minus_one] = (
                    self.ON_DOWN[startDate_minus_one]
                    * self.ON_DOWN[startDate_minus_two]
                    * (self.PowerLevel[startDate_minus_one] - self.PowerLevel[startDate_minus_two])
                )

            # COMBINATION 7
            if self.T_stop >= 1 and self.T_start >= 1 and self.T_stable == 0:
                # In this case, there are five state variables and four auxiliary variables.

                # Initial conditions on the state variables
                # Only need to set one value, the mutual exclusion constraint being defined over the
                # whole extended time frame.

                # There are now three cases:either q_t >= q_min, 0 < q_t < q_min or q_t = 0
                for time in initialCondTimeFame:
                    if lastPower.GetValue(time) >= self.MinimumPower[time]:
                        self.OFF[time] = 0
                        self.STOP[time] = 0
                        self.START[time] = 0
                        self.ON_DOWN[time] = 1
                        self.ON_UP[time] = (
                            1  # Set both ON states to 1 in order to allow the unit to do whatever it wants as there is no
                        )
                    # stable constraint at this point.
                    elif (
                        lastPower.GetValue(time) > 0
                    ):  # We will below see whether the unit was being turned on or turned off.
                        self.STOP[time] = 1
                        self.START[time] = 1
                        self.OFF[time] = 0
                        self.ON_UP[time] = 0
                        self.ON_DOWN[time] = 0
                    else:
                        self.STOP[time] = 0
                        self.START[time] = 0
                        self.OFF[time] = 1
                        self.ON_UP[time] = 0
                        self.ON_DOWN[time] = 0

                    # Distinguish between start-ups and shutdowns
                    # discard the extendedStartDate only.
                    if not time == extendedStartDate:
                        if self.START[time] == 1:  # Take start or stop, does not matter.
                            # If the power output increases, then we are starting up.
                            if self.PowerLevel[time] > self.PowerLevel[time.AddMinutes(-p.time_step)]:
                                self.STOP[time] = 0
                                self.START[time] = 1
                            # Otherwise we are shutting down the unit.
                            elif self.PowerLevel[time] < self.PowerLevel[time.AddMinutes(-p.time_step)]:
                                self.STOP[time] = 1
                                self.START[time] = 0

                    # Initial conditions on the auxiliary variables
                    # Initialize all the values to 0
                    self.turned_on[time] = 0
                    self.turned_off[time] = 0
                    self.down_to_stop[time] = 0

                    # Reconstruct potential switches using the state variables
                    # See if the unit has been turned off
                    if not time == extendedStartDate:
                        if self.STOP[time] - self.STOP[time.AddMinutes(-p.time_step)] == 1:
                            self.turned_off[time] = 1

                        # Or turned on
                        elif self.START[time] - self.START[time.AddMinutes(-p.time_step)] == 1:
                            self.turned_on[time] = 1

                        # Reconstruction of down_to_stop
                        elif self.STOP[time] - self.ON_DOWN[time.AddMinutes(-p.time_step)] == 0:
                            self.down_to_stop[time] = 1

            # COMBINATION 8
            if self.T_stop >= 1 and self.T_start >= 1 and self.T_stable >= 1:
                for time in initialCondTimeFame:
                    if lastPower.GetValue(time) >= self.MinimumPower[time]:
                        self.OFF[time] = 0
                        self.START[time] = 0
                        self.STOP[time] = 0

                    elif lastPower.GetValue(time) >= self.MinimumPower[time]:
                        self.OFF[time] = 0
                        self.START[time] = 1
                        self.STOP[time] = 1

                    else:
                        self.OFF[time] = 1
                        self.START[time] = 0
                        self.STOP[time] = 0

                    # Distinguish between start-ups and shutdowns
                    # discard the extendedStartDate only.

                    # Take start or stop, does not matter.
                    if (self.START[time] == 1) and (not time == extendedStartDate):
                        # If the power output increases, then we are starting up.
                        if self.PowerLevel[time] > self.PowerLevel[time.AddMinutes(-p.time_step)]:
                            self.STOP[time] = 0
                            self.START[time] = 1

                        # otherwise we are shutting down the unit.
                        elif self.PowerLevel[time] < self.PowerLevel[time.AddMinutes(-p.time_step)]:
                            self.STOP[time] = 1
                            self.START[time] = 0

                    # Initial conditions on the auxiliary variables turned_on turned_off

                    # Initialize all the values to 0
                    self.turned_on[time] = 0
                    self.turned_off[time] = 0

                    if not time == extendedStartDate:
                        # See if the unit has been turned off

                        if self.STOP[time] - self.STOP[time.AddMinutes(-p.time_step)] == 1:
                            self.turned_off[time] = 1

                        # Or turned on
                        elif self.START[time] - self.START[time.AddMinutes(-p.time_step)] == 1:
                            self.turned_on[time] = 1

                    # Reconstruct the values of UP, DOWN and FLAT and their associated
                    # auxiliary variables

                for time_enum, time in enumerate(stableInitialCondTimeFame):
                    # if ((self.OFF[time] == 0) and (self.START[time] == 0) and (self.STOP[time] == 0)):
                    if self.OFF[time] == 0:
                        # OFF = 0 and START = 1 and STOP = 1:
                        if (self.START[time] == 1) or (self.STOP[time] == 1):
                            self.ON_UP[time] = 0
                            self.ON_DOWN[time] = 0
                            self.ON_FLAT[time] = 0

                        # OFF = 0 and START = 0 and STOP = 0:
                        else:
                            # See if the power output was stable, increasing or decreasing:
                            if self.PowerLevel[time] < self.PowerLevel[time.AddMinutes(p.time_step)]:
                                self.ON_UP[time] = 1
                                self.ON_DOWN[time] = 0
                                self.ON_FLAT[time] = 0

                            elif self.PowerLevel[time] > self.PowerLevel[time.AddMinutes(p.time_step)]:
                                self.ON_UP[time] = 0
                                self.ON_DOWN[time] = 1
                                self.ON_FLAT[time] = 0

                            elif self.PowerLevel[time] == self.PowerLevel[time.AddMinutes(p.time_step)]:
                                self.ON_UP[time] = 0
                                self.ON_DOWN[time] = 0
                                self.ON_FLAT[time] = 1
                    # OFF = 1
                    else:
                        self.ON_UP[time] = 0
                        self.ON_DOWN[time] = 0
                        self.ON_FLAT[time] = 0

                    # Default value set to 0
                    self.stable[time] = 0
                    self.entered_up[time] = 0
                    self.entered_down[time] = 0

                    if (not time == extendedStartDate) and (not self.OFF[time] == 1):
                        # See if the unit entered the FLAT state
                        if self.ON_FLAT[time] - self.ON_FLAT[time.AddMinutes(-p.time_step)] == 1:
                            self.stable[time] = 1
                        # or the UP state
                        if self.ON_UP[time] - self.ON_UP[time.AddMinutes(-p.time_step)] == 1:
                            self.entered_up[time] = 1
                        # or the DOWN state
                        if self.ON_DOWN[time] - self.ON_DOWN[time.AddMinutes(-p.time_step)] == 1:
                            self.entered_down[time] = 1

                    # Initialize flat_down_stop.
                    if time_enum >= 2:
                        # Moreover, if we are after extendedStartDate + deltaTime
                        # initialize flat_down_stop (which traces back up to two time index before)

                        self.flat_down_stop[time] = int(
                            math.floor(
                                (
                                    self.STOP[time]
                                    + self.ON_DOWN[time.AddMinutes(-p.time_step)]
                                    + self.ON_FLAT[time.AddMinutes(-2 * p.time_step)]
                                )
                                / 3
                            )
                        )

                    # Initialize the gradient auxiliaries. This is only required for the last time step of the
                    # previousTimeFrame. Only ON_UP[startDate_minus_one] and ON_DOWN[startDate_minus_one] are decision variables
                    # in the expressions below

                self.U[startDate_minus_one] = (
                    self.ON_UP[startDate_minus_one]
                    * self.ON_UP[startDate_minus_two]
                    * (self.PowerLevel[startDate_minus_one] - self.PowerLevel[startDate_minus_two])
                )

                self.D[startDate_minus_one] = (
                    self.ON_DOWN[startDate_minus_one]
                    * self.ON_DOWN[startDate_minus_two]
                    * (self.PowerLevel[startDate_minus_one] - self.PowerLevel[startDate_minus_two])
                )

                self.flat_down_stop[startDate_minus_one] = int(
                    math.floor(
                        (
                            self.STOP[startDate_minus_one]
                            + self.ON_DOWN[startDate_minus_two]
                            + self.ON_FLAT[startDate_minus_three]
                        )
                        / 3
                    )
                )
