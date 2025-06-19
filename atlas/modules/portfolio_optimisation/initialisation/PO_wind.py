import API

from atlas.models.equipment.wind import Wind
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.solver.solver_interface import OptimisationModel


class POWind:
    """
    This class is used to feed a POWind from a wind equipment
    """

    def __init__(self, name: str):
        # variables
        self.name = name
        self.power_level = {}
        self.price = {}

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
        self.relaxed_reserves = {}
        self.automated_reserves_up = {}
        self.automated_reserves_down = {}
        self.contracted_difference_up = {}
        self.contracted_difference_down = {}
        self.automated_contracted_difference_up = {}
        self.automated_contracted_difference_down = {}

        self.maximum_afrr = 0
        self.maximum_fcr = 0
        self.maximum_automated = 0

        self.maximum_power = {}
        self.minimum_power = {}

    def fill_model(
        self,
        wind_object: Wind,
        parameters: PortfolioOptimisationParameters,
        optimisation_model: OptimisationModel,
    ):
        self.maximum_afrr = wind_object.maximum_afrr
        self.maximum_fcr = wind_object.maximum_fcr

        # get global matrix power
        t0_minus_delta_t = API.datetime_index.shift(parameters.target_times, "-" + parameters.time_step_str)[0]
        power = wind_object.power.get_forecast(parameters.execution_date, t0_minus_delta_t, parameters.start_date)
        if power is None:
            power = wind_object.final_prog

        for idx, time in enumerate(parameters.target_times):
            # Get min and max power
            max_power = wind_object.maximum_power_forecast.get_forecast(
                parameters.execution_date, time, time
            ).get_value(time)
            min_power = (1 - wind_object.maximum_curtailment_ratio.get_value(time)) * max_power

            price = wind_object.variable_cost.get_value(time)

            afrr_up = wind_object.afrr_up_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
            afrr_down = wind_object.afrr_down_procured.get_forecast(parameters.execution_date, time, time).get_value(
                time
            )
            mfrr_up = wind_object.mfrr_up_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
            mfrr_down = wind_object.mfrr_down_procured.get_forecast(parameters.execution_date, time, time).get_value(
                time
            )
            rr_up = wind_object.rr_up_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
            rr_down = wind_object.rr_down_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
            fcr_up = wind_object.fcr_up_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
            fcr_down = wind_object.fcr_down_procured.get_forecast(parameters.execution_date, time, time).get_value(time)

            self.maximum_power[time] = max_power
            self.minimum_power[time] = min_power
            self.price[time] = price

            self.afrr_up_procured[time] = afrr_up
            self.afrr_down_procured[time] = afrr_down
            self.mfrr_up_procured[time] = mfrr_up
            self.mfrr_down_procured[time] = mfrr_down
            self.rr_up_procured[time] = rr_up
            self.rr_down_procured[time] = rr_down
            self.fcr_up_procured[time] = fcr_up
            self.fcr_down_procured[time] = fcr_down

            # create optimization variables
            self.power_level[time] = optimisation_model.add_continuous_variable(
                name=f"{self.name}_power_level_{idx}",
                lower_bound=0,
                upper_bound=max_power,
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

            # Optimisation Variables related to reserves
            self.reserves_up[time] = optimisation_model.add_continuous_variable(
                name=f"res_up_e_{self.name}_at_{idx}",
                lower_bound=0,
                upper_bound=max_power,
            )
            self.reserves_down[time] = optimisation_model.add_continuous_variable(
                name=f"res_down_e_{self.name}_at_{idx}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            self.unprovided_reserves_up[time] = optimisation_model.add_continuous_variable(
                name=f"unp_res_up_e_{self.name}_at_{idx}",
                lower_bound=0,
                upper_bound=max_power,
            )
            self.unprovided_reserves_down[time] = optimisation_model.add_continuous_variable(
                name=f"unp_res_down_e_{self.name}_at_{idx}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            self.automated_reserves_up[time] = optimisation_model.add_continuous_variable(
                name=f"auto_res_up_e_{self.name}_at_{idx}",
                lower_bound=0,
                upper_bound=self.maximum_automated,
            )
            self.automated_reserves_down[time] = optimisation_model.add_continuous_variable(
                name=f"auto_res_down_e_{self.name}_at_{idx}",
                lower_bound=0,
                upper_bound=self.maximum_automated,
            )
            self.contracted_difference_up[time] = optimisation_model.add_continuous_variable(
                name=f"contracted_diff_up_e_{self.name}_at_{idx}",
                lower_bound=0,
                upper_bound=max_power,
            )
            self.contracted_difference_down[time] = optimisation_model.add_continuous_variable(
                name=f"contracted_diff_down_e_{self.name}_at_{idx}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            self.automated_contracted_difference_up[time] = self.optimisation_model.add_continuous_variable(
                name=f"auto_contracted_diff_up_e_{self.name}_at_{idx}",
                lower_bound=0,
                upper_bound=max_power,
            )
            self.automated_contracted_difference_down[time] = self.optimisation_model.add_continuous_variable(
                name=f"auto_contracted_diff_down_e_{self.name}_at_{idx}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
