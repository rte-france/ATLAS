from typing import Any

from pendulum import DateTime

from atlas.models.portfolio import Portfolio
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
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
                    portfolio,
                    time,
                    imbalance_price_down,
                    imbalance_price_up,
                    large_imbalance_price_down,
                    large_imbalance_price_up,
                )
            )
            objective_terms.extend(self._get_reserve_penalty_terms(model, portfolio, time))
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
        portfolio: Portfolio,
        time: DateTime,
        imbalance_price_down,
        imbalance_price_up,
        large_imbalance_price_down,
        large_imbalance_price_up,
    ) -> list[Any]:
        """Get imbalance cost terms as OR-Tools expressions."""
        time_factor = self.parameters.timestep
        terms = []

        small_imbalance_up = model.get_variable(f"{portfolio.name}_small_imbalance_up_{time}")
        small_imbalance_down = model.get_variable(f"{portfolio.name}_small_imbalance_down_{time}")
        large_imbalance_up = model.get_variable(f"{portfolio.name}_large_imbalance_up_{time}")
        large_imbalance_down = model.get_variable(f"{portfolio.name}_large_imbalance_down_{time}")

        # Small imbalance costs
        if imbalance_price_up:
            terms.append(imbalance_price_up * small_imbalance_up * time_factor)

        if imbalance_price_down:
            terms.append(-imbalance_price_down * small_imbalance_down * time_factor)

        # Large imbalance costs
        if large_imbalance_price_up:
            terms.append(large_imbalance_price_up * large_imbalance_up * time_factor)

        if large_imbalance_price_down:
            terms.append(-large_imbalance_price_down * large_imbalance_down * time_factor)

        return terms

    def _get_reserve_penalty_terms(self, model: OptimisationModel, portfolio: Portfolio, time: DateTime) -> list[Any]:
        """Get reserve penalty terms as OR-Tools expressions."""
        time_factor = self.parameters.timestep
        terms = []

        contracted_diff_up = model.get_variable(f"contracted_diff_up_{portfolio.name}_{time}")
        contracted_diff_down = model.get_variable(f"contracted_diff_down_{portfolio.name}_{time}")
        auto_contracted_diff_up = model.get_variable(f"auto_contracted_diff_up_{portfolio.name}_{time}")
        auto_contracted_diff_down = model.get_variable(f"auto_contracted_diff_down_{portfolio.name}_{time}")

        # Manual reserve penalties
        manual_penalty = getattr(self.parameters, "manual_unprocured_reserves_penalty", 1000)
        terms.append(manual_penalty * time_factor * contracted_diff_up)
        terms.append(manual_penalty * time_factor * contracted_diff_down)

        # Automated reserve penalties
        auto_penalty = getattr(self.parameters, "automated_unprocured_reserves_penalty", 1000)
        terms.append(auto_penalty * time_factor * auto_contracted_diff_up)
        terms.append(auto_penalty * time_factor * auto_contracted_diff_down)

        return terms

    def _get_hydro_terms(self):
        pass

    def _get_load_terms(self):
        pass

    def _get_solar_wind_terms(self):
        pass

    def _get_thermal_terms(self):
        pass

    def _get_storage_terms(self):
        pass
