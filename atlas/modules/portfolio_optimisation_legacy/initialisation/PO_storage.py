import sys

import API
from PO_functions import get_time_series_value


class PO_Storage:
    """
    This class is used to feed a PO_Storage from a storage equipment
    """

    def __init__(self, name, p):
        self.name = name
        self.StorageType = ""
        self.PowerLevelBuy = {}
        self.PowerLevelSell = {}

        self.PowerLevelBuy_n = {}
        self.PowerLevelSell_n = {}

        for n in range(0, max(p.ev_nb_fragments, p.battery_nb_fragments, p.phs_nb_fragments)):
            self.PowerLevelBuy_n[n] = {}
            self.PowerLevelSell_n[n] = {}

        self.StoredEnergy = {}
        self.Usable_energy = {}

        self.Is_Sell = {}

        # parameters from optimate equipment to optimized memory
        self.LastTimeT = 0
        self.VariableCost = 0
        self.StartupCost = 0
        self.InitialStock = 0
        self.ChargeEfficiency = 1
        self.DischargeEfficiency = 1
        self.isV2G = 0

        # self.AFRRMax = 0
        self.MaximumPower = {}
        self.MinimumPower = {}
        self.DAClearedQuantity = {}
        self.DisplacementEnergy = {}

        # reserve requirements
        self.aFRRUpProcured = {}
        self.aFRRDownProcured = {}
        self.mFRRUpProcured = {}
        self.mFRRDownProcured = {}
        self.rRUpProcured = {}
        self.rRDownProcured = {}
        self.fCRUpProcured = {}
        self.fCRDownProcured = {}
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
        self.automatedReservesUp = {}
        self.automatedReservesDown = {}
        self.contractedDifferenceUp = {}
        self.contractedDifferenceDown = {}
        self.automatedContractedDifferenceUp = {}
        self.automatedContractedDifferenceDown = {}

        self.MaximumEnergy = {}
        self.MinimumStateOfCharge = {}
        self.maximumAFRR = 0
        self.maximumFCR = 0
        self.maximumAutomated = 0

    def init_variables(self, opt_storage, p):
        # Retrieve the optimization time frame
        if opt_storage.StorageType == "Battery":
            op_time_frame = p.battery_op_times
        elif opt_storage.StorageType == "PumpedHydraulicStorage":
            op_time_frame = p.phs_op_times
        elif opt_storage.StorageType == "ElectricVehicle":
            op_time_frame = p.ev_op_times

        # get data from optimate equipment
        self.VariableCost = get_time_series_value(opt_storage.VariableCost, p.start_date)
        self.StartupCost = get_time_series_value(opt_storage.StartupCost, p.start_date)

        self.maximumAFRR = opt_storage.MaximumAFRR
        self.maximumFCR = opt_storage.MaximumFCR

        # a affiner en fonction de stored energy
        self.StorageType = opt_storage.StorageType

        # FC: hypothesis here, we check if the StoredEnergy matrix has values over the last 48 hours
        # If it is not the case, the equipment is assumed to be in initial state.
        # This hypothesis could be challenged, but is at least applied uniformly to all modules
        if (
            opt_storage.StoredEnergy.GetForecast(
                p.execution_date, p.init_battery_time.AddDays(-2), p.init_battery_time
            ).Length
            == 0
        ):
            self.InitialStock = (
                get_time_series_value(opt_storage.MaximumEnergy, p.start_date.AddMinutes(-p.time_step))
                * opt_storage.StorageInitialLevel
            )

        else:
            self.InitialStock = opt_storage.StoredEnergy.GetForecast(
                p.execution_date, p.init_battery_time, p.init_battery_time
            )[0]

        if p.debug:
            msg = f"The initial energy storage level is : {self.InitialStock} MWh"
            API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

        self.isV2G = opt_storage.isV2G
        self.ChargeEfficiency = opt_storage.ChargeEfficiency
        self.DischargeEfficiency = opt_storage.DischargeEfficiency

        if self.ChargeEfficiency == 0:
            msg = f"The property ChargeEfficiency of the equipement {opt_storage.Name} must be greater than 0."
            API.IO.Trace.Log(msg, API.IO.LogTypeWarn)
        # Check if the equipement is able to be discharge if Zero a division by zero will appeared
        if self.DischargeEfficiency == 0:
            msg = f"The property DischargeEfficiency of the equipement {opt_storage.Name} must be greater than 0."
            API.IO.Trace.Log(msg, API.IO.LogTypeError)
            sys.exit()  ### FUTURE WARNING : WILL HAVE TO BE REPLACED BY AN API FUNCTION THAT STOPS THE EXECUTION OF THE PROGRAM ASAP

        # self.MinimumStateOfCharge = opt_storage.MinimumStateOfCharge

        for time_enum, time in enumerate(op_time_frame):
            max_power = get_time_series_value(opt_storage.MaximumPower, time)
            if opt_storage.MinimumPower.Count == 0:
                min_power = -max_power
            else:
                min_power = get_time_series_value(opt_storage.MinimumPower, time)

            max_stock = get_time_series_value(opt_storage.MaximumEnergy, time)
            minSOC = get_time_series_value(opt_storage.MinimumStateOfCharge, time)
            disp_en = get_time_series_value(opt_storage.DisplacementEnergy, time)

            afrrup = opt_storage.AFRRUpProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            afrrdown = opt_storage.AFRRDownProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            mfrrup = opt_storage.MFRRUpProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            mfrrdown = opt_storage.MFRRDownProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            rrup = opt_storage.RRUpProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            rrdown = opt_storage.RRDownProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            fcrup = opt_storage.FCRUpProcured.GetForecast(p.execution_date, time, time).GetValue(time)
            fcrdown = opt_storage.FCRDownProcured.GetForecast(p.execution_date, time, time).GetValue(time)

            self.MaximumPower[time] = max_power
            self.MinimumPower[time] = min_power

            if time_enum == 0:
                self.MaximumEnergy[time.AddMinutes(-p.time_step)] = get_time_series_value(
                    opt_storage.MaximumEnergy, time.AddMinutes(-p.time_step)
                )
                self.MinimumStateOfCharge[time.AddMinutes(-p.time_step)] = get_time_series_value(
                    opt_storage.MinimumStateOfCharge, time.AddMinutes(-p.time_step)
                )
                self.DisplacementEnergy[time.AddMinutes(-p.time_step)] = get_time_series_value(
                    opt_storage.DisplacementEnergy, time.AddMinutes(-p.time_step)
                )

            self.MaximumEnergy[time] = max_stock
            self.MinimumStateOfCharge[time] = minSOC
            self.DisplacementEnergy[time] = disp_en

            self.aFRRUpProcured[time] = afrrup
            self.aFRRDownProcured[time] = afrrdown
            self.mFRRUpProcured[time] = mfrrup
            self.mFRRDownProcured[time] = mfrrdown
            self.rRUpProcured[time] = rrup
            self.rRDownProcured[time] = rrdown
            self.fCRUpProcured[time] = fcrup
            self.fCRDownProcured[time] = fcrdown

            # Create variables at time
            self.PowerLevelSell[time] = API.Solver.NewOpVariable(
                f"{self.name}_power_level_sell_{time_enum}",
                0,
                max_power,
                API.Solver.OpCategoryReal,
            )
            self.PowerLevelBuy[time] = API.Solver.NewOpVariable(
                f"{self.name}_power_level_buy_{time_enum}",
                min_power,
                0,
                API.Solver.OpCategoryReal,
            )
            self.Is_Sell[time] = API.Solver.NewOpVariable(
                f"{self.name}_is_sell_{time_enum}", API.Solver.OpCategoryBinary
            )
            self.StoredEnergy[time] = API.Solver.NewOpVariable(
                f"{self.name}_StoredEnergy_{time_enum}",
                minSOC * max_stock,
                max_stock,
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

            if self.StorageType == "Battery":
                nbr_fragement = p.battery_nb_fragments
            elif self.StorageType == "ElectricVehicle":
                nbr_fragement = p.ev_nb_fragments
            elif self.StorageType == "PumpedHydraulicStorage":
                nbr_fragement = p.phs_nb_fragments

            for n in range(0, nbr_fragement):
                self.PowerLevelSell_n[n][time] = API.Solver.NewOpVariable(
                    f"{self.name}_power_level_sell_n_{n}_time_{time_enum}",
                    0,
                    max_power,
                    API.Solver.OpCategoryReal,
                )
                self.PowerLevelBuy_n[n][time] = API.Solver.NewOpVariable(
                    f"{self.name}_power_level_buy_n_{n}_time_{time_enum}",
                    min_power,
                    0,
                    API.Solver.OpCategoryReal,
                )

            # Optimisation Variables related tp,
            self.reservesUp[time] = API.Solver.NewOpVariable(
                "resUp_e_%s_at_%s" % (self.name, str(time)), 0, max_power, API.Solver.OpCategoryReal
            )
            self.reservesDown[time] = API.Solver.NewOpVariable(
                "resDown_e_%s_at_%s" % (self.name, str(time)),
                min_power,
                max_power,
                API.Solver.OpCategoryReal,
            )
            self.unprovidedReservesUp[time] = API.Solver.NewOpVariable(
                "unprResUp_e_%s_at_%s" % (self.name, str(time)),
                0,
                max_power,
                API.Solver.OpCategoryReal,
            )
            self.unprovidedReservesDown[time] = API.Solver.NewOpVariable(
                "unprResDown_e_%s_at_%s" % (self.name, str(time)),
                min_power,
                max_power,
                API.Solver.OpCategoryReal,
            )
            self.automatedReservesUp[time] = API.Solver.NewOpVariable(
                "autoResUp_e_%s_at_%s" % (self.name, str(time)),
                0,
                self.maximumAutomated,
                API.Solver.OpCategoryReal,
            )
            self.automatedReservesDown[time] = API.Solver.NewOpVariable(
                "autoResDown_e_%s_at_%s" % (self.name, str(time)),
                -self.maximumAutomated,
                self.maximumAutomated,
                API.Solver.OpCategoryReal,
            )
