import API
from PO_functions import get_time_series_value


class PO_Load:
    """
    This class is used to feed a PO_Load from a dispatchable load equipment
    """

    def __init__(self, name):
        # Variables
        self.name = name
        self.PowerLevel = {}
        self.Price = {}

        # Reserve requirements, disallowed for load units for now (left empty)
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

        # Others
        self.LoadType = 0

    def init_variables(self, opt_Load, p):
        self.maximumAFRR = opt_Load.MaximumAFRR
        self.maximumFCR = opt_Load.MaximumFCR
        self.LoadType = opt_Load.LoadType

        # get global matrix power
        t0MinusDeltaT = API.DatetimeIndex.Shift(p.target_times, "-" + p.time_step_str)[0]
        power = opt_Load.Power.GetForecast(p.execution_date, t0MinusDeltaT, p.start_date)
        if power is None:
            power = opt_Load.FinalProg

        # The following power level should be from last forecast of Power matrix, it is final prog for test
        # self.power_level_prev =  get_time_series_value(power, t0MinusDeltaT)

        for time_index, time in enumerate(p.target_times):
            # Get min and max power
            # By convention, min_power is set to 0 for dispatchable load
            max_power = get_time_series_value(
                opt_Load.MaximumPowerForecast.GetForecast(p.execution_date, time, time), time
            )
            min_power = 0

            # Get variable cost
            price = get_time_series_value(opt_Load.VariableCost, time)

            # Get procured reserves
            afrrup = opt_Load.AFRRUpProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            afrrdown = opt_Load.AFRRDownProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            mfrrup = opt_Load.MFRRUpProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            mfrrdown = opt_Load.MFRRDownProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            rrup = opt_Load.RRUpProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            rrdown = opt_Load.RRDownProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            fcrup = opt_Load.FCRUpProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            fcrdown = opt_Load.FCRDownProcured.GetForecast(p.execution_date, time, time).GetValue(time)

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
                f"{self.name}_Power_level_{time_index}",
                max_power,
                min_power,
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

            # Optimisation Variables related to reserves, not created for load equipments
            """
            self.reservesUp.Add(API.Solver.NewOpVariable('resUp_e_%s_at_%s' %(self.name, str(i)), 0, max_power, API.Solver.OpCategoryReal))
            self.reservesDown.Add(API.Solver.NewOpVariable('resDown_e_%s_at_%s' %(self.name, str(i)), min_power, max_power, API.Solver.OpCategoryReal))
            self.unprovidedReservesUp.Add(API.Solver.NewOpVariable('unpResUp_e_%s_at_%s' %(self.name, str(i)), 0, max_power, API.Solver.OpCategoryReal))
            self.unprovidedReservesDown.Add(API.Solver.NewOpVariable('unpResDown_e_%s_at_%s' %(self.name, str(i)), min_power, max_power, API.Solver.OpCategoryReal))
            #self.relaxedReserves.Add(API.Solver.NewOpVariable('relaxedReserves_control_variable_of_equipment_%s_at_%s' %(self.name, str(i)), min_power,0, API.Solver.OpCategoryReal))
            self.automatedReservesUp.Add(API.Solver.NewOpVariable('autoResUp_e_%s_at_%s' %(self.name, str(i)), 0, self.maximumAutomated, API.Solver.OpCategoryReal))
            self.automatedReservesDown.Add(API.Solver.NewOpVariable('autoResDown_e_%s_at_%s' %(self.name, str(i)), 0, self.maximumAutomated, API.Solver.OpCategoryReal))
            self.contractedDifferenceUp.Add(API.Solver.NewOpVariable('contractedDiffUp_e_%s_at_%s' %(self.name, str(i)), 0, max_power, API.Solver.OpCategoryReal))
            self.contractedDifferenceDown.Add(API.Solver.NewOpVariable('contractedDiffDown_e_%s_at_%s' %(self.name, str(i)), min_power, max_power, API.Solver.OpCategoryReal))
            self.automatedContractedDifferenceUp.Add(API.Solver.NewOpVariable('autoContractedDiffUp_e_%s_at_%s' %(self.name, str(i)), 0, max_power, API.Solver.OpCategoryReal))
            self.automatedContractedDifferenceDown.Add(API.Solver.NewOpVariable('autoContractedDiffDown_e_%s_at_%s' %(self.name, str(i)), min_power, max_power, API.Solver.OpCategoryReal))
            """
