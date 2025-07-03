from typing import Any

from pendulum import DateTime

from atlas.enum import LoadType
from atlas.models.equipment.hydro import Hydro
from atlas.models.equipment.load import Load
from atlas.models.equipment.solar import Solar
from atlas.models.equipment.storage import Storage
from atlas.models.equipment.wind import Wind
from atlas.models.portfolio import Portfolio
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.get_fragment_price import _get_fragment_length, compute_fragment_prices
from atlas.modules.portfolio_optimisation.utils.getters import get_variable_cost
from atlas.modules.portfolio_optimisation.utils.imbalance_price import estimate_imbalance_prices
from atlas.solver.solver_interface import OptimisationModel


class ObjectiveFunctionBuilder:
    """Builds the optimization objective function using OptimisationModel."""

    def __init__(self, parameters: PortfolioOptimisationParameters):
        self.parameters = parameters

    def set_objective(self, model: OptimisationModel, portfolio: Portfolio, target_times: list) -> None:
        """Set the objective function in the optimization model."""
        objective = self.build_objective(model, portfolio, target_times)
        if objective:
            model.set_objective(objective)
        else:
            raise ValueError("No valid objective function could be built.")

    def build_objective(self, model: OptimisationModel, portfolio: Portfolio, target_times: list[DateTime]) -> Any:
        """Build the complete objective function as OR-Tools expression."""
        objective_terms = []

        for time in target_times:
            imbalance_price_down, imbalance_price_up, large_imbalance_price_down, large_imbalance_price_up = (
                estimate_imbalance_prices(time, portfolio.market_area, portfolio.control_block, self.parameters)
            )
            objective_terms.extend(
                self._get_imbalance_cost_terms(
                    model,
                    portfolio.name,
                    time,
                    imbalance_price_down,
                    imbalance_price_up,
                    large_imbalance_price_down,
                    large_imbalance_price_up,
                )
            )
            objective_terms.extend(self._get_reserve_penalty_terms(model, portfolio.name, time))
            objective_terms.extend(self._get_hydro_terms())
            objective_terms.extend(self._get_load_terms())
            objective_terms.extend(self._get_solar_wind_terms())
            objective_terms.extend(self._get_thermal_terms())
            objective_terms.extend(self._get_storage_terms())

        if objective_terms:
            return sum(objective_terms)

    def _get_imbalance_cost_terms(
        self,
        model: OptimisationModel,
        portfolio_name: str,
        time: DateTime,
        imbalance_price_down: float,
        imbalance_price_up: float,
        large_imbalance_price_down: float,
        large_imbalance_price_up: float,
    ) -> list[Any]:
        """Get imbalance cost terms as OR-Tools expressions."""

        terms = []

        small_imbalance_up_var = model.get_variable(f"{portfolio_name}_small_imbalance_up_{time}")
        small_imbalance_down_var = model.get_variable(f"{portfolio_name}_small_imbalance_down_{time}")
        large_imbalance_up_var = model.get_variable(f"{portfolio_name}_large_imbalance_up_{time}")
        large_imbalance_down_var = model.get_variable(f"{portfolio_name}_large_imbalance_down_{time}")

        # Small imbalance costs
        if imbalance_price_up:
            terms.append(imbalance_price_up * small_imbalance_up_var * self.parameters.timestep)

        if imbalance_price_down:
            terms.append(-imbalance_price_down * small_imbalance_down_var * self.parameters.timestep)

        # Large imbalance costs
        if large_imbalance_price_up:
            terms.append(large_imbalance_price_up * large_imbalance_up_var * self.parameters.timestep)

        if large_imbalance_price_down:
            terms.append(-large_imbalance_price_down * large_imbalance_down_var * self.parameters.timestep)

        return terms

    def _get_reserve_penalty_terms(self, model: OptimisationModel, portfolio_name: str, time: DateTime) -> list[Any]:
        """Get reserve penalty terms as OR-Tools expressions."""

        terms = []

        contracted_diff_up = model.get_variable(f"contracted_diff_up_{portfolio_name}_{time}")
        contracted_diff_down = model.get_variable(f"contracted_diff_down_{portfolio_name}_{time}")
        auto_contracted_diff_up = model.get_variable(f"auto_contracted_diff_up_{portfolio_name}_{time}")
        auto_contracted_diff_down = model.get_variable(f"auto_contracted_diff_down_{portfolio_name}_{time}")

        # Manual reserve penalties
        terms.append(self.parameters.manual_unprocured_reserves_penalty, *self.parameters.timestep * contracted_diff_up)
        terms.append(
            self.parameters.manual_unprocured_reserves_penalty, *self.parameters.timestep * contracted_diff_down
        )

        # Automated reserve penalties
        terms.append(
            self.parameters.automated_unprocured_reserves_penalty * self.parameters.timestep * auto_contracted_diff_up
        )
        terms.append(
            self.parameters.automated_unprocured_reserves_penalty * self.parameters.timestep * auto_contracted_diff_down
        )

        return terms

    def _get_hydro_terms(
        self, model: OptimisationModel, time: DateTime, hydro_equipments: dict[str, list[Hydro]], price_forecast: float
    ):
        for obj in hydro_equipments:
            for k in range(_get_fragment_length(obj)):
                if time in self.parameters.target_times:
                    model.add_objective(
                        compute_fragment_prices(obj, time, k, self.parameters)
                        * model.get_variable(f"{obj.name}_power_level_frag_{k}_at_{time}")
                        * self.parameters.timestep
                    )

                else:
                    model.add_objective(
                        -(price_forecast - compute_fragment_prices(obj, time, k, self.parameters))
                        * model.get_variable(f"{obj.name}_power_level_frag_{k}_at_{time}")
                        * self.parameters.timestep
                    )

    def _get_load_terms(
        self,
        model: OptimisationModel,
        time: DateTime,
        load_equipments: list[Load],
        price_forecast: float,
    ):
        for obj in load_equipments:
            if time in self.parameters.target_times:
                power_level_var = model.get_variable(f"{obj.name}_power_level_{time}")
                if obj.load_type == LoadType.POWER_TO_GAS:
                    model.add_objective(
                        (get_variable_cost(obj, time) - price_forecast) * power_level_var * self.parameters.timestep
                    )
                else:
                    model.add_objective(get_variable_cost(obj, time) * -power_level_var * self.parameters.timestep)

    def _get_solar_wind_terms(
        self,
        model: OptimisationModel,
        time: DateTime,
        equipments: list[Wind | Solar],
    ):
        for obj in equipments:
            if time in self.parameters.target_times:
                power_level_var = model.get_variable(f"{obj.name}_power_level_{time}")
                model.add_objective(get_variable_cost(obj, time) * power_level_var * self.parameters.timestep)

    def _get_thermal_terms(self):
        pass

    def _get_storage_terms(
        self,
        model: OptimisationModel,
        time: DateTime,
        storage_equipments: list[Storage],
        price_forecast: float,
    ):
        for obj in storage_equipments:
            power_level_sell_var = model.get_variable(f"{obj.name}_power_level_sell_{time}")
            power_level_buy_var = model.get_variable(f"{obj.name}_power_level_buy_{time}")

            if max(obj.maximum_energy.values()) <= 0:
                continue
            local_op_times = self.parameters.storage_mapping[obj.storage_type].get("optimisation_times", [])

            if time not in local_op_times:
                continue

            model.add_objective(
                price_forecast * (power_level_buy_var + power_level_sell_var) * self.parameters.timestep
            )
            if time not in self.parameters.target_times:
                smoothing_factor = self.parameters.storage_mapping[obj.storage_type]["smoothing_factor"]
                nb_fragment = self.parameters.storage_mapping[obj.storage_type]["nb_fragment"]
                for n in range(0, nb_fragment):
                    power_level_sell_n_var = model.get_variable(f"{obj.name}_power_level_sell_n_{n}_time_{time}")
                    power_level_buy_n_var = model.get_variable(f"{obj.name}_power_level_buy_n_{n}_time_{time}")

                    # The objective function is the total profit over the optimisation period
                    if nb_fragment == 1 and n == 0:
                        model.add_objective(
                            -power_level_sell_n_var * price_forecast - power_level_buy_n_var * price_forecast
                        )
                    else:
                        model.add_objective(
                            -power_level_sell_n_var * price_forecast * (1 - n * smoothing_factor / (nb_fragment - 1))
                            - power_level_buy_n_var * price_forecast * (1 + n * smoothing_factor / (nb_fragment - 1))
                        )
