from ast import Load

from pendulum import DateTime

from atlas.models.equipment.hydro import Hydro
from atlas.models.equipment.other_non_dispatchable import OtherNonDispatchable
from atlas.models.equipment.solar import Solar
from atlas.models.equipment.storage import Storage
from atlas.models.equipment.thermal import Thermal
from atlas.models.equipment.wind import Wind
from atlas.models.portfolio import Portfolio
from atlas.modules.portfolio_optimisation.initialisation.PO_hydraulic import POHydraulic
from atlas.modules.portfolio_optimisation.initialisation.PO_load import POLoad
from atlas.modules.portfolio_optimisation.initialisation.PO_pv import POPV
from atlas.modules.portfolio_optimisation.initialisation.PO_storage import POStorage
from atlas.modules.portfolio_optimisation.initialisation.PO_wind import POWind
from atlas.modules.portfolio_optimisation.parameters import MarketEnum, PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.imbalance_price import estimate_imbalance_prices
from atlas.solver.solver_interface import OptimisationModel


class POPortfolio:
    """
    Object portfolio containing portfolio variables and equipments
    """

    def __init__(self, name):
        self.name = name
        # variable of perimeter P in MW (and not MWh)
        self.small_imbal_up = {}
        self.large_imbal_up = {}
        self.small_imbal_down = {}
        self.large_imbal_down = {}

        # Variable relate to the reserve
        self.reserve_up = {}
        self.reserve_down = {}
        self.automated_reserve_up = {}
        self.automated_reserve_down = {}
        self.max_power = {}
        self.min_power = {}
        # computed parameters of the perimerter
        self.max_overall_imbal = {}
        self.residual_energy = {}
        self.small_imbal_up_limit = 0
        self.small_imbal_down_limit = 0
        self.imbal_price_up = {}
        self.large_imbal_price_up = {}
        self.imbal_price_down = {}
        self.large_imbal_price_down = {}
        self.price_forecast = {}

        self.contracted_difference_up = {}
        self.contracted_difference_down = {}
        self.automated_contracted_difference_up = {}
        self.automated_contracted_difference_down = {}

        self.thermics = {}
        self.hydraulics = {}
        self.storage = {}
        self.optimal_dispatch_ndp = {}
        self.wind = {}
        self.pv = {}
        self.load = {}
        self.optimal_dispatch_ndl = {}

    def init_variables_and_pre_computations(
        self,
        portfolio_object: Portfolio,
        thermics: list[Thermal],
        hydraulics: list[Hydro],
        storage: list[Storage],
        wind: list[Wind],
        pv: list[Solar],
        ndp,
        ndl: list[OtherNonDispatchable],
        dl: list[Load],
        time_index,
        parameters: PortfolioOptimisationParameters,
        optimisation_model: OptimisationModel,
    ):
        max_energy_tot = 0

        global_series_ndp = {}
        global_series_ndl = {}

        for idx, time in enumerate(time_index):
            residual_energy_ti = 0
            reserve_up_ti = 0
            reserve_down_ti = 0
            automated_reserve_up_ti = 0
            automated_reserve_down_ti = 0
            max_power_ti = 0

            if time in parameters.target_times:
                if parameters.use_forecast:
                    if parameters.market == MarketEnum.dayahead:
                        self.price_forecast[time] = portfolio_object.market_area.price_forecast_medium.get_value(time)
                    elif parameters.market == MarketEnum.intraday:
                        self.price_forecast[time] = portfolio_object.market_area.id_price_forecast.get_forecast(
                            parameters.execution_date, time, time
                        ).get_value(time)
                else:
                    if parameters.market == MarketEnum.dayahead:
                        self.price_forecast[time] = portfolio_object.market_area.da_price.get_value(time)
                    elif parameters.market == MarketEnum.intraday:
                        self.price_forecast[time] = portfolio_object.market_area.id_price.get_forecast(
                            parameters.execution_date, time, time
                        ).get_value(time)
                    elif parameters.market == MarketEnum.rr_activation:
                        self.price_forecast[time] = portfolio_object.market_area.rr_activation_price.get_value(time)
                    elif parameters.market == MarketEnum.mfrr_activation:
                        self.price_forecast[time] = portfolio_object.market_area.mfrr_activation_price.get_value(time)
            else:
                price = portfolio_object.market_area.price_forecast_medium.get_forecast(
                    parameters.execution_date, time, time
                ).get_value(time)  # Need some change
                self.price_forecast[time] = price

            # --- non_dispatchable productions ---
            has_imbal_price = 0
            for opt_ndp in ndp:
                # Initialization
                if idx == 0:
                    global_series_ndp[opt_ndp] = opt_ndp.maximum_power_forecast.get_forecast(
                        parameters.execution_date, parameters.start_date, parameters.end_date
                    )
                    self.optimal_dispatch_ndp[opt_ndp.name] = {}
                last_forecast_ti = 0

                if global_series_ndp[opt_ndp] is not None:
                    last_forecast_ti = global_series_ndp[opt_ndp].get_value(time)
                if has_imbal_price == 0:
                    # get da_price (first equipment in list set the da_price)
                    estimate_imbalance_prices(
                        time,
                        portfolio_object,
                        opt_ndp.node.market_area,
                        opt_ndp.node.control_block,
                        self.imbal_price_up,
                        self.large_imbal_price_up,
                        self.imbal_price_down,
                        self.large_imbal_price_down,
                        parameters,
                    )
                    has_imbal_price = 1

                if parameters.market == MarketEnum.rr_activation:
                    upstream_sold_energy_ti = opt_ndp.rr_activated.get_value(time)
                elif parameters.market == MarketEnum.mfrr_activation:
                    upstream_sold_energy_ti = opt_ndp.mfrr_activated.get_value(time)
                else:
                    upstream_sold_energy_ti = opt_ndp.total_id_cleared_quantity.get_value(
                        time
                    ) + opt_ndp.da_cleared_quantity.get_value(time)

                optimal_dispatch_ti = min(last_forecast_ti, upstream_sold_energy_ti)
                residual_energy_ti += upstream_sold_energy_ti - optimal_dispatch_ti

                # save optimal dispatch
                self.optimal_dispatch_ndp[opt_ndp.name][time] = optimal_dispatch_ti

            # --- non dispatchable loads ---
            i_ndload = 0
            for opt_load in ndl:
                # Initialization
                if idx == 0:
                    global_series_ndl[opt_load] = opt_load.maximum_power_forecast.get_forecast(
                        parameters.execution_date, parameters.start_date, parameters.end_date
                    )
                    self.optimal_dispatch_ndl[opt_load.name] = {}

                last_forecast_ti = 0
                if global_series_ndl[opt_load] is not None:
                    last_forecast_ti = global_series_ndl[opt_load].get_value(time)
                if has_imbal_price == 0:
                    # get da_price (first equipment in list set the da_price)
                    estimate_imbalance_prices(
                        time,
                        portfolio_object,
                        opt_load.node.market_area,
                        opt_load.node.control_block,
                        self.imbal_price_up,
                        self.large_imbal_price_up,
                        self.imbal_price_down,
                        self.large_imbal_price_down,
                        parameters,
                    )
                    has_imbal_price = 1

                inflex_qty_ti = last_forecast_ti

                if parameters.market == MarketEnum.rr_activation:
                    upstream_bought_energy_ti = opt_load.rr_activated.get_value(time)
                elif parameters.market == MarketEnum.mfrr_activation:
                    upstream_bought_energy_ti = opt_load.mfrr_activated.get_value(time)
                else:
                    upstream_bought_energy_ti = opt_load.total_id_cleared_quantity.get_value(
                        time
                    ) + opt_load.da_cleared_quantity.get_value(time)

                optimal_dispatch_ti = min(inflex_qty_ti, upstream_bought_energy_ti)
                residual_energy_ti += upstream_bought_energy_ti - optimal_dispatch_ti
                self.optimal_dispatch_ndl[opt_load.name][time] = optimal_dispatch_ti

                i_ndload += 1

            # --- dispatchable loads ---
            for opt_load in dl:
                if idx == 0:
                    po_loadj = POLoad(opt_load.name)
                    po_loadj.fill_model(opt_load, parameters, optimisation_model)
                    self.load[opt_load.name] = po_loadj

                if has_imbal_price == 0:
                    # get da_price (first equipment in list set the da_price)
                    estimate_imbalance_prices(
                        time,
                        portfolio_object,
                        opt_load.node.market_area,
                        opt_load.node.control_block,
                        self.imbal_price_up,
                        self.large_imbal_price_up,
                        self.imbal_price_down,
                        self.large_imbal_price_down,
                        parameters,
                    )
                    has_imbal_price = 1

                # compute residual energy
                if parameters.market == MarketEnum.rr_activation:
                    upstream_bought_energy_ti = opt_load.rr_activated.get_value(time)
                elif parameters.market == MarketEnum.mfrr_activation:
                    upstream_bought_energy_ti = opt_load.mfrr_activated.get_value(time)
                else:
                    upstream_bought_energy_ti = opt_load.total_id_cleared_quantity.get_value(
                        time
                    ) + opt_load.da_cleared_quantity.get_value(time)

                residual_energy_ti += upstream_bought_energy_ti

                # compute reserve
                (
                    reserve_up_ti,
                    reserve_down_ti,
                    automated_reserve_up_ti,
                    automated_reserve_down_ti,
                    max_power_ti,
                ) = self._get_reserve(
                    opt_load,
                    reserve_up_ti,
                    reserve_down_ti,
                    automated_reserve_up_ti,
                    automated_reserve_down_ti,
                    max_power_ti,
                    time,
                    parameters,
                )

                # get max power
                if idx == 0:
                    max_energy_tot = max_energy_tot + abs(po_loadj.maximum_power[time])

            # --- wind ---
            for opt_wind in wind:
                # get last forecast
                if idx == 0:
                    po_windj = POWind(opt_wind.name)
                    po_windj.init_variables(opt_wind, parameters, optimisation_model)
                    self.wind[opt_wind.name] = po_windj

                if has_imbal_price == 0:
                    # get da_price (first equipment in list set the da_price)
                    estimate_imbalance_prices(
                        time,
                        portfolio_object,
                        opt_wind.node.market_area,
                        opt_wind.node.control_block,
                        self.imbal_price_up,
                        self.large_imbal_price_up,
                        self.imbal_price_down,
                        self.large_imbal_price_down,
                        parameters,
                    )
                    has_imbal_price = 1

                # compute residual energy
                if parameters.market == MarketEnum.rr_activation:
                    upstream_sold_energy_ti = opt_wind.rr_activated.get_value(time)
                elif parameters.market == MarketEnum.mfrr_activation:
                    upstream_sold_energy_ti = opt_wind.mfrr_activated.get_value(time)
                else:
                    upstream_sold_energy_ti = opt_wind.total_id_cleared_quantity.get_value(
                        time
                    ) + opt_wind.da_cleared_quantity.get_value(time)

                residual_energy_ti += upstream_sold_energy_ti

                # compute reserve
                (
                    reserve_up_ti,
                    reserve_down_ti,
                    automated_reserve_up_ti,
                    automated_reserve_down_ti,
                    max_power_ti,
                ) = self._get_reserve(
                    opt_wind,
                    reserve_up_ti,
                    reserve_down_ti,
                    automated_reserve_up_ti,
                    automated_reserve_down_ti,
                    max_power_ti,
                    time,
                    parameters,
                )

                # get max power
                if idx == 0:
                    max_energy_tot = max_energy_tot + po_windj.maximum_power[time]

            # --- photovoltaic ---
            for opt_pv in pv:
                # get last forecast
                if idx == 0:
                    po_pvj = POPV(opt_pv.name)
                    po_pvj.init_variables(opt_pv, parameters, optimisation_model)
                    self.pv[opt_pv.name] = po_pvj

                if has_imbal_price == 0:
                    # get da_price (first equipment in list set the da_price)
                    estimate_imbalance_prices(
                        time,
                        portfolio_object,
                        opt_pv.node.market_area,
                        opt_pv.node.control_block,
                        self.imbal_price_up,
                        self.large_imbal_price_up,
                        self.imbal_price_down,
                        self.large_imbal_price_down,
                        parameters,
                    )
                    has_imbal_price = 1

                # compute residual energy
                if parameters.market == MarketEnum.rr_activation:
                    upstream_sold_energy_ti = opt_pv.rr_activated.get_value(time)
                elif parameters.market == MarketEnum.mfrr_activation:
                    upstream_sold_energy_ti = opt_pv.mfrr_activated.get_value(time)
                else:
                    upstream_sold_energy_ti = opt_pv.total_id_cleared_quantity.get_value(
                        time
                    ) + opt_pv.da_cleared_quantity.get_value(time)

                residual_energy_ti += upstream_sold_energy_ti

                # compute reserve
                (
                    reserve_up_ti,
                    reserve_down_ti,
                    automated_reserve_up_ti,
                    automated_reserve_down_ti,
                    max_power_ti,
                ) = self._get_reserve(
                    opt_pv,
                    reserve_up_ti,
                    reserve_down_ti,
                    automated_reserve_up_ti,
                    automated_reserve_down_ti,
                    max_power_ti,
                    time,
                    parameters,
                )

                # get max power
                if idx == 0:
                    max_energy_tot = max_energy_tot + po_pvj.maximum_power[time]

            # --- thermic ---
            for opt_index, opt_thermic in enumerate(thermics):
                if idx == 0:
                    if parameters.debug:
                        API.io.trace.log("Debug thermic equipments match: ")
                        API.io.trace.log(f"{opt_thermic.name} = th_{opt_index}")

                    po_dtj = POThermic(opt_thermic.name, opt_index)
                    po_dtj.fill_model(opt_thermic, parameters, optimisation_model)
                    self.thermics[opt_thermic.name] = po_dtj
                if has_imbal_price == 0:
                    estimate_imbalance_prices(
                        time,
                        portfolio_object,
                        opt_thermic.node.market_area,
                        opt_thermic.node.control_block,
                        self.imbal_price_up,
                        self.large_imbal_price_up,
                        self.imbal_price_down,
                        self.large_imbal_price_down,
                        parameters,
                    )
                    has_imbal_price = 1

                if parameters.market == MarketEnum.rr_activation:
                    upstream_sold_energy_ti = opt_thermic.rr_activated.get_value(time)
                elif parameters.market == MarketEnum.mfrr_activation:
                    upstream_sold_energy_ti = opt_thermic.mfrr_activated.get_value(time)
                else:
                    upstream_sold_energy_ti = opt_thermic.total_id_cleared_quantity.get_value(
                        time
                    ) + opt_thermic.da_cleared_quantity.get_value(time)

                residual_energy_ti += upstream_sold_energy_ti

                # compute reserve
                (
                    reserve_up_ti,
                    reserve_down_ti,
                    automated_reserve_up_ti,
                    automated_reserve_down_ti,
                    max_power_ti,
                ) = self._get_reserve(
                    opt_thermic,
                    reserve_up_ti,
                    reserve_down_ti,
                    automated_reserve_up_ti,
                    automated_reserve_down_ti,
                    max_power_ti,
                    time,
                    parameters,
                )

                # get max power
                if idx == 0:
                    max_energy_tot = max_energy_tot + po_dtj.maximum_power[time]

            # --- hydraulic ---
            for opt_hydrau in hydraulics:
                if idx == 0:
                    po_dhj = POHydraulic(opt_hydrau, opt_hydrau.name)
                    po_dhj.fill_model(opt_hydrau, parameters, optimisation_model)
                    self.hydraulics[opt_hydrau.name] = po_dhj
                if has_imbal_price == 0:
                    estimate_imbalance_prices(
                        time,
                        portfolio_object,
                        opt_hydrau.node.market_area,
                        opt_hydrau.node.control_block,
                        self.imbal_price_up,
                        self.large_imbal_price_up,
                        self.imbal_price_down,
                        self.large_imbal_price_down,
                        parameters,
                    )
                    has_imbal_price = 1

                if parameters.market == MarketEnum.rr_activation:
                    upstream_sold_energy_ti = opt_hydrau.rr_activated.get_value(time)
                elif parameters.market == MarketEnum.mfrr_activation:
                    upstream_sold_energy_ti = opt_hydrau.mfrr_activated.get_value(time)
                else:
                    upstream_sold_energy_ti = opt_hydrau.total_id_cleared_quantity.get_value(
                        time
                    ) + opt_hydrau.da_cleared_quantity.get_value(time)

                residual_energy_ti += upstream_sold_energy_ti

                (
                    reserve_up_ti,
                    reserve_down_ti,
                    automated_reserve_up_ti,
                    automated_reserve_down_ti,
                    max_power_ti,
                ) = self._get_reserve(
                    opt_hydrau,
                    reserve_up_ti,
                    reserve_down_ti,
                    automated_reserve_up_ti,
                    automated_reserve_down_ti,
                    max_power_ti,
                    time,
                    parameters,
                )
                # get max power
                if idx == 0:
                    max_energy_tot = max_energy_tot + po_dhj.maximum_power[time]

            # --- storage ---
            for opt_storage in storage:
                if idx == 0:
                    po_dsj = POStorage(opt_storage.name, parameters)
                    po_dsj.init_variables(opt_storage, parameters, optimisation_model)
                    self.storage[opt_storage.name] = po_dsj

                if has_imbal_price == 0:
                    # get da_price (first equipment in list set the da_price)
                    estimate_imbalance_prices(
                        time,
                        portfolio_object,
                        opt_storage.node.market_area,
                        opt_storage.node.control_block,
                        self.imbal_price_up,
                        self.large_imbal_price_up,
                        self.imbal_price_down,
                        self.large_imbal_price_down,
                        parameters,
                    )
                    has_imbal_price = 1

                # compute residual energy
                if parameters.market == MarketEnum.rr_activation:
                    upstream_sold_energy_ti = opt_storage.rr_activated.get_value(time)
                elif parameters.market == MarketEnum.mfrr_activation:
                    upstream_sold_energy_ti = opt_storage.mfrr_activated.get_value(time)
                else:
                    upstream_sold_energy_ti = opt_storage.total_id_cleared_quantity.get_value(
                        time
                    ) + opt_storage.da_cleared_quantity.get_value(time)

                residual_energy_ti += upstream_sold_energy_ti

                (
                    reserve_up_ti,
                    reserve_down_ti,
                    automated_reserve_up_ti,
                    automated_reserve_down_ti,
                    max_power_ti,
                ) = self._get_reserve(
                    opt_storage,
                    reserve_up_ti,
                    reserve_down_ti,
                    automated_reserve_up_ti,
                    automated_reserve_down_ti,
                    max_power_ti,
                    time,
                    parameters,
                )
                # get max power
                if idx == 0:
                    max_energy_tot = max_energy_tot + po_dsj.maximum_power[time]

            # save values at ti
            self.residual_energy[time] = residual_energy_ti

            self.reserve_up[time] = reserve_up_ti
            self.reserve_down[time] = reserve_down_ti
            self.automated_reserve_up[time] = automated_reserve_up_ti
            self.automated_reserve_down[time] = automated_reserve_down_ti
            self.max_power[time] = max_power_ti

            # should be min in specifications but in tests it is max
            self.max_overall_imbal[time] = max(residual_energy_ti, parameters.max_overall_imbalance)

        # compute imbal limits and compute reserve
        self.small_imbal_up_limit = max_energy_tot * parameters.small_imbalance_size
        self.small_imbal_down_limit = self.small_imbal_up_limit

        for idx, time in enumerate(time_index):
            # create variables at ti
            self.small_imbal_up[time] = optimisation_model.add_continuous_variable(
                name=f"{self.name}_small_imbal_up{idx}",
                lower_bound=0,
                upper_bound=self.small_imbal_up_limit,
            )
            self.large_imbal_up[time] = optimisation_model.add_continuous_variable(
                name=f"{self.name}_large_imbal_up{idx}",
                lower_bound=0,
                upper_bound=self.max_overall_imbal[time],
            )
            self.small_imbal_down[time] = optimisation_model.add_continuous_variable(
                name=f"{self.name}_small_imbal_down{idx}",
                lower_bound=0,
                upper_bound=self.small_imbal_down_limit,
            )
            self.large_imbal_down[time] = optimisation_model.add_continuous_variable(
                name=f"{self.name}_large_imbal_down{idx}",
                lower_bound=0,
                upper_bound=self.max_overall_imbal[time],
            )

            self.contracted_difference_up[time] = optimisation_model.add_continuous_variable(
                name=f"contracted_diff_up_e_{self.name}_at_{idx}",
                lower_bound=0,
                upper_bound=self.max_power[time],
            )
            self.contracted_difference_down[time] = optimisation_model.add_continuous_variable(
                name=f"contracted_diff_down_e_{self.name}_at_{idx}",
                lower_bound=0,
                upper_bound=self.max_power[time],
            )
            self.automated_contracted_difference_up[time] = optimisation_model.add_continuous_variable(
                name=f"auto_contracted_diff_up_e_{self.name}_at_{idx}",
                lower_bound=0,
                upper_bound=self.max_power[time],
            )
            self.automated_contracted_difference_down[time] = optimisation_model.add_continuous_variable(
                name=f"auto_contracted_diff_down_e_{self.name}_at_{idx}",
                lower_bound=0,
                upper_bound=self.max_power[time],
            )

    def _get_reserve(
        self,
        opt,
        reserve_up_ti,
        reserve_down_ti,
        automated_reserve_up_ti,
        automated_reserve_down_ti,
        max_power_ti,
        time: DateTime,
        parameters: PortfolioOptimisationParameters,
    ):
        maximum_afrr = opt.maximum_afrr
        maximum_fcr = opt.maximum_fcr

        if isinstance(opt, Wind | Solar | Load | OtherNonDispatchable):
            max_power_ti += abs(
                opt.maximum_power_forecast.get_forecast(parameters.execution_date, time, time).get_value(
                    time,
                )
            )

        else:
            max_power_ti += opt.maximum_power.abs().get_value(time)

        afrr_up = opt.afrr_up_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
        afrr_down = opt.afrr_down_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
        mfrr_up = opt.mfrr_up_procured.get_forecast(parameters.execution_date, time, time).get_value(time)

        mfrr_down = opt.mfrr_down_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
        rr_up = opt.rr_up_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
        rr_down = opt.rr_down_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
        fcr_up = opt.fcr_up_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
        fcr_down = opt.fcr_down_procured.get_forecast(parameters.execution_date, time, time).get_value(time)

        reserve_up_ti += rr_up + mfrr_up
        reserve_down_ti += rr_down + mfrr_down
        automated_reserve_up_ti += min(afrr_up, maximum_afrr) + min(fcr_up, maximum_fcr)
        automated_reserve_down_ti += min(afrr_down, maximum_afrr) + min(fcr_down, maximum_fcr)

        return (
            reserve_up_ti,
            reserve_down_ti,
            automated_reserve_up_ti,
            automated_reserve_down_ti,
            max_power_ti,
        )
