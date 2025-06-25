from pendulum import DateTime

from atlas.enum import StorageType
from atlas.models.equipment.equipment import Equipment
from atlas.models.equipment.hydro import Hydro
from atlas.models.equipment.load import Load
from atlas.models.equipment.solar import Solar
from atlas.models.equipment.storage import Storage
from atlas.models.equipment.wind import Wind
from atlas.models.portfolio import Portfolio
from atlas.modules.portfolio_optimisation.parameters import MarketEnum, PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.get_fragment_price import get_fragment_price_and_size
from atlas.modules.portfolio_optimisation.utils.imbalance_price import estimate_imbalance_prices
from atlas.solver.solver_interface import OptimisationModel


def add_variables_hydro(
    time: DateTime,
    equipments: list[Hydro],
    model: OptimisationModel,
    parameters: PortfolioOptimisationParameters,
):
    for obj in equipments:
        if len(
            (
                obj.stored_energy.get_forecast(
                    parameters.execution_date,
                    parameters.start_date - parameters.timestep,
                    parameters.end_date,
                )
            )
            == 0
        ):
            obj.initial_level = obj.initial_level.filter(
                [parameters.start_date - parameters.timestep, parameters.end_date]
            )
        else:
            if (
                obj.stored_energy.get_forecast(
                    parameters.execution_date,
                    parameters.start_date - parameters.timestep,
                    parameters.end_date,
                ).first_date()
                < parameters.start_date
            ):
                obj.initial_level = obj.stored_energy.get_forecast(
                    parameters.execution_date,
                    parameters.start_date - parameters.timestep,
                    parameters.end_date,
                )

            else:
                obj.initial_level = obj.initial_level.filter(
                    [parameters.start_date - parameters.timestep, parameters.end_date]
                )

        for _, time in enumerate(parameters.hydraulic_op_times):
            min_power = obj.minimum_power.get_value(time)
            max_power = obj.maximum_power.get_value(time)
            max_energy = obj.maximum_energy.get_value(time)

            model.add_continuous_variable(
                name=f"{obj.name}_power_level_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"{obj.name}_stored_energy_{time}",
                lower_bound=0,
                upper_bound=max_energy,
            )
            get_fragment_price_and_size(obj, time, parameters, model)

            maximum_automated = obj.maximum_afrr + obj.maximum_fcr

            # Optimisation Variables related to reserves
            model.add_continuous_variable(
                name=f"reserves_up_e_{obj.name}_at_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"reserves_down_e_{obj.name}_at_{time}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"unprovided_reserves_up_e_{obj.name}_at_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"unprovided_reserves_down_e_{obj.name}_at_{time}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"relaxed_reservese_{obj.name}_at_{time}",
                lower_bound=min_power,
                upper_bound=0,
            )
            model.add_continuous_variable(
                name=f"automated_res_up_e_{obj.name}_at_{time}",
                lower_bound=0,
                upper_bound=maximum_automated,
            )
            model.add_continuous_variable(
                name=f"automated_res_down_e_{obj.name}_at_{time}",
                lower_bound=0,
                upper_bound=maximum_automated,
            )
            model.add_continuous_variable(
                name=f"contracted_diff_up_e_{obj.name}_at_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"contracted_diff_down_e_{obj.name}_at_{time}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"automated_contracted_diff_up_e_{obj.name}_at_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"automated_contracted_diff_down_e_{obj.name}_at_{time}",
                lower_bound=min_power,
                upper_bound=max_power,
            )


