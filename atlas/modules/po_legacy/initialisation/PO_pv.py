# coding: utf-8

from PO_functions import get_time_series_value
import API


class PO_PV(object):
    """
    This class is used to feed a PO_PV from a photovoltaic equipment
    """

    def __init__(self, name):
        # variables
        self.name = name
        self.PowerLevel = {}
        self.Price = {}

        # reserve requirements
        self.AFRRUpProcured = {}
        self.AFRRDownProcured = {}
        self.MFRRUpProcured = {}
        self.MFRRDownProcured = {}
        self.RRUpProcured = {}
        self.RRDownProcured = {}
        self.FCRUpProcured = {}
        self.FCRDownProcured = {}
        self.reservesUpProcured = {}
        self.reservesDownProcured = {}

        self.feasibleAutomatedReservesUpProcured = {}
        self.feasibleAutomatedReservesDownProcured = {}
        self.automatedUnsuppliedReserves = 0

        # reserve variables
        self.reservesUp = {}
        self.reservesDown = {}
        self.unprovidedReservesUp = {}
        self.unprovidedReservesDown = {}
        self.relaxedReserves = {}
        self.automatedReservesUp = {}
        self.automatedReservesDown = {}
        self.contractedDifferenceUp = {}
        self.contractedDifferenceDown = {}
        self.automatedContractedDifferenceUp = {}
        self.automatedContractedDifferenceDown = {}

        self.maximumAFRR = 0
        self.maximumFCR = 0
        self.maximumAutomated = 0

        self.MaximumPower = {}
        self.MinimumPower = {}

    def init_variables(self, opt_PV, p):
        self.maximumAFRR = opt_PV.MaximumAFRR
        self.maximumFCR = opt_PV.MaximumFCR

        # get global matrix power
        t0MinusDeltaT = API.DatetimeIndex.Shift(p.target_times, "-" + p.time_step_str)[0]
        power = opt_PV.Power.GetForecast(p.execution_date, t0MinusDeltaT, p.start_date)
        if power is None:
            power = opt_PV.FinalProg

        # The following power level should be from last forecast of Power matrix, it is final prog for test
        # self.power_level_prev =  get_time_series_value(power, t0MinusDeltaT)

        for time_enum, time in enumerate(p.target_times):
            # Get min and max power
            max_power = get_time_series_value(
                opt_PV.MaximumPowerForecast.GetForecast(p.execution_date, time, time), time
            )
            min_power = (1 - get_time_series_value(opt_PV.MaximumCurtailmentRatio, time)) * max_power

            # Get variable cost
            price = get_time_series_value(opt_PV.VariableCost, time)

            # Get procured reserves
            afrrup = opt_PV.AFRRUpProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            afrrdown = opt_PV.AFRRDownProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            mfrrup = opt_PV.MFRRUpProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            mfrrdown = opt_PV.MFRRDownProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            rrup = opt_PV.RRUpProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            rrdown = opt_PV.RRDownProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            fcrup = opt_PV.FCRUpProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            fcrdown = opt_PV.FCRDownProcured.GetForecast(p.execution_date, time, time).GetValue(time)

            self.MaximumPower[time] = max_power
            self.MinimumPower[time] = min_power
            self.Price[time] = price

            self.AFRRUpProcured[time] = afrrup
            self.AFRRDownProcured[time] = afrrdown
            self.MFRRUpProcured[time] = mfrrup
            self.MFRRDownProcured[time] = mfrrdown
            self.RRUpProcured[time] = rrup
            self.RRDownProcured[time] = rrdown
            self.FCRUpProcured[time] = fcrup
            self.FCRDownProcured[time] = fcrdown

            # init variables
            # create optimisation variables
            self.PowerLevel[time] = API.Solver.NewOpVariable(
                "{name}_Power_level_{val}".format(name=self.name, val=time_enum),
                0,
                max_power,
                API.Solver.OpCategoryReal,
            )

            # Set-up the reserve requirements
            self.reservesUpProcured[time] = rrup + mfrrup
            self.reservesDownProcured[time] = rrdown + mfrrdown
            self.maximumAutomated = self.maximumAFRR + self.maximumFCR

            self.feasibleAutomatedReservesUpProcured[time] = min(afrrup, self.maximumAFRR) + min(fcrup, self.maximumFCR)
            self.feasibleAutomatedReservesDownProcured[time] = min(afrrdown, self.maximumAFRR) + min(
                fcrdown, self.maximumFCR
            )
            self.automatedUnsuppliedReserves += (
                max(afrrup - self.maximumAFRR, 0)
                + max(fcrup - self.maximumFCR, 0)
                + max(afrrdown - self.maximumAFRR, 0)
                + max(fcrdown - self.maximumFCR, 0)
            )

            # Optimisation Variables related tp,
            self.reservesUp[time] = API.Solver.NewOpVariable(
                "resUp_e_%s_at_%s" % (self.name, str(time_enum)), 0, max_power, API.Solver.OpCategoryReal
            )
            self.reservesDown[time] = API.Solver.NewOpVariable(
                "resDown_e_%s_at_%s" % (self.name, str(time_enum)), min_power, max_power, API.Solver.OpCategoryReal
            )
            self.unprovidedReservesUp[time] = API.Solver.NewOpVariable(
                "unpResUp_e_%s_at_%s" % (self.name, str(time_enum)), 0, max_power, API.Solver.OpCategoryReal
            )
            self.unprovidedReservesDown[time] = API.Solver.NewOpVariable(
                "unpResDown_e_%s_at_%s" % (self.name, str(time_enum)), min_power, max_power, API.Solver.OpCategoryReal
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
            self.contractedDifferenceUp[time] = API.Solver.NewOpVariable(
                "contractedDiffUp_e_%s_at_%s" % (self.name, str(time_enum)), 0, max_power, API.Solver.OpCategoryReal
            )
            self.contractedDifferenceDown[time] = API.Solver.NewOpVariable(
                "contractedDiffDown_e_%s_at_%s" % (self.name, str(time_enum)),
                min_power,
                max_power,
                API.Solver.OpCategoryReal,
            )
            self.automatedContractedDifferenceUp[time] = API.Solver.NewOpVariable(
                "autoContractedDiffUp_e_%s_at_%s" % (self.name, str(time_enum)), 0, max_power, API.Solver.OpCategoryReal
            )
            self.automatedContractedDifferenceDown[time] = API.Solver.NewOpVariable(
                "autoContractedDiffDown_e_%s_at_%s" % (self.name, str(time_enum)),
                min_power,
                max_power,
                API.Solver.OpCategoryReal,
            )
