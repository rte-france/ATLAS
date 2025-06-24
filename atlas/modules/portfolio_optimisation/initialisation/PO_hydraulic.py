from pendulum import DateTime

from atlas.models.equipment.hydro import Hydro
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.solver.solver_interface import OptimisationModel


class POHydraulic:
    """
    This class is used to feed a POHydraulic from a hydraulic equipment
    """

    def __init__(self, hydro_object: Hydro, name: str):
        # variables
        self.name = name
        self.power_level = {}
        self.stored_energy = {}
        self.power_level_fragment_sum = {}

        # For each power fragment
        self.power_level_fragment = {}
        self.price_fragment = {}

        for n in range(0, len(hydro_object.fragment_volumes)):
            self.power_level_fragment[n] = {}
            self.price_fragment[n] = {}

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

        # Parameters
        self.maximum_power = {}
        self.minimum_power = {}
        self.initial_level = 0
        self.maximum_energy = {}
        self.minimum_energy = {}
        self.stored_energy_matrix = 0
        self.storage_marginal_value = 0
        self.power_level_prev = 0

        self.maximum_power_sum = 0

    def fill_model(
        self,
        hydro_object: Hydro,
        parameters: PortfolioOptimisationParameters,
        model: OptimisationModel,
    ):
        self.storage_marginal_value = hydro_object.storage_marginal_value

        self.maximum_afrr = hydro_object.maximum_afrr
        self.maximum_fcr = hydro_object.maximum_fcr

        self.stored_energy_matrix = hydro_object.stored_energy
        if len(
            (
                self.stored_energy_matrix.get_forecast(
                    parameters.execution_date,
                    parameters.start_date - parameters.time_step,
                    parameters.end_date,
                )
            )
            == 0
        ):
            self.initial_level = hydro_object.initial_level.filter(
                parameters.start_date - parameters.time_step, parameters.end_date
            )
        else:
            if (
                self.stored_energy_matrix.get_forecast(
                    parameters.execution_date,
                    parameters.start_date - parameters.time_step,
                    parameters.end_date,
                ).first_date()
                < parameters.start_date
            ):
                self.initial_level = self.stored_energy_matrix.get_forecast(
                    parameters.execution_date,
                    parameters.start_date - parameters.time_step,
                    parameters.end_date,
                )

            else:
                self.initial_level = hydro_object.initial_level.filter(
                    parameters.start_date - parameters.time_step, parameters.end_date
                )

        # get global matrix power
        t0_minus_delta_t = parameters.hydraulic_op_times[0] - parameters.time_step_str
        power = hydro_object.power.get_forecast(parameters.execution_date, t0_minus_delta_t, parameters.start_date)
        if power is None:
            power = hydro_object.FinalProg

        self.power_level_prev = power.get_value(t0_minus_delta_t)

        for time in parameters.target_times:
            self.maximum_power_sum += hydro_object.maximum_power.get_value(time)

        for idx, time in enumerate(parameters.hydraulic_op_times):
            min_power = hydro_object.minimum_power.get_value(time)
            max_power = hydro_object.maximum_power.get_value(time)

            self.maximum_power[time] = max_power
            self.minimum_power[time] = min_power
            self.maximum_energy[time] = hydro_object.maximum_energy.get_value(time)
            self.minimum_energy[time] = hydro_object.minimum_energy.get_value(time)

            self.power_level[time] = model.add_continuous_variable(
                name=f"{self.name}_power_level_{idx}",
                lower_bound=0,
                upper_bound=max_power,
            )
            self.stored_energy[time] = model.add_continuous_variable(
                name=f"{self.name}_stored_energy_{idx}",
                lower_bound=0,
                upper_bound=self.maximum_energy[time],
            )
            self._get_fragment_price_and_size(hydro_object, time, parameters)

            self.maximum_automated = self.maximum_afrr + self.maximum_fcr

            # Optimisation Variables related to reserves
            self.reserves_up[time] = model.add_continuous_variable(
                name=f"ress_up_e_{self.name}_at_{str(idx)}",
                lower_bound=0,
                upper_bound=max_power,
            )
            self.reserves_down[time] = model.add_continuous_variable(
                name=f"res_down_e_{self.name}_at_{str(idx)}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            self.unprovided_reserves_up[time] = model.add_continuous_variable(
                name=f"unp_res_up_e_{self.name}_at_{str(idx)}",
                lower_bound=0,
                upper_bound=max_power,
            )
            self.unprovided_reserves_down[time] = model.add_continuous_variable(
                name=f"unp_res_down_e_{self.name}_at_{str(idx)}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            self.relaxed_reserves[time] = model.add_continuous_variable(
                name=f"rel_res_e_{self.name}_at_{str(idx)}",
                lower_bound=min_power,
                upper_bound=0,
            )
            self.automated_reserves_up[time] = model.add_continuous_variable(
                name=f"auto_res_up_e_{self.name}_at_{str(idx)}",
                lower_bound=0,
                upper_bound=self.maximum_automated,
            )
            self.automated_reserves_down[time] = model.add_continuous_variable(
                name=f"auto_res_down_e_{self.name}_at_{str(idx)}",
                lower_bound=0,
                upper_bound=self.maximum_automated,
            )
            self.contracted_difference_up[time] = model.add_continuous_variable(
                name=f"contracted_diff_up_e_{self.name}_at_{str(idx)}",
                lower_bound=0,
                upper_bound=max_power,
            )
            self.contracted_difference_down[time] = model.add_continuous_variable(
                name=f"contracted_diff_down_e_{self.name}_at_{str(idx)}",
                lower_bound=min_power,
                upper_bound=max_power,
            )
            self.automated_contracted_difference_up[time] = model.add_continuous_variable(
                name=f"auto_contracted_diff_up_e_{self.name}_at_{str(idx)}",
                lower_bound=0,
                upper_bound=max_power,
            )
            self.automated_contracted_difference_down[time] = model.add_continuous_variable(
                name=f"auto_contracted_diff_down_e_{self.name}_at_{str(idx)}",
                lower_bound=min_power,
                upper_bound=max_power,
            )

    def _get_fragment_price_and_size(
        self, hydro_object: Hydro, time: DateTime, parameters: PortfolioOptimisationParameters
    ):
        """
        This function formulates the hydraulic reservoir offers.

        Arguments:
        - `input_marker`: an input marker
        - `output_marker`: an output marker
        - `orders_time`: a list of dates at which orders must be formulated.
        """

        delta_wu = {}
        for category in range(len(hydro_object.fragment_volumes)):
            delta_wu[category] = (
                hydro_object.fragment_volumes[category],
                hydro_object.fragment_prices[category],
            )

        energy_forecast = self.stored_energy_matrix.get_forecast(
            parameters.execution_date,
            parameters.start_date - parameters.time_step,
            parameters.start_date - parameters.time_step,
        )

        if len(energy_forecast) > 0:
            energy_level = energy_forecast.get_value(parameters.start_date - parameters.time_step)
        else:
            energy_level = self.initial_level.get_value(parameters.start_date - parameters.time_step)

        x_min = filter(lambda x: int(x) <= energy_level, self.storage_marginal_value.Index)
        x_max = filter(lambda x: int(x) > energy_level, self.storage_marginal_value.Index)

        if x_min:
            xp_min = max(x_min, key=lambda x: int(x))
            level_inf = self.storage_marginal_value.GetTimeSeriesByName(xp_min)
        if x_max:
            xp_max = min(x_max, key=lambda x: int(x))
            level_sup = self.storage_marginal_value.GetTimeSeriesByName(xp_max)
        if x_min and x_max:
            weight_inf = (int(xp_max) - energy_level) / (int(xp_max) - int(xp_min))
            weight_sup = (energy_level - int(xp_min)) / (int(xp_max) - int(xp_min))

        # Now we loop over the time stamps for which we want an offer to be made.
        # We formulate as many offers as there are time stamps in orders_time.

        # Compute the actual volumes of fragments, according to maximum_power
        capacity = self.maximum_power[time]
        volumes = {key: capacity * vu[0] for key, vu in delta_wu.items()}

        if time in parameters.hydraulic_op_times:
            self.power_level_fragment_sum[time] = 0

            # create an offer for each element in volumes
            for k, v in volumes.items():
                if not x_min and x_max:
                    price = level_sup.get_value(time, API.TimeSeries.Linear) + delta_wu[k][1]
                elif not x_max and x_min:
                    price = level_inf.get_value(time, API.TimeSeries.Linear) + delta_wu[k][1]
                elif not x_max and not x_min:
                    price = delta_wu[k][1]
                else:
                    # This AREA DEAL WITH THE PRICE
                    p_min = level_inf.get_value(time, API.TimeSeries.Linear)
                    p_max = level_sup.get_value(time, API.TimeSeries.Linear)
                    price = weight_inf * p_min + weight_sup * p_max + delta_wu[k][1]

                self.power_level_fragment[k][time] = API.Solver.NewOpVariable(
                    f"{self.name}_power_level_frag_{k}_at_{str(time)}",
                    0,
                    v,
                    API.Solver.OpCategoryReal,
                )
                self.price_fragment[k][time] = price

                if k == 0:
                    self.power_level_fragment_sum[time] = self.power_level_fragment[k][time]
                else:
                    self.power_level_fragment_sum[time] += self.power_level_fragment[k][time]
