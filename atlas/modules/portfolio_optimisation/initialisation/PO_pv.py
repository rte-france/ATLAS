import API

from atlas.models.equipment.solar import Solar
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.solver.solver_interface import OptimisationModel


class POPV:
    """
    This class is used to feed a POPV from a photovoltaic equipment
    """

    def __init__(self, name):
        # variables
        self.name = name
        self.power_level = {}
        self.price = {}

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
        solar_object: Solar,
        parameters: PortfolioOptimisationParameters,
        model: OptimisationModel,
    ):
        self.maximum_afrr = solar_object.maximum_afrr
        self.maximum_fcr = solar_object.maximum_fcr

        # get global matrix power
        t0_minus_delta_t = API.datetime_index.shift(parameters.target_times, "-" + parameters.time_step_str)[0]
        power = solar_object.power.get_forecast(parameters.execution_date, t0_minus_delta_t, parameters.start_date)
        if power is None:
            power = solar_object.final_prog

        for idx, time in enumerate(parameters.target_times):
            # Get min and max power
            max_power = solar_object.maximum_power_forecast.get_forecast(
                parameters.execution_date, time, time
            ).get_value(time)

            min_power = (1 - solar_object.maximum_curtailment_ratio.get_value(time)) * max_power

            price = solar_object.variable_cost.get_value(time)

            afrr_up = solar_object.afrr_up_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
            afrr_down = solar_object.afrr_down_procured.get_forecast(parameters.execution_date, time, time).get_value(
                time
            )
            mfrr_up = solar_object.mfrr_up_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
            mfrr_down = solar_object.mfrr_down_procured.get_forecast(parameters.execution_date, time, time).get_value(
                time
            )
            rr_up = solar_object.rr_up_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
            rr_down = solar_object.rr_down_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
            fcr_up = solar_object.fcr_up_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
            fcr_down = solar_object.fcr_down_procured.get_forecast(parameters.execution_date, time, time).get_value(
                time
            )

            self.maximum_power[time] = max_power
            self.minimum_power[time] = min_power
            self.price[time] = price

            # create optimisation variables
            self.power_level[time] = model.add_continuous_variable(
                name=f"{self.name}_power_level_{idx}",
                lower_bound=0,
                upper_bound=max_power,
            )

            self.maximum_automated = self.maximum_afrr + self.maximum_fcr

            # Optimisation Variables related tp,
            self.reserves_up[time] = model.add_continuous_variable(
                name=f"res_up_e_{self.name}_at_{idx}",
                lower_bound=0,
                upper_bound=max_power,
            )
            self.reserves_down[time] = model.add_continuous_variable(
                name=f"res_down_e_{self.name}_at_{idx}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            self.unprovided_reserves_up[time] = model.add_continuous_variable(
                name=f"unp_res_up_e_{self.name}_at_{idx}",
                lower_bound=0,
                upper_bound=max_power,
            )
            self.unprovided_reserves_down[time] = model.add_continuous_variable(
                name=f"unp_res_down_e_{self.name}_at_{idx}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            self.automated_reserves_up[time] = model.add_continuous_variable(
                name=f"auto_res_up_e_{self.name}_at_{idx}",
                lower_bound=0,
                upper_bound=self.maximum_automated,
            )
            self.automated_reserves_down[time] = model.add_continuous_variable(
                name=f"auto_res_down_e_{self.name}_at_{idx}",
                lower_bound=0,
                upper_bound=self.maximum_automated,
            )
            self.contracted_difference_up[time] = model.add_continuous_variable(
                name=f"contracted_diff_up_e_{self.name}_at_{idx}",
                lower_bound=0,
                upper_bound=max_power,
            )
            self.contracted_difference_down[time] = model.add_continuous_variable(
                name=f"contracted_diff_down_e_{self.name}_at_{idx}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            self.automated_contracted_difference_up[time] = model.add_continuous_variable(
                name=f"auto_contracted_diff_up_e_{self.name}_at_{idx}",
                lower_bound=0,
                upper_bound=max_power,
            )
            self.automated_contracted_difference_down[time] = model.add_continuous_variable(
                name=f"auto_contracted_diff_down_e_{self.name}_at_{idx}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
