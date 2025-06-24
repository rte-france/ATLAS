from atlas.enum import LoadType
from atlas.models.equipment.load import Load
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.solver.solver_interface import OptimisationModel


class POLoad:
    """
    This class is used to feed a POLoad from a dispatchable load equipment
    """

    def __init__(self, name):
        # Variables
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

        self.load_type: LoadType | None = None

    def fill_model(self, load_object: Load, parameters: PortfolioOptimisationParameters, model: OptimisationModel):
        self.maximum_afrr = load_object.maximum_afrr
        self.maximum_fcr = load_object.maximum_fcr
        self.load_type = load_object.load_type

        t0_minus_delta_t = parameters.target_times[0] - parameters.timestep
        power = load_object.power.get_forecast(parameters.execution_date, t0_minus_delta_t, parameters.start_date)
        if power is None:
            power = load_object.FinalProg

        for idx, time in enumerate(parameters.target_times):
            max_power = load_object.maximum_power_forecast.get_forecast(
                parameters.execution_date, time, time
            ).get_value(time)

            min_power = 0

            # Get variable cost
            price = load_object.variable_cost.get_value(time)

            self.maximum_power[time] = max_power
            self.minimum_power[time] = min_power
            self.price[time] = price

            model.add_continuous_variable(
                f"{self.name}_power_level_{idx}",
                lower_bound=min_power,
                upper_bound=max_power,
            )

            self.maximum_automated = self.maximum_afrr + self.maximum_fcr
