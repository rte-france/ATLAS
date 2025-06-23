from typing import Any

from pendulum import DateTime

from atlas.models.portfolio import Portfolio
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.solver.solver_interface import OptimisationModel


class ObjectiveFunctionBuilder:
    """Builds the optimization objective function using OptimisationModel."""

    def __init__(self, parameters: PortfolioOptimisationParameters):
        self.parameters = parameters

    def build_objective(self, model: OptimisationModel, portfolio: Portfolio, target_times: list) -> Any:
        """Build the complete objective function as OR-Tools expression."""
        objective_terms = []

        for time in target_times:
            objective_terms.extend(self._get_imbalance_cost_terms(model, portfolio, time))
            objective_terms.extend(self._get_reserve_penalty_terms(model, portfolio, time))
            objective_terms.extend(self._get_hydro_terms())
            objective_terms.extend(self._get_load_terms())
            objective_terms.extend(self._get_solar_wind_terms())
            objective_terms.extend(self._get_thermal_terms())
            objective_terms.extend(self._get_storage_terms())

        if objective_terms:
            return sum(objective_terms)

    def _get_imbalance_cost_terms(self, model: OptimisationModel, portfolio: Portfolio, time) -> list[Any]:
        """Get imbalance cost terms as OR-Tools expressions."""
        time_factor = self.parameters.time_step / 60.0
        terms = []

        # Get variables from portfolio (these would need to be OR-Tools variables)
        small_imbal_up = model.get_variable(f"small_imbal_up_{time}")
        small_imbal_down = model.get_variable(f"small_imbal_down_{time}")
        large_imbal_up = model.get_variable(f"large_imbal_up_{time}")
        large_imbal_down = model.get_variable(f"large_imbal_down_{time}")

        # Small imbalance costs
        if portfolio.imbal_price_up and time in portfolio.imbal_price_up:
            terms.append(portfolio.imbal_price_up[time] * small_imbal_up * time_factor)

        if portfolio.imbal_price_down and time in portfolio.imbal_price_down:
            terms.append(-portfolio.imbal_price_down[time] * small_imbal_down * time_factor)

        # Large imbalance costs
        if portfolio.large_imbal_price_up and time in portfolio.large_imbal_price_up:
            terms.append(portfolio.large_imbal_price_up[time] * large_imbal_up * time_factor)

        if portfolio.large_imbal_price_down and time in portfolio.large_imbal_price_down:
            terms.append(-portfolio.large_imbal_price_down[time] * large_imbal_down * time_factor)

        return terms

    def _get_reserve_penalty_terms(self, model: OptimisationModel, portfolio: Portfolio, time: DateTime) -> list[Any]:
        """Get reserve penalty terms as OR-Tools expressions."""
        time_factor = self.parameters.time_step / 60.0
        terms = []

        contracted_diff_up = model.get_variable(f"contracted_diff_up_{time}")
        contracted_diff_down = model.get_variable(f"contracted_diff_down_{time}")
        auto_contracted_diff_up = model.get_variable(f"auto_contracted_diff_up_{time}")
        auto_contracted_diff_down = model.get_variable(f"auto_contracted_diff_down_{time}")

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
