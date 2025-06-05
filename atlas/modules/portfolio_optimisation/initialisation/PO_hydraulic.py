import API
from PO_functions import get_time_series_value


class PO_Hydraulic:
    """
    This class is used to feed a PO_Hydraulic from a hydraulic equipment
    """

    def __init__(self, opt_hydrau, name, p):
        # variables
        self.name = name
        self.PowerLevel = {}
        self.StoredEnergy = {}
        self.PowerLevelFragmentSum = {}

        # For each power fragment
        self.PowerLevelFragment = {}
        self.PriceFragment = {}

        for n in range(0, len(opt_hydrau.FragmentVolumes)):
            self.PowerLevelFragment[n] = {}
            self.PriceFragment[n] = {}

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

        # Parameters
        self.MaximumPower = {}
        self.MinimumPower = {}
        self.InitialLevel = 0
        self.MaximumEnergy = {}
        self.MinimumEnergy = {}
        self.StoredEnergyMatrix = 0
        self.StorageMarginalValue = 0
        self.power_level_prev = 0

        # Others
        self.MaximumPowerSum = 0

    def init_variables(self, opt_hydrau, p):
        # Get Initial reservoir level
        self.StorageMarginalValue = opt_hydrau.StorageMarginalValue
        # get data from optimate equipment
        self.maximumAFRR = opt_hydrau.MaximumAFRR
        self.maximumFCR = opt_hydrau.MaximumFCR

        self.StoredEnergyMatrix = opt_hydrau.StoredEnergy
        if (
            self.StoredEnergyMatrix.GetForecast(
                p.execution_date, p.start_date.AddMinutes(-p.time_step), p.end_date
            ).Length
            == 0
        ):
            self.InitialLevel = opt_hydrau.InitialLevel.Slice(p.start_date.AddMinutes(-p.time_step), p.end_date)
        else:
            if (
                self.StoredEnergyMatrix.GetForecast(
                    p.execution_date, p.start_date.AddMinutes(-p.time_step), p.end_date
                ).FirstDate
                < p.start_date
            ):
                self.InitialLevel = self.StoredEnergyMatrix.GetForecast(
                    p.execution_date, p.start_date.AddMinutes(-p.time_step), p.end_date
                )

            else:
                self.InitialLevel = opt_hydrau.InitialLevel.Slice(p.start_date.AddMinutes(-p.time_step), p.end_date)

        # get global matrix power
        t0MinusDeltaT = API.DatetimeIndex.Shift(p.hydraulic_op_times, "-" + p.time_step_str)[0]
        power = opt_hydrau.Power.GetForecast(p.execution_date, t0MinusDeltaT, p.start_date)
        if power is None:
            power = opt_hydrau.FinalProg

        # The following power level should be from last forecast of Power matrix, it is final prog for test
        self.power_level_prev = get_time_series_value(power, t0MinusDeltaT)

        for time in p.target_times:
            self.MaximumPowerSum += opt_hydrau.MaximumPower.GetValue(time)

        for time_enum, time in enumerate(p.hydraulic_op_times):
            # Get min and max power
            min_power = get_time_series_value(opt_hydrau.MinimumPower, time)
            max_power = get_time_series_value(opt_hydrau.MaximumPower, time)

            afrrup = opt_hydrau.AFRRUpProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            afrrdown = opt_hydrau.AFRRDownProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            mfrrup = opt_hydrau.MFRRUpProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            mfrrdown = opt_hydrau.MFRRDownProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            rrup = opt_hydrau.RRUpProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            rrdown = opt_hydrau.RRDownProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            fcrup = opt_hydrau.FCRUpProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            fcrdown = opt_hydrau.FCRDownProcured.GetForecast(p.execution_date, time, time).GetValue(time)

            self.MaximumPower[time] = max_power
            self.MinimumPower[time] = min_power
            self.MaximumEnergy[time] = opt_hydrau.MaximumEnergy.GetValue(time)
            self.MinimumEnergy[time] = opt_hydrau.MinimumEnergy.GetValue(time)

            self.AFRRUpProcured[time] = afrrup
            self.AFRRDownProcured[time] = afrrdown
            self.MFRRUpProcured[time] = mfrrup
            self.MFRRDownProcured[time] = mfrrdown
            self.RRUpProcured[time] = rrup
            self.RRDownProcured[time] = rrdown
            self.FCRUpProcured[time] = fcrup
            self.FCRDownProcured[time] = fcrdown

            # init variables
            self.PowerLevel[time] = API.Solver.NewOpVariable(
                f"{self.name}_Power_level_{time_enum}",
                0,
                max_power,
                API.Solver.OpCategoryReal,
            )
            self.StoredEnergy[time] = API.Solver.NewOpVariable(
                f"{self.name}_Stored_Energy_{time_enum}",
                0,
                self.MaximumEnergy[time],
                API.Solver.OpCategoryReal,
            )
            self.getFragmentPriceAndSize(opt_hydrau, time, p)

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
                "ressUp_e_%s_at_%s" % (self.name, str(time_enum)),
                0,
                max_power,
                API.Solver.OpCategoryReal,
            )
            self.reservesDown[time] = API.Solver.NewOpVariable(
                "resDown_e_%s_at_%s" % (self.name, str(time_enum)),
                min_power,
                max_power,
                API.Solver.OpCategoryReal,
            )
            self.unprovidedReservesUp[time] = API.Solver.NewOpVariable(
                "unpResUp_e_%s_at_%s" % (self.name, str(time_enum)),
                0,
                max_power,
                API.Solver.OpCategoryReal,
            )
            self.unprovidedReservesDown[time] = API.Solver.NewOpVariable(
                "unpResDown_e_%s_at_%s" % (self.name, str(time_enum)),
                min_power,
                max_power,
                API.Solver.OpCategoryReal,
            )
            self.relaxedReserves[time] = API.Solver.NewOpVariable(
                "relRes_e_%s_at_%s" % (self.name, str(time_enum)),
                min_power,
                0,
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
            self.contractedDifferenceUp[time] = API.Solver.NewOpVariable(
                "contractedDiffUp_e_%s_at_%s" % (self.name, str(time_enum)),
                0,
                max_power,
                API.Solver.OpCategoryReal,
            )
            self.contractedDifferenceDown[time] = API.Solver.NewOpVariable(
                "contractedDiffDown_e_%s_at_%s" % (self.name, str(time_enum)),
                min_power,
                max_power,
                API.Solver.OpCategoryReal,
            )
            self.automatedContractedDifferenceUp[time] = API.Solver.NewOpVariable(
                "autoContractedDiffUp_e_%s_at_%s" % (self.name, str(time_enum)),
                0,
                max_power,
                API.Solver.OpCategoryReal,
            )
            self.automatedContractedDifferenceDown[time] = API.Solver.NewOpVariable(
                "autoContractedDiffDown_e_%s_at_%s" % (self.name, str(time_enum)),
                min_power,
                max_power,
                API.Solver.OpCategoryReal,
            )

    def getFragmentPriceAndSize(self, opt_hydrau, time, p):
        """
        This function formulates the hydraulic reservoir offers.

        Arguments:
        - `InputMarker`: an input marker
        - `outputMarker`: an output marker
        - `orders_time`: a list of dates at which orders must be formulated.
        """

        delta_wu = {}
        for category in range(len(opt_hydrau.FragmentVolumes)):
            delta_wu[category] = (
                opt_hydrau.FragmentVolumes[category],
                opt_hydrau.FragmentPrices[category],
            )

        energy_forecast = self.StoredEnergyMatrix.GetForecast(
            p.execution_date,
            p.start_date.AddHours(-p.time_step / 60.0),
            p.start_date.AddHours(-p.time_step / 60.0),
        )

        if energy_forecast.Length > 0:
            energyLevel = energy_forecast.GetValue(p.start_date.AddHours(-p.time_step / 60.0))
        else:
            energyLevel = self.InitialLevel.GetValue(p.start_date.AddMinutes(-p.time_step))

        xmin = filter(lambda x: int(x) <= energyLevel, self.StorageMarginalValue.Index)
        xmax = filter(lambda x: int(x) > energyLevel, self.StorageMarginalValue.Index)

        if xmin:
            xpmin = max(xmin, key=lambda x: int(x))
            levelInf = self.StorageMarginalValue.GetTimeSeriesByName(xpmin)
        if xmax:
            xpmax = min(xmax, key=lambda x: int(x))
            levelSup = self.StorageMarginalValue.GetTimeSeriesByName(xpmax)
        if xmin and xmax:
            weightInf = (int(xpmax) - energyLevel) / (int(xpmax) - int(xpmin))
            weightSup = (energyLevel - int(xpmin)) / (int(xpmax) - int(xpmin))

        # Now we loop over the time stamps for which we want an offer to be made.
        # We formulate as many offers as there are time stamps in orders_time.

        # Compute the actual volumes of fragments, according to MaximumPower
        capacity = self.MaximumPower[time]
        volumes = {key: capacity * vu[0] for key, vu in delta_wu.items()}

        if time in p.hydraulic_op_times:
            self.PowerLevelFragmentSum[time] = 0

            # create an offer for each element in volumes
            for k, v in volumes.items():
                if not xmin and xmax:
                    price = levelSup.GetValue(time, API.TimeSeries.Linear) + delta_wu[k][1]
                elif not xmax and xmin:
                    price = levelInf.GetValue(time, API.TimeSeries.Linear) + delta_wu[k][1]
                elif not xmax and not xmin:
                    price = delta_wu[k][1]
                else:
                    # This AREA DEAL WITH THE PRICE
                    pmin = levelInf.GetValue(time, API.TimeSeries.Linear)
                    pmax = levelSup.GetValue(time, API.TimeSeries.Linear)
                    price = weightInf * pmin + weightSup * pmax + delta_wu[k][1]

                self.PowerLevelFragment[k][time] = API.Solver.NewOpVariable(
                    f"{self.name}_Power_level_frag_{k}_at_{str(time)}",
                    0,
                    v,
                    API.Solver.OpCategoryReal,
                )
                self.PriceFragment[k][time] = price

                if k == 0:
                    self.PowerLevelFragmentSum[time] = self.PowerLevelFragment[k][time]
                else:
                    self.PowerLevelFragmentSum[time] += self.PowerLevelFragment[k][time]
