import API
from PO_functions import get_time_series_value

from atlas.models.equipment.solar import Solar
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


class POPV:
    """
    This class is used to feed a POPV from a photovoltaic equipment
    """

    def __init__(self, name):
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

    def init_variables(self, solar_object: Solar, p: PortfolioOptimisationParameters):
        self.maximum_afrr = solar_object.maximum_afrr
        self.maximum_fcr = solar_object.maximum_fcr

        # get global matrix power
        t0_minus_delta_t = API.datetime_index.shift(p.target_times, "-" + p.time_step_str)[0]
        power = solar_object.power.get_forecast(p.execution_date, t0_minus_delta_t, p.start_date)
        if power is None:
            power = solar_object.final_prog

        # The following power level should be from last forecast of Power matrix, it is final prog for test
        # self.power_level_prev = get_time_series_value(power, t0_minus_delta_t)

        for time_enum, time in enumerate(p.target_times):
            # Get min and max power
            max_power = get_time_series_value(
                solar_object.maximum_power_forecast.get_forecast(p.execution_date, time, time), time
            )
            min_power = (1 - get_time_series_value(solar_object.maximum_curtailment_ratio, time)) * max_power

            # Get variable cost
            price = get_time_series_value(solar_object.variable_cost, time)

            # Get procured reserves
            afrr_up = solar_object.afrr_up_procured.get_forecast(p.execution_date, time, time).get_value(time)
            afrr_down = solar_object.afrr_down_procured.get_forecast(p.execution_date, time, time).get_value(time)
            mfrr_up = solar_object.mfrr_up_procured.get_forecast(p.execution_date, time, time).get_value(time)
            mfrr_down = solar_object.mfrr_down_procured.get_forecast(p.execution_date, time, time).get_value(time)
            rr_up = solar_object.rr_up_procured.get_forecast(p.execution_date, time, time).get_value(time)
            rr_down = solar_object.rr_down_procured.get_forecast(p.execution_date, time, time).get_value(time)
            fcr_up = solar_object.fcr_up_procured.get_forecast(p.execution_date, time, time).get_value(time)
            fcr_down = solar_object.fcr_down_procured.get_forecast(p.execution_date, time, time).get_value(time)

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

            # init variables
            # create optimisation variables
            self.power_level[time] = API.solver.new_op_variable(
                f"{self.name}_power_level_{time_enum}",
                0,
                max_power,
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

            # Optimisation Variables related tp,
            self.reserves_up[time] = API.solver.new_op_variable(
                "res_up_e_%s_at_%s" % (self.name, str(time_enum)),
                0,
                max_power,
                API.solver.op_category_real,
            )
            self.reserves_down[time] = API.solver.new_op_variable(
                "res_down_e_%s_at_%s" % (self.name, str(time_enum)),
                min_power,
                max_power,
                API.solver.op_category_real,
            )
            self.unprovided_reserves_up[time] = API.solver.new_op_variable(
                "unp_res_up_e_%s_at_%s" % (self.name, str(time_enum)),
                0,
                max_power,
                API.solver.op_category_real,
            )
            self.unprovided_reserves_down[time] = API.solver.new_op_variable(
                "unp_res_down_e_%s_at_%s" % (self.name, str(time_enum)),
                min_power,
                max_power,
                API.solver.op_category_real,
            )
            self.automated_reserves_up[time] = API.solver.new_op_variable(
                "auto_res_up_e_%s_at_%s" % (self.name, str(time_enum)),
                0,
                self.maximum_automated,
                API.solver.op_category_real,
            )
            self.automated_reserves_down[time] = API.solver.new_op_variable(
                "auto_res_down_e_%s_at_%s" % (self.name, str(time_enum)),
                0,
                self.maximum_automated,
                API.solver.op_category_real,
            )
            self.contracted_difference_up[time] = API.solver.new_op_variable(
                "contracted_diff_up_e_%s_at_%s" % (self.name, str(time_enum)),
                0,
                max_power,
                API.solver.op_category_real,
            )
            self.contracted_difference_down[time] = API.solver.new_op_variable(
                "contracted_diff_down_e_%s_at_%s" % (self.name, str(time_enum)),
                min_power,
                max_power,
                API.solver.op_category_real,
            )
            self.automated_contracted_difference_up[time] = API.solver.new_op_variable(
                "auto_contracted_diff_up_e_%s_at_%s" % (self.name, str(time_enum)),
                0,
                max_power,
                API.solver.op_category_real,
            )
            self.automated_contracted_difference_down[time] = API.solver.new_op_variable(
                "auto_contracted_diff_down_e_%s_at_%s" % (self.name, str(time_enum)),
                min_power,
                max_power,
                API.solver.op_category_real,
            )
