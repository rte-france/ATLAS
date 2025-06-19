import API

from atlas.enum import StorageType
from atlas.models.equipment.storage import Storage
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.solver.solver_interface import OptimisationModel


class POStorage:
    """
    This class is used to feed a POStorage from a storage equipment
    """

    def __init__(self, name, parameters):
        self.name = name
        self.storage_type: StorageType | None = None
        self.power_level_buy = {}
        self.power_level_sell = {}

        self.power_level_buy_n = {}
        self.power_level_sell_n = {}

        for n in range(
            0,
            max(
                parameters.ev_nb_fragments,
                parameters.battery_nb_fragments,
                parameters.phs_nb_fragments,
            ),
        ):
            self.power_level_buy_n[n] = {}
            self.power_level_sell_n[n] = {}

        self.stored_energy = {}
        self.usable_energy = {}

        self.is_sell = {}

        # parameters from optimate equipment to optimized memory
        self.last_time_t = 0
        self.variable_cost = 0
        self.startup_cost = 0
        self.initial_stock = 0
        self.charge_efficiency = 1
        self.discharge_efficiency = 1
        self.is_v2g = 0

        # self.afrr_max = 0
        self.maximum_power = {}
        self.minimum_power = {}
        self.da_cleared_quantity = {}
        self.displacement_energy = {}

        # reserve requirements
        self.afrr_up_procured = {}
        self.afrr_down_procured = {}
        self.mfrr_up_procured = {}
        self.mfrr_down_procured = {}
        self.rr_up_procured = {}
        self.rr_down_procured = {}
        self.fcr_up_procured = {}
        self.fcr_down_procured = {}
        self.reserves_up_procured = {}
        self.reserves_down_procured = {}

        self.feasible_automated_reserves_up_procured = {}
        self.feasible_automated_reserves_down_procured = {}
        self.automated_unsupplied_reserves = 0

        # reserve variables
        self.reserves_up = {}
        self.reserves_down = {}
        self.unprovided_reserves_up = {}
        self.unprovided_reserves_down = {}
        self.automated_reserves_up = {}
        self.automated_reserves_down = {}
        self.contracted_difference_up = {}
        self.contracted_difference_down = {}
        self.automated_contracted_difference_up = {}
        self.automated_contracted_difference_down = {}

        self.maximum_energy = {}
        self.minimum_state_of_charge = {}
        self.maximum_afrr = 0
        self.maximum_fcr = 0
        self.maximum_automated = 0

    def fill_model(
        self,
        storage_object: Storage,
        parameters: PortfolioOptimisationParameters,
        optimisation_model: OptimisationModel,
    ):
        # Retrieve the optimization time frame
        if storage_object.storage_type == "Battery":
            op_time_frame = parameters.battery_op_times
        elif storage_object.storage_type == "PumpedHydraulicStorage":
            op_time_frame = parameters.phs_op_times
        elif storage_object.storage_type == "ElectricVehicle":
            op_time_frame = parameters.ev_op_times

        # get data from optimate equipment
        self.variable_cost = storage_object.variable_cost.get_value(parameters.start_date)
        self.startup_cost = storage_object.startup_cost.get_value(parameters.start_date)

        self.maximum_afrr = storage_object.maximum_afrr
        self.maximum_fcr = storage_object.maximum_fcr

        # a affiner en fonction de stored energy
        self.storage_type = storage_object.storage_type

        # FC: hypothesis here, we check if the stored_energy matrix has values over the last 48 hours
        # If it is not the case, the equipment is assumed to be in initial state.
        # This hypothesis could be challenged, but is at least applied uniformly to all modules
        if (
            len(
                storage_object.stored_energy.get_forecast(
                    parameters.execution_date,
                    parameters.init_battery_time.subtract(days=-2),
                    parameters.init_battery_time,
                )
            )
            == 0
        ):
            self.initial_stock = storage_object.maximum_energy.get_value(
                (parameters.start_date - parameters.time_step) * storage_object.storage_initial_level,
            )

        else:
            self.initial_stock = storage_object.stored_energy.get_forecast(
                parameters.execution_date,
                parameters.init_battery_time,
                parameters.init_battery_time,
            )[0]

        if parameters.debug:
            msg = f"The initial energy storage level is : {self.initial_stock} MWh"
            API.io.trace.log(msg, API.io.log_type_info)

        self.is_v2g = storage_object.is_v2g
        self.charge_efficiency = storage_object.charge_efficiency
        self.discharge_efficiency = storage_object.discharge_efficiency

        for idx, time in enumerate(op_time_frame):
            max_power = storage_object.maximum_power.get_value(time)
            if storage_object.minimum_power.count == 0:
                min_power = -max_power
            else:
                min_power = storage_object.minimum_power.get_value(time)

            max_stock = storage_object.maximum_energy.get_value(time)
            min_soc = storage_object.minimum_state_of_charge.get_value(time)
            disp_en = storage_object.displacement_energy.get_value(time)

            afrr_up = storage_object.afrr_up_procured.get_forecast(parameters.execution_date, time, time).get_value(
                time
            )
            afrr_down = storage_object.afrr_down_procured.get_forecast(parameters.execution_date, time, time).get_value(
                time
            )
            mfrr_up = storage_object.mfrr_up_procured.get_forecast(parameters.execution_date, time, time).get_value(
                time
            )
            mfrr_down = storage_object.mfrr_down_procured.get_forecast(parameters.execution_date, time, time).get_value(
                time
            )
            rr_up = storage_object.rr_up_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
            rr_down = storage_object.rr_down_procured.get_forecast(parameters.execution_date, time, time).get_value(
                time
            )
            fcr_up = storage_object.fcr_up_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
            fcr_down = storage_object.fcr_down_procured.get_forecast(parameters.execution_date, time, time).get_value(
                time
            )

            self.maximum_power[time] = max_power
            self.minimum_power[time] = min_power

            if idx == 0:
                self.maximum_energy[time.add_minutes(-parameters.time_step)] = storage_object.maximum_energy.get_value(
                    time - parameters.time_step
                )

                self.minimum_state_of_charge[time - parameters.time_step] = (
                    storage_object.minimum_state_of_charge.get_value(time - parameters.time_step)
                )

                self.displacement_energy[time - parameters.time_step] = storage_object.displacement_energy.get_value(
                    time - parameters.time_step
                )

            self.maximum_energy[time] = max_stock
            self.minimum_state_of_charge[time] = min_soc
            self.displacement_energy[time] = disp_en

            self.afrr_up_procured[time] = afrr_up
            self.afrr_down_procured[time] = afrr_down
            self.mfrr_up_procured[time] = mfrr_up
            self.mfrr_down_procured[time] = mfrr_down
            self.rr_up_procured[time] = rr_up
            self.rr_down_procured[time] = rr_down
            self.fcr_up_procured[time] = fcr_up
            self.fcr_down_procured[time] = fcr_down

            # Create variables at time
            self.power_level_sell[time] = API.solver.new_op_variable(
                f"{self.name}_power_level_sell_{idx}",
                0,
                max_power,
                API.solver.op_category_real,
            )
            self.power_level_buy[time] = API.solver.new_op_variable(
                f"{self.name}_power_level_buy_{idx}",
                min_power,
                0,
                API.solver.op_category_real,
            )
            self.is_sell[time] = API.solver.new_op_variable(f"{self.name}_is_sell_{idx}", API.solver.op_category_binary)
            self.stored_energy[time] = API.solver.new_op_variable(
                f"{self.name}_stored_energy_{idx}",
                min_soc * max_stock,
                max_stock,
                API.solver.op_category_real,
            )

            # Set-up the reserve requirements
            self.reserves_up_procured[time] = rr_up + mfrr_up
            self.reserves_down_procured[time] = rr_down + mfrr_down
            self.maximum_automated = self.maximum_afrr + self.maximum_fcr

            self.feasible_automated_reserves_up_procured[time] = min(afrr_up, self.maximum_afrr) + min(
                fcr_up, self.maximum_fcr
            )
            self.feasible_automated_reserves_down_procured[time] = min(afrr_down, self.maximum_afrr) + min(
                fcr_down, self.maximum_fcr
            )
            self.automated_unsupplied_reserves += (
                max(afrr_up - self.maximum_afrr, 0)
                + max(fcr_up - self.maximum_fcr, 0)
                + max(afrr_down - self.maximum_afrr, 0)
                + max(fcr_down - self.maximum_fcr, 0)
            )

            if self.storage_type == StorageType.BATTERY:
                nbr_fragment = parameters.battery_nb_fragments
            elif self.storage_type == StorageType.ELECTRIC_VEHICLE:
                nbr_fragment = parameters.ev_nb_fragments
            elif self.storage_type == StorageType.PUMPED_HYDRAULIC_STORAGE:
                nbr_fragment = parameters.phs_nb_fragments

            for n in range(0, nbr_fragment):
                self.power_level_sell_n[n][time] = optimisation_model.add_continuous_variable(
                    name=f"{self.name}_power_level_sell_n_{n}_time_{idx}",
                    lower_bound=0,
                    upper_bound=max_power,
                )
                self.power_level_buy_n[n][time] = optimisation_model.add_continuous_variable(
                    name=f"{self.name}_power_level_buy_n_{n}_time_{idx}",
                    lower_bound=min_power,
                    upper_bound=0,
                )

            # Optimisation Variables related to reserves
            self.reserves_up[time] = optimisation_model.add_continuous_variable(
                name=f"res_up_e_{self.name}_at_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
            self.reserves_down[time] = optimisation_model.add_continuous_variable(
                name=f"res_down_e_{self.name}_at_{time}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            self.unprovided_reserves_up[time] = optimisation_model.add_continuous_variable(
                name=f"unpr_res_up_e_{self.name}_at_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )
            self.unprovided_reserves_down[time] = optimisation_model.add_continuous_variable(
                name=f"unpr_res_down_e_{self.name}_at_{time}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            self.automated_reserves_up[time] = optimisation_model.add_continuous_variable(
                name=f"auto_res_up_e_{self.name}_at_{time}",
                lower_bound=0,
                upper_bound=self.maximum_automated,
            )
            self.automated_reserves_down[time] = optimisation_model.add_continuous_variable(
                name=f"auto_res_down_e_{self.name}_at_{time}",
                lower_bound=-self.maximum_automated,
                upper_bound=self.maximum_automated,
            )