def add_variables_solar_wind(
    time: DateTime,
    equipments: list[Solar | Wind],
    model: OptimisationModel,
    parameters: PortfolioOptimisationParameters,
):
    for obj in equipments:
        for _, time in enumerate(parameters.target_times):
            max_power = obj.maximum_power_forecast.get_forecast(parameters.execution_date, time, time).get_value(time)

            min_power = (1 - obj.maximum_curtailment_ratio.get_value(time)) * max_power

            model.add_continuous_variable(
                name=f"{obj.name}_power_level_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )

            maximum_automated = obj.maximum_afrr + obj.maximum_fcr

            model.add_continuous_variable(
                name=f"reserves_up_e_{obj.name}_at_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"reserves_down_e_{obj.name}_at_{time}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"unprovided_reserves_up_e_{obj.name}_at_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"unprovided_reserves_down_e_{obj.name}_at_{time}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"automated_reserves_up_e_{obj.name}_at_{time}",
                lower_bound=0,
                upper_bound=maximum_automated,
            )
            model.add_continuous_variable(
                name=f"automated_reserves_down_e_{obj.name}_at_{time}",
                lower_bound=0,
                upper_bound=maximum_automated,
            )
            model.add_continuous_variable(
                name=f"contracted_diff_up_e_{obj.name}_at_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"contracted_diff_down_e_{obj.name}_at_{time}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"automated_contracted_diff_up_e_{obj.name}_at_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"automated_contracted_diff_down_e_{obj.name}_at_{time}",
                lower_bound=min_power,
                upper_bound=max_power,
            )


def add_variables_storage(
    time: DateTime,
    equipments: list[Storage],
    model: OptimisationModel,
    parameters: PortfolioOptimisationParameters,
):
    MAPPING_STORAGE_TYPE_OPTIMISATION_TIMES = {
        StorageType.BATTERY: {
            "op_time_frame": parameters.battery_op_times,
            "fragment": parameters.battery_number_of_fragments,
        },
        StorageType.PUMPED_HYDRAULIC_STORAGE: {
            "op_time_frame": parameters.phs_op_times,
            "fragment": parameters.pumped_hydraulic_number_of_fragments,
        },
        StorageType.ELECTRIC_VEHICLE: {
            "op_time_frame": parameters.ev_op_times,
            "fragment": parameters.electric_vehicle_number_of_fragments,
        },
    }

    for obj in equipments:
        if (
            len(
                obj.stored_energy.get_forecast(
                    parameters.execution_date,
                    parameters.init_battery_time.subtract(days=2),
                    parameters.init_battery_time,
                )
            )
            == 0
        ):
            obj.initial_stock = obj.maximum_energy.get_value(
                (parameters.start_date - parameters.timestep) * obj.storage_initial_level,
            )

        else:
            obj.initial_stock = (
                obj.stored_energy.get_forecast(
                    parameters.execution_date,
                    parameters.init_battery_time,
                    parameters.init_battery_time,
                )
                .dataframe.select("time")
                .to_series()
                .to_list()[0]
            )

        op_time_frame = MAPPING_STORAGE_TYPE_OPTIMISATION_TIMES[obj.storage_type]["op_time_frame"]
        for _, time in enumerate(op_time_frame):
            max_power = obj.maximum_power.get_value(time)
            if obj.minimum_power or len(obj.minimum_power) == 0:
                min_power = -max_power
            else:
                min_power = obj.minimum_power.get_value(time)

            maximum_energy = obj.maximum_energy.get_value(time)
            min_state_of_charge = obj.minimum_state_of_charge.get_value(time)

            model.add_continuous_variable(
                name=f"{obj.name}_power_level_sell_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )

            model.add_continuous_variable(
                name=f"{obj.name}_power_level_buy_{time}",
                lower_bound=min_power,
                upper_bound=0,
            )

            model.add_boolean_variable(
                name=f"{obj.name}_is_sell_{time}",
            )

            model.add_continuous_variable(
                name=f"{obj.name}_stored_energy_{time}",
                lower_bound=min_state_of_charge * maximum_energy,
                upper_bound=maximum_energy,
            )

            maximum_automated = obj.maximum_afrr + obj.maximum_fcr

            nbr_fragment = MAPPING_STORAGE_TYPE_OPTIMISATION_TIMES[obj.storage_type]["fragment"]

            for n in range(0, nbr_fragment):
                model.add_continuous_variable(
                    name=f"{obj.name}_power_level_sell_n_{n}_time_{time}",
                    lower_bound=0,
                    upper_bound=max_power,
                )
                model.add_continuous_variable(
                    name=f"{obj.name}_power_level_buy_n_{n}_time_{time}",
                    lower_bound=min_power,
                    upper_bound=0,
                )

            model.add_continuous_variable(
                name=f"reserves_up_e_{obj.name}_at_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"reserves_down_e_{obj.name}_at_{time}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"unprovided_reserves_up_e_{obj.name}_at_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"unprovided_reserves_down_e_{obj.name}_at_{time}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            model.add_continuous_variable(
                name=f"automated_reserves_up_e_{obj.name}_at_{time}",
                lower_bound=0,
                upper_bound=maximum_automated,
            )
            model.add_continuous_variable(
                name=f"automated_reserves_down_e_{obj.name}_at_{time}",
                lower_bound=-maximum_automated,
                upper_bound=maximum_automated,
            )


def add_variables_load(
    time: DateTime,
    equipments: list[Load],
    model: OptimisationModel,
    parameters: PortfolioOptimisationParameters,
):
    for obj in equipments:
        for _, time in enumerate(parameters.target_times):
            max_power = obj.maximum_power_forecast.get_forecast(parameters.execution_date, time, time).get_value(time)

            model.add_continuous_variable(
                f"{obj.name}_power_level_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )


def add_variables_portfolio(
    portfolio: Portfolio,
    equipments: dict[str, list[type[Equipment]]],
    times: list[DateTime],
    parameters: PortfolioOptimisationParameters,
):
    max_energy_tot = 0

    global_series_ndp = {}
    global_series_ndl = {}

    for idx, time in enumerate(times):
        residual_energy_ti = 0
        reserve_up_ti = 0
        reserve_down_ti = 0
        automated_reserve_up_ti = 0
        automated_reserve_down_ti = 0
        max_power_ti = 0

        if time in parameters.target_times:
            if parameters.use_forecast:
                if parameters.market == MarketEnum.dayahead:
                    self.price_forecast[time] = portfolio.market_area.price_forecast_medium.get_value(time)
                elif parameters.market == MarketEnum.intraday:
                    self.price_forecast[time] = portfolio.market_area.id_price_forecast.get_forecast(
                        parameters.execution_date, time, time
                    ).get_value(time)
            else:
                if parameters.market == MarketEnum.dayahead:
                    self.price_forecast[time] = portfolio.market_area.da_price.get_value(time)
                elif parameters.market == MarketEnum.intraday:
                    self.price_forecast[time] = portfolio.market_area.id_price.get_forecast(
                        parameters.execution_date, time, time
                    ).get_value(time)
                elif parameters.market == MarketEnum.rr_activation:
                    self.price_forecast[time] = portfolio.market_area.rr_activation_price.get_value(time)
                elif parameters.market == MarketEnum.mfrr_activation:
                    self.price_forecast[time] = portfolio.market_area.mfrr_activation_price.get_value(time)
        else:
            price = portfolio.market_area.price_forecast_medium.get_forecast(
                parameters.execution_date, time, time
            ).get_value(time)  # Need some change
            self.price_forecast[time] = price

        # --- non_dispatchable productions ---
        has_imbal_price = 0
        for obj in equipments["non_dispatchable_production"]:
            # Initialization
            if idx == 0:
                global_series_ndp[obj] = obj.maximum_power_forecast.get_forecast(
                    parameters.execution_date, parameters.start_date, parameters.end_date
                )
                self.optimal_dispatch_ndp[obj.name] = {}
            last_forecast_ti = 0

            if global_series_ndp[obj] is not None:
                last_forecast_ti = global_series_ndp[obj].get_value(time)
            if has_imbal_price == 0:
                # get da_price (first equipment in list set the da_price)
                estimate_imbalance_prices(
                    time,
                    obj.node.market_area,
                    obj.node.control_block,
                    self.imbal_price_up,
                    self.large_imbal_price_up,
                    self.imbal_price_down,
                    self.large_imbal_price_down,
                    parameters,
                )
                has_imbal_price = 1

            if parameters.market == MarketEnum.rr_activation:
                upstream_sold_energy_ti = obj.rr_activated.get_value(time)
            elif parameters.market == MarketEnum.mfrr_activation:
                upstream_sold_energy_ti = obj.mfrr_activated.get_value(time)
            else:
                upstream_sold_energy_ti = obj.total_id_cleared_quantity.get_value(
                    time
                ) + obj.da_cleared_quantity.get_value(time)

            optimal_dispatch_ti = min(last_forecast_ti, upstream_sold_energy_ti)
            residual_energy_ti += upstream_sold_energy_ti - optimal_dispatch_ti

            # save optimal dispatch
            self.optimal_dispatch_ndp[obj.name][time] = optimal_dispatch_ti

        # --- non dispatchable loads ---
        for obj in equipments["non_dispacthable_load"]:
            # Initialization
            if idx == 0:
                global_series_ndl[obj] = obj.maximum_power_forecast.get_forecast(
                    parameters.execution_date, parameters.start_date, parameters.end_date
                )
                self.optimal_dispatch_ndl[obj.name] = {}

            last_forecast_ti = 0
            if global_series_ndl[obj] is not None:
                last_forecast_ti = global_series_ndl[obj].get_value(time)
            if has_imbal_price == 0:
                # get da_price (first equipment in list set the da_price)
                estimate_imbalance_prices(
                    time,
                    obj.node.market_area,
                    obj.node.control_block,
                    self.imbal_price_up,
                    self.large_imbal_price_up,
                    self.imbal_price_down,
                    self.large_imbal_price_down,
                    parameters,
                )
                has_imbal_price = 1

            inflex_qty_ti = last_forecast_ti

            if parameters.market == MarketEnum.rr_activation:
                upstream_bought_energy_ti = obj.rr_activated.get_value(time)
            elif parameters.market == MarketEnum.mfrr_activation:
                upstream_bought_energy_ti = obj.mfrr_activated.get_value(time)
            else:
                upstream_bought_energy_ti = obj.total_id_cleared_quantity.get_value(
                    time
                ) + obj.da_cleared_quantity.get_value(time)

            optimal_dispatch_ti = min(inflex_qty_ti, upstream_bought_energy_ti)
            residual_energy_ti += upstream_bought_energy_ti - optimal_dispatch_ti
            self.optimal_dispatch_ndl[obj.name][time] = optimal_dispatch_ti

        # --- dispatchable loads ---
        for obj in equipments["dispatchable_load"]:
            if idx == 0:
                po_loadj = POLoad(obj.name)
                po_loadj.fill_model(obj, parameters, model)
                self.load[obj.name] = po_loadj

            if has_imbal_price == 0:
                # get da_price (first equipment in list set the da_price)
                estimate_imbalance_prices(
                    time,
                    obj.node.market_area,
                    obj.node.control_block,
                    self.imbal_price_up,
                    self.large_imbal_price_up,
                    self.imbal_price_down,
                    self.large_imbal_price_down,
                    parameters,
                )
                has_imbal_price = 1

            # compute residual energy
            if parameters.market == MarketEnum.rr_activation:
                upstream_bought_energy_ti = obj.rr_activated.get_value(time)
            elif parameters.market == MarketEnum.mfrr_activation:
                upstream_bought_energy_ti = obj.mfrr_activated.get_value(time)
            else:
                upstream_bought_energy_ti = obj.total_id_cleared_quantity.get_value(
                    time
                ) + obj.da_cleared_quantity.get_value(time)

            residual_energy_ti += upstream_bought_energy_ti

            # compute reserve
            (
                reserve_up_ti,
                reserve_down_ti,
                automated_reserve_up_ti,
                automated_reserve_down_ti,
                max_power_ti,
            ) = self._get_reserve(
                obj,
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
        for obj in wind:
            # get last forecast
            if idx == 0:
                po_windj = POWind(obj.name)
                po_windj.fill_model(obj, parameters, model)
                self.wind[obj.name] = po_windj

            if has_imbal_price == 0:
                # get da_price (first equipment in list set the da_price)
                estimate_imbalance_prices(
                    time,
                    obj.node.market_area,
                    obj.node.control_block,
                    self.imbal_price_up,
                    self.large_imbal_price_up,
                    self.imbal_price_down,
                    self.large_imbal_price_down,
                    parameters,
                )
                has_imbal_price = 1

            # compute residual energy
            if parameters.market == MarketEnum.rr_activation:
                upstream_sold_energy_ti = obj.rr_activated.get_value(time)
            elif parameters.market == MarketEnum.mfrr_activation:
                upstream_sold_energy_ti = obj.mfrr_activated.get_value(time)
            else:
                upstream_sold_energy_ti = obj.total_id_cleared_quantity.get_value(
                    time
                ) + obj.da_cleared_quantity.get_value(time)

            residual_energy_ti += upstream_sold_energy_ti

            # compute reserve
            (
                reserve_up_ti,
                reserve_down_ti,
                automated_reserve_up_ti,
                automated_reserve_down_ti,
                max_power_ti,
            ) = self._get_reserve(
                obj,
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
        for obj in solar:
            # get last forecast
            if idx == 0:
                po_pvj = POPV(obj.name)
                po_pvj.fill_model(obj, parameters, model)
                self.solar[obj.name] = po_pvj

            if has_imbal_price == 0:
                # get da_price (first equipment in list set the da_price)
                estimate_imbalance_prices(
                    time,
                    obj.node.market_area,
                    obj.node.control_block,
                    self.imbal_price_up,
                    self.large_imbal_price_up,
                    self.imbal_price_down,
                    self.large_imbal_price_down,
                    parameters,
                )
                has_imbal_price = 1

            # compute residual energy
            if parameters.market == MarketEnum.rr_activation:
                upstream_sold_energy_ti = obj.rr_activated.get_value(time)
            elif parameters.market == MarketEnum.mfrr_activation:
                upstream_sold_energy_ti = obj.mfrr_activated.get_value(time)
            else:
                upstream_sold_energy_ti = obj.total_id_cleared_quantity.get_value(
                    time
                ) + obj.da_cleared_quantity.get_value(time)

            residual_energy_ti += upstream_sold_energy_ti

            # compute reserve
            (
                reserve_up_ti,
                reserve_down_ti,
                automated_reserve_up_ti,
                automated_reserve_down_ti,
                max_power_ti,
            ) = self._get_reserve(
                obj,
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
        for opt_index, opt_thermic in enumerate(thermal):
            if idx == 0:
                po_dtj = POThermic(opt_thermic.name, opt_index)
                po_dtj.fill_model(opt_thermic, parameters, model)
                self.thermal[opt_thermic.name] = po_dtj
            if has_imbal_price == 0:
                estimate_imbalance_prices(
                    time,
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
        for obj in hydro:
            if idx == 0:
                po_dhj = POHydraulic(obj, obj.name)
                po_dhj.fill_model(obj, parameters, model)
                self.hydro[obj.name] = po_dhj
            if has_imbal_price == 0:
                estimate_imbalance_prices(
                    time,
                    obj.node.market_area,
                    obj.node.control_block,
                    self.imbal_price_up,
                    self.large_imbal_price_up,
                    self.imbal_price_down,
                    self.large_imbal_price_down,
                    parameters,
                )
                has_imbal_price = 1

            if parameters.market == MarketEnum.rr_activation:
                upstream_sold_energy_ti = obj.rr_activated.get_value(time)
            elif parameters.market == MarketEnum.mfrr_activation:
                upstream_sold_energy_ti = obj.mfrr_activated.get_value(time)
            else:
                upstream_sold_energy_ti = obj.total_id_cleared_quantity.get_value(
                    time
                ) + obj.da_cleared_quantity.get_value(time)

            residual_energy_ti += upstream_sold_energy_ti

            (
                reserve_up_ti,
                reserve_down_ti,
                automated_reserve_up_ti,
                automated_reserve_down_ti,
                max_power_ti,
            ) = self._get_reserve(
                obj,
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
        for obj in storage:
            if idx == 0:
                po_dsj = POStorage(obj.name, parameters)
                po_dsj.fill_model(obj, parameters, model)
                self.storage[obj.name] = po_dsj

            if has_imbal_price == 0:
                # get da_price (first equipment in list set the da_price)
                estimate_imbalance_prices(
                    time,
                    obj.node.market_area,
                    obj.node.control_block,
                    self.imbal_price_up,
                    self.large_imbal_price_up,
                    self.imbal_price_down,
                    self.large_imbal_price_down,
                    parameters,
                )
                has_imbal_price = 1

            # compute residual energy
            if parameters.market == MarketEnum.rr_activation:
                upstream_sold_energy_ti = obj.rr_activated.get_value(time)
            elif parameters.market == MarketEnum.mfrr_activation:
                upstream_sold_energy_ti = obj.mfrr_activated.get_value(time)
            else:
                upstream_sold_energy_ti = obj.total_id_cleared_quantity.get_value(
                    time
                ) + obj.da_cleared_quantity.get_value(time)

            residual_energy_ti += upstream_sold_energy_ti

            (
                reserve_up_ti,
                reserve_down_ti,
                automated_reserve_up_ti,
                automated_reserve_down_ti,
                max_power_ti,
            ) = self._get_reserve(
                obj,
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

    for _, time in enumerate(idx):
        # create variables at ti
        self.small_imbal_up[time] = model.add_continuous_variable(
            name=f"{self.name}_small_imbal_up_{time}",
            lower_bound=0,
            upper_bound=self.small_imbal_up_limit,
        )
        self.large_imbal_up[time] = model.add_continuous_variable(
            name=f"{self.name}_large_imbal_up_{time}",
            lower_bound=0,
            upper_bound=self.max_overall_imbal[time],
        )
        self.small_imbal_down[time] = model.add_continuous_variable(
            name=f"{self.name}_small_imbal_down_{time}",
            lower_bound=0,
            upper_bound=self.small_imbal_down_limit,
        )
        self.large_imbal_down[time] = model.add_continuous_variable(
            name=f"{self.name}_large_imbal_down_{time}",
            lower_bound=0,
            upper_bound=self.max_overall_imbal[time],
        )

        self.contracted_difference_up[time] = model.add_continuous_variable(
            name=f"contracted_diff_up_e_{self.name}_at__{time}",
            lower_bound=0,
            upper_bound=self.max_power[time],
        )
        self.contracted_difference_down[time] = model.add_continuous_variable(
            name=f"contracted_diff_down_e_{self.name}_at__{time}",
            lower_bound=0,
            upper_bound=self.max_power[time],
        )
        self.automated_contracted_difference_up[time] = model.add_continuous_variable(
            name=f"auto_contracted_diff_up_e_{self.name}_at__{time}",
            lower_bound=0,
            upper_bound=self.max_power[time],
        )
        self.automated_contracted_difference_down[time] = model.add_continuous_variable(
            name=f"auto_contracted_diff_down_e_{self.name}_at__{time}",
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
