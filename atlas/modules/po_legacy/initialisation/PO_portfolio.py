from PO_functions import get_time_series_value, estimate_imbalance_prices
from PO_thermic import PO_Thermic
from PO_hydraulic import PO_Hydraulic
from PO_storage import PO_Storage
from PO_pv import PO_PV
from PO_wind import PO_Wind
from PO_load import PO_Load
import API


class PO_portfolio(object):
    """
    Object portoflio containing portfolio variables and equipments
    """

    def __init__(self, name):
        self.name = name
        # variable of perimeter P in MW (and not MWh)
        self.Small_imbal_up = {}
        self.Large_imbal_up = {}
        self.Small_imbal_down = {}
        self.Large_imbal_down = {}

        # Variable relate to the reserve
        self.reserve_Up = {}
        self.reserve_Down = {}
        self.automated_Reserve_Up = {}
        self.automated_Reserve_Down = {}
        self.max_power = {}
        self.min_power = {}
        # computed parameters of the perimerter
        self.max_overall_imbal = {}
        self.residualEnergy = {}
        self.small_Imbal_up_limit = 0
        self.small_Imbal_down_limit = 0
        self.imbal_price_up = {}
        self.large_imbal_price_up = {}
        self.imbal_price_down = {}
        self.large_imbal_price_down = {}
        self.priceForecast = {}

        self.contractedDifferenceUp = {}
        self.contractedDifferenceDown = {}
        self.automatedContractedDifferenceUp = {}
        self.automatedContractedDifferenceDown = {}

        self.thermics = {}
        self.hydraulics = {}
        self.storage = {}
        self.Optimal_dispatch_NDP = {}
        self.wind = {}
        self.pv = {}
        self.load = {}
        self.Optimal_dispatch_NDL = {}

    def InitVariablesAndPreComputations(
        self, opt_portfolio, thermics, hydraulics, storage, wind, pv, ndp, ndl, dl, time_index, p
    ):
        max_energy_tot = 0

        globalSeries_NDP = {}
        globalSeries_NDL = {}

        for time_enum, time in enumerate(time_index):
            residualEnergy_ti = 0
            reserve_up_ti = 0
            reserve_down_ti = 0
            automated_reserve_up_ti = 0
            automated_reserve_down_ti = 0
            max_power_ti = 0

            if time in p.target_times:
                if p.use_forecast:
                    if p.market == "DayAhead":
                        self.priceForecast[time] = opt_portfolio.MarketArea.PriceForecastMedium.GetValue(time)
                    elif p.market == "Intraday":
                        self.priceForecast[time] = opt_portfolio.MarketArea.IDPriceForecast.GetForecast(
                            p.execution_date, time, time
                        ).GetValue(time)
                else:
                    if p.market == "DayAhead":
                        self.priceForecast[time] = opt_portfolio.MarketArea.DAPrice.GetValue(time)
                    elif p.market == "Intraday":
                        self.priceForecast[time] = opt_portfolio.MarketArea.IDPrice.GetForecast(
                            p.execution_date, time, time
                        ).GetValue(time)
                    elif p.market == "RRActivation":
                        self.priceForecast[time] = opt_portfolio.MarketArea.RRActivationPrice.GetValue(time)
                    elif p.market == "MFRRActivation":
                        self.priceForecast[time] = opt_portfolio.MarketArea.MFRRActivationPrice.GetValue(time)
            else:
                price = opt_portfolio.MarketArea.PriceForecastMedium.GetForecast(p.execution_date, time, time).GetValue(
                    time
                )  # Need some change
                self.priceForecast[time] = price

            # --- NonDispatchable productions ---
            hasImbalPrice = 0
            for opt_NDP in ndp:
                # Initialization
                if time_enum == 0:
                    globalSeries_NDP[opt_NDP] = opt_NDP.MaximumPowerForecast.GetForecast(
                        p.execution_date, p.start_date, p.end_date
                    )
                    self.Optimal_dispatch_NDP[opt_NDP.Name] = {}
                lastForecast_ti = 0

                if globalSeries_NDP[opt_NDP] is not None:
                    lastForecast_ti = get_time_series_value(globalSeries_NDP[opt_NDP], time)
                if hasImbalPrice == 0:
                    # get DAPrice (first equipment in list set the DAPrice)
                    estimate_imbalance_prices(
                        time,
                        opt_portfolio,
                        opt_NDP.Node.MarketArea,
                        opt_NDP.Node.ControlBlock,
                        self.imbal_price_up,
                        self.large_imbal_price_up,
                        self.imbal_price_down,
                        self.large_imbal_price_down,
                        p,
                    )
                    hasImbalPrice = 1

                # compute residual energy

                if p.market == "RRActivation":
                    upstream_sold_energy_ti = get_time_series_value(opt_NDP.RRActivated, time)
                elif p.market == "MFRRActivation":
                    upstream_sold_energy_ti = get_time_series_value(opt_NDP.MFRRActivated, time)
                else:
                    upstream_sold_energy_ti = get_time_series_value(
                        opt_NDP.TotalIDClearedQuantity, time
                    ) + get_time_series_value(opt_NDP.DAClearedQuantity, time)

                optimal_dispatch_ti = min(lastForecast_ti, upstream_sold_energy_ti)
                residualEnergy_ti += upstream_sold_energy_ti - optimal_dispatch_ti

                # save optimal dispatch
                self.Optimal_dispatch_NDP[opt_NDP.Name][time] = optimal_dispatch_ti

            # --- Non dispatchable Loads ---
            i_ndload = 0
            for opt_load in ndl:
                # Initialization
                if time_enum == 0:
                    globalSeries_NDL[opt_load] = opt_load.MaximumPowerForecast.GetForecast(
                        p.execution_date, p.start_date, p.end_date
                    )
                    self.Optimal_dispatch_NDL[opt_load.Name] = {}

                lastForecast_ti = 0
                if globalSeries_NDL[opt_load] is not None:
                    lastForecast_ti = get_time_series_value(globalSeries_NDL[opt_load], time)
                if hasImbalPrice == 0:
                    # get DAPrice (first equipment in list set the DAPrice)
                    estimate_imbalance_prices(
                        time,
                        opt_portfolio,
                        opt_load.Node.MarketArea,
                        opt_load.Node.ControlBlock,
                        self.imbal_price_up,
                        self.large_imbal_price_up,
                        self.imbal_price_down,
                        self.large_imbal_price_down,
                        p,
                    )
                    hasImbalPrice = 1

                # compute residual energy
                inflexqty_ti = lastForecast_ti

                if p.market == "RRActivation":
                    upstream_bought_energy_ti = get_time_series_value(opt_load.RRActivated, time)
                elif p.market == "MFRRActivation":
                    upstream_bought_energy_ti = get_time_series_value(opt_load.MFRRActivated, time)
                else:
                    upstream_bought_energy_ti = get_time_series_value(
                        opt_load.TotalIDClearedQuantity, time
                    ) + get_time_series_value(opt_load.DAClearedQuantity, time)

                optimal_dispatch_ti = min(inflexqty_ti, upstream_bought_energy_ti)
                residualEnergy_ti += upstream_bought_energy_ti - optimal_dispatch_ti
                self.Optimal_dispatch_NDL[opt_load.Name][time] = optimal_dispatch_ti

                i_ndload += 1

            # --- Dispatchable Loads ---
            for opt_load in dl:
                if time_enum == 0:
                    PO_loadj = PO_Load(opt_load.Name)
                    PO_loadj.init_variables(opt_load, p)
                    self.load[opt_load.Name] = PO_loadj

                if hasImbalPrice == 0:
                    # get DAPrice (first equipment in list set the DAPrice)
                    estimate_imbalance_prices(
                        time,
                        opt_portfolio,
                        opt_load.Node.MarketArea,
                        opt_load.Node.ControlBlock,
                        self.imbal_price_up,
                        self.large_imbal_price_up,
                        self.imbal_price_down,
                        self.large_imbal_price_down,
                        p,
                    )
                    hasImbalPrice = 1

                # compute residual energy
                if p.market == "RRActivation":
                    upstream_bought_energy_ti = get_time_series_value(opt_load.RRActivated, time)
                elif p.market == "MFRRActivation":
                    upstream_bought_energy_ti = get_time_series_value(opt_load.MFRRActivated, time)
                else:
                    upstream_bought_energy_ti = get_time_series_value(
                        opt_load.TotalIDClearedQuantity, time
                    ) + get_time_series_value(opt_load.DAClearedQuantity, time)

                residualEnergy_ti += upstream_bought_energy_ti

                # Compute reserve
                (reserve_up_ti, reserve_down_ti, automated_reserve_up_ti, automated_reserve_down_ti, max_power_ti) = (
                    self.get_reserve(
                        opt_load,
                        reserve_up_ti,
                        reserve_down_ti,
                        automated_reserve_up_ti,
                        automated_reserve_down_ti,
                        max_power_ti,
                        time,
                        p,
                    )
                )

                # get max power
                if time_enum == 0:
                    max_energy_tot = max_energy_tot + abs(PO_loadj.MaximumPower[time])

            # --- Wind ---
            for opt_wind in wind:
                # Get last forecast
                if time_enum == 0:
                    PO_windj = PO_Wind(opt_wind.Name)
                    PO_windj.init_variables(opt_wind, p)
                    self.wind[opt_wind.Name] = PO_windj

                if hasImbalPrice == 0:
                    # get DAPrice (first equipment in list set the DAPrice)
                    estimate_imbalance_prices(
                        time,
                        opt_portfolio,
                        opt_wind.Node.MarketArea,
                        opt_wind.Node.ControlBlock,
                        self.imbal_price_up,
                        self.large_imbal_price_up,
                        self.imbal_price_down,
                        self.large_imbal_price_down,
                        p,
                    )
                    hasImbalPrice = 1

                # compute residual energy
                if p.market == "RRActivation":
                    upstream_sold_energy_ti = get_time_series_value(opt_wind.RRActivated, time)
                elif p.market == "MFRRActivation":
                    upstream_sold_energy_ti = get_time_series_value(opt_wind.MFRRActivated, time)
                else:
                    upstream_sold_energy_ti = get_time_series_value(
                        opt_wind.TotalIDClearedQuantity, time
                    ) + get_time_series_value(opt_wind.DAClearedQuantity, time)

                residualEnergy_ti += upstream_sold_energy_ti

                # Compute reserve
                (reserve_up_ti, reserve_down_ti, automated_reserve_up_ti, automated_reserve_down_ti, max_power_ti) = (
                    self.get_reserve(
                        opt_wind,
                        reserve_up_ti,
                        reserve_down_ti,
                        automated_reserve_up_ti,
                        automated_reserve_down_ti,
                        max_power_ti,
                        time,
                        p,
                    )
                )

                # get max power
                if time_enum == 0:
                    max_energy_tot = max_energy_tot + PO_windj.MaximumPower[time]

            # --- Photovoltaic ---
            for opt_PV in pv:
                # Get last forecast
                if time_enum == 0:
                    PO_pvj = PO_PV(opt_PV.Name)
                    PO_pvj.init_variables(opt_PV, p)
                    self.pv[opt_PV.Name] = PO_pvj

                if hasImbalPrice == 0:
                    # get DAPrice (first equipment in list set the DAPrice)
                    estimate_imbalance_prices(
                        time,
                        opt_portfolio,
                        opt_PV.Node.MarketArea,
                        opt_PV.Node.ControlBlock,
                        self.imbal_price_up,
                        self.large_imbal_price_up,
                        self.imbal_price_down,
                        self.large_imbal_price_down,
                        p,
                    )
                    hasImbalPrice = 1

                # compute residual energy
                if p.market == "RRActivation":
                    upstream_sold_energy_ti = get_time_series_value(opt_PV.RRActivated, time)
                elif p.market == "MFRRActivation":
                    upstream_sold_energy_ti = get_time_series_value(opt_PV.MFRRActivated, time)
                else:
                    upstream_sold_energy_ti = get_time_series_value(
                        opt_PV.TotalIDClearedQuantity, time
                    ) + get_time_series_value(opt_PV.DAClearedQuantity, time)

                residualEnergy_ti += upstream_sold_energy_ti

                # Compute reserve
                (reserve_up_ti, reserve_down_ti, automated_reserve_up_ti, automated_reserve_down_ti, max_power_ti) = (
                    self.get_reserve(
                        opt_PV,
                        reserve_up_ti,
                        reserve_down_ti,
                        automated_reserve_up_ti,
                        automated_reserve_down_ti,
                        max_power_ti,
                        time,
                        p,
                    )
                )

                # get max power
                if time_enum == 0:
                    max_energy_tot = max_energy_tot + PO_pvj.MaximumPower[time]

            # --- Thermic ---
            for opt_index, opt_thermic in enumerate(thermics):
                if time_enum == 0:
                    if p.debug:
                        API.IO.Trace.Log("Debug thermic equiments match: ")
                        API.IO.Trace.Log("{} = {}".format(opt_thermic.Name, "th_" + str(opt_index)))

                    PO_DTj = PO_Thermic(opt_thermic.Name, opt_index)
                    PO_DTj.init_variables(opt_thermic, p)
                    self.thermics[opt_thermic.Name] = PO_DTj
                if hasImbalPrice == 0:
                    estimate_imbalance_prices(
                        time,
                        opt_portfolio,
                        opt_thermic.Node.MarketArea,
                        opt_thermic.Node.ControlBlock,
                        self.imbal_price_up,
                        self.large_imbal_price_up,
                        self.imbal_price_down,
                        self.large_imbal_price_down,
                        p,
                    )
                    hasImbalPrice = 1
                # compute residual energy
                if p.market == "RRActivation":
                    upstream_sold_energy_ti = get_time_series_value(opt_thermic.RRActivated, time)
                elif p.market == "MFRRActivation":
                    upstream_sold_energy_ti = get_time_series_value(opt_thermic.MFRRActivated, time)
                else:
                    upstream_sold_energy_ti = get_time_series_value(
                        opt_thermic.TotalIDClearedQuantity, time
                    ) + get_time_series_value(opt_thermic.DAClearedQuantity, time)

                residualEnergy_ti += upstream_sold_energy_ti

                # Compute reserve
                (reserve_up_ti, reserve_down_ti, automated_reserve_up_ti, automated_reserve_down_ti, max_power_ti) = (
                    self.get_reserve(
                        opt_thermic,
                        reserve_up_ti,
                        reserve_down_ti,
                        automated_reserve_up_ti,
                        automated_reserve_down_ti,
                        max_power_ti,
                        time,
                        p,
                    )
                )

                # get max power
                if time_enum == 0:
                    max_energy_tot = max_energy_tot + PO_DTj.MaximumPower[time]

            # --- Hydraulic ---
            for opt_hydrau in hydraulics:
                if time_enum == 0:
                    PO_DHj = PO_Hydraulic(opt_hydrau, opt_hydrau.Name, p)
                    PO_DHj.init_variables(opt_hydrau, p)
                    self.hydraulics[opt_hydrau.Name] = PO_DHj
                if hasImbalPrice == 0:
                    # get DAPrice (first equipment in list set the DAPrice)
                    estimate_imbalance_prices(
                        time,
                        opt_portfolio,
                        opt_hydrau.Node.MarketArea,
                        opt_hydrau.Node.ControlBlock,
                        self.imbal_price_up,
                        self.large_imbal_price_up,
                        self.imbal_price_down,
                        self.large_imbal_price_down,
                        p,
                    )
                    hasImbalPrice = 1

                # compute residual energy
                if p.market == "RRActivation":
                    upstream_sold_energy_ti = get_time_series_value(opt_hydrau.RRActivated, time)
                elif p.market == "MFRRActivation":
                    upstream_sold_energy_ti = get_time_series_value(opt_hydrau.MFRRActivated, time)
                else:
                    upstream_sold_energy_ti = get_time_series_value(
                        opt_hydrau.TotalIDClearedQuantity, time
                    ) + get_time_series_value(opt_hydrau.DAClearedQuantity, time)

                residualEnergy_ti += upstream_sold_energy_ti

                # Compute reserve
                (reserve_up_ti, reserve_down_ti, automated_reserve_up_ti, automated_reserve_down_ti, max_power_ti) = (
                    self.get_reserve(
                        opt_hydrau,
                        reserve_up_ti,
                        reserve_down_ti,
                        automated_reserve_up_ti,
                        automated_reserve_down_ti,
                        max_power_ti,
                        time,
                        p,
                    )
                )
                # get max power
                if time_enum == 0:
                    max_energy_tot = max_energy_tot + PO_DHj.MaximumPower[time]

            # --- Storage ---
            for opt_storage in storage:
                if time_enum == 0:
                    PO_DSj = PO_Storage(opt_storage.Name, p)
                    PO_DSj.init_variables(opt_storage, p)
                    self.storage[opt_storage.Name] = PO_DSj

                if hasImbalPrice == 0:
                    # get DAPrice (first equipment in list set the DAPrice)
                    estimate_imbalance_prices(
                        time,
                        opt_portfolio,
                        opt_storage.Node.MarketArea,
                        opt_storage.Node.ControlBlock,
                        self.imbal_price_up,
                        self.large_imbal_price_up,
                        self.imbal_price_down,
                        self.large_imbal_price_down,
                        p,
                    )
                    hasImbalPrice = 1

                # compute residual energy
                if p.market == "RRActivation":
                    upstream_sold_energy_ti = get_time_series_value(opt_storage.RRActivated, time)
                elif p.market == "MFRRActivation":
                    upstream_sold_energy_ti = get_time_series_value(opt_storage.MFRRActivated, time)
                else:
                    upstream_sold_energy_ti = get_time_series_value(
                        opt_storage.TotalIDClearedQuantity, time
                    ) + get_time_series_value(opt_storage.DAClearedQuantity, time)

                residualEnergy_ti += upstream_sold_energy_ti

                # Compute reserve
                (reserve_up_ti, reserve_down_ti, automated_reserve_up_ti, automated_reserve_down_ti, max_power_ti) = (
                    self.get_reserve(
                        opt_storage,
                        reserve_up_ti,
                        reserve_down_ti,
                        automated_reserve_up_ti,
                        automated_reserve_down_ti,
                        max_power_ti,
                        time,
                        p,
                    )
                )
                # get max power
                if time_enum == 0:
                    max_energy_tot = max_energy_tot + PO_DSj.MaximumPower[time]

            # save values at ti
            self.residualEnergy[time] = residualEnergy_ti

            self.reserve_Up[time] = reserve_up_ti
            self.reserve_Down[time] = reserve_down_ti
            self.automated_Reserve_Up[time] = automated_reserve_up_ti
            self.automated_Reserve_Down[time] = automated_reserve_down_ti
            self.max_power[time] = max_power_ti

            # should be min in specifications but in tests it is max
            self.max_overall_imbal[time] = max(residualEnergy_ti, p.max_overall_imbalance)

        # compute imbal limits and compute reserve
        self.small_Imbal_up_limit = max_energy_tot * p.small_imbalance_size
        self.small_Imbal_down_limit = self.small_Imbal_up_limit
        if p.verbose:
            msg = "In portfolio: {}, the smal imbal up limit is {} MWh".format(
                opt_portfolio.Name, self.small_Imbal_up_limit
            )
            API.IO.Trace.Log(msg, API.IO.LogTypeInfo)
        for time_enum, time in enumerate(time_index):
            # create variables at ti
            self.Small_imbal_up[time] = API.Solver.NewOpVariable(
                "{name}_small_imbal_up{val}".format(name=self.name, val=time_enum),
                0,
                self.small_Imbal_up_limit,
                API.Solver.OpCategoryReal,
            )
            self.Large_imbal_up[time] = API.Solver.NewOpVariable(
                "{name}_large_imbal_up{val}".format(name=self.name, val=time_enum),
                0,
                self.max_overall_imbal[time],
                API.Solver.OpCategoryReal,
            )
            self.Small_imbal_down[time] = API.Solver.NewOpVariable(
                "{name}_small_imbal_down{val}".format(name=self.name, val=time_enum),
                0,
                self.small_Imbal_down_limit,
                API.Solver.OpCategoryReal,
            )
            self.Large_imbal_down[time] = API.Solver.NewOpVariable(
                "{name}_large_imbal_down{val}".format(name=self.name, val=time_enum),
                0,
                self.max_overall_imbal[time],
                API.Solver.OpCategoryReal,
            )

            # QB: This check is probably useless (max_power >= 0 by construction and egals 0 if no equipment are present in the portfolio or all their maxpower is 0)
            # This check causes issues in UC mode
            # if self.max_power[time] > 0:
            self.contractedDifferenceUp[time] = API.Solver.NewOpVariable(
                "contractedDiffUp_e_%s_at_%s" % (self.name, str(time_enum)),
                0,
                self.max_power[time],
                API.Solver.OpCategoryReal,
            )
            self.contractedDifferenceDown[time] = API.Solver.NewOpVariable(
                "contractedDiffDown_e_%s_at_%s" % (self.name, str(time_enum)),
                0,
                self.max_power[time],
                API.Solver.OpCategoryReal,
            )
            self.automatedContractedDifferenceUp[time] = API.Solver.NewOpVariable(
                "autoContractedDiffUp_e_%s_at_%s" % (self.name, str(time_enum)),
                0,
                self.max_power[time],
                API.Solver.OpCategoryReal,
            )
            self.automatedContractedDifferenceDown[time] = API.Solver.NewOpVariable(
                "autoContractedDiffDown_e_%s_at_%s" % (self.name, str(time_enum)),
                0,
                self.max_power[time],
                API.Solver.OpCategoryReal,
            )

    def get_reserve(
        self,
        opt,
        reserve_up_ti,
        reserve_down_ti,
        automated_reserve_up_ti,
        automated_reserve_down_ti,
        max_power_ti,
        time,
        p,
    ):
        maximumAFRR = opt.MaximumAFRR
        maximumFCR = opt.MaximumFCR
        # QB: Added abs() because MaximumPowerForecast is negative for load units
        if opt.Class in ["Wind", "Photovoltaic", "Load", "OtherNonDispatchable"]:
            max_power_ti += abs(
                get_time_series_value(opt.MaximumPowerForecast.GetForecast(p.execution_date, time, time), time)
            )
        # QB: Added an 'else' here, as MaximumPower is no longer defined for some units
        else:
            max_power_ti += abs(get_time_series_value(opt.MaximumPower, time))

        afrrup = opt.AFRRUpProcured.GetForecast(p.execution_date, time, time).GetValue(time)
        afrrdown = opt.AFRRDownProcured.GetForecast(p.execution_date, time, time).GetValue(time)
        mfrrup = opt.MFRRUpProcured.GetForecast(p.execution_date, time, time).GetValue(time)

        mfrrdown = opt.MFRRDownProcured.GetForecast(p.execution_date, time, time).GetValue(time)
        rrup = opt.RRUpProcured.GetForecast(p.execution_date, time, time).GetValue(time)
        rrdown = opt.RRDownProcured.GetForecast(p.execution_date, time, time).GetValue(time)
        fcrup = opt.FCRUpProcured.GetForecast(p.execution_date, time, time).GetValue(time)
        fcrdown = opt.FCRDownProcured.GetForecast(p.execution_date, time, time).GetValue(time)

        reserve_up_ti += rrup + mfrrup
        reserve_down_ti += rrdown + mfrrdown
        automated_reserve_up_ti += min(afrrup, maximumAFRR) + min(fcrup, maximumFCR)
        automated_reserve_down_ti += min(afrrdown, maximumAFRR) + min(fcrdown, maximumFCR)

        return (reserve_up_ti, reserve_down_ti, automated_reserve_up_ti, automated_reserve_down_ti, max_power_ti)
