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
            # Add imbalance costs
            objective_terms.extend(self._get_imbalance_cost_terms(model, portfolio, time))

            # Add reserve penalties
            objective_terms.extend(self._get_reserve_penalty_terms(model, portfolio, time))

        # Sum all terms into a single expression
        if objective_terms:
            return sum(objective_terms)
        else:
            # Return zero expression if no terms
            dummy_var = model.add_continuous_variable("dummy_objective", 0, 0)
            return dummy_var

    def _get_imbalance_cost_terms(self, model: OptimisationModel, portfolio: Portfolio, time) -> list[Any]:
        """Get imbalance cost terms as OR-Tools expressions."""
        time_factor = self.parameters.time_step / 60.0
        terms = []

        # Get variables from portfolio (these would need to be OR-Tools variables)
        small_imbal_up = self._get_or_create_variable(model, f"small_imbal_up_{time}")
        small_imbal_down = self._get_or_create_variable(model, f"small_imbal_down_{time}")
        large_imbal_up = self._get_or_create_variable(model, f"large_imbal_up_{time}")
        large_imbal_down = self._get_or_create_variable(model, f"large_imbal_down_{time}")

        # Small imbalance costs
        if hasattr(portfolio, "imbal_price_up") and time in portfolio.imbal_price_up:
            terms.append(portfolio.imbal_price_up[time] * small_imbal_up * time_factor)

        if hasattr(portfolio, "imbal_price_down") and time in portfolio.imbal_price_down:
            terms.append(-portfolio.imbal_price_down[time] * small_imbal_down * time_factor)

        # Large imbalance costs
        if hasattr(portfolio, "large_imbal_price_up") and time in portfolio.large_imbal_price_up:
            terms.append(portfolio.large_imbal_price_up[time] * large_imbal_up * time_factor)

        if hasattr(portfolio, "large_imbal_price_down") and time in portfolio.large_imbal_price_down:
            terms.append(-portfolio.large_imbal_price_down[time] * large_imbal_down * time_factor)

        return terms

    def _get_reserve_penalty_terms(self, model: OptimisationModel, portfolio: Portfolio, time: DateTime) -> list[Any]:
        """Get reserve penalty terms as OR-Tools expressions."""
        time_factor = self.parameters.time_step / 60.0
        terms = []

        # Get or create reserve variables
        contracted_diff_up = self._get_or_create_variable(model, f"contracted_diff_up_{time}")
        contracted_diff_down = self._get_or_create_variable(model, f"contracted_diff_down_{time}")
        auto_contracted_diff_up = self._get_or_create_variable(model, f"auto_contracted_diff_up_{time}")
        auto_contracted_diff_down = self._get_or_create_variable(model, f"auto_contracted_diff_down_{time}")

        # Manual reserve penalties
        manual_penalty = getattr(self.parameters, "manual_unprocured_reserves_penalty", 1000)
        terms.append(manual_penalty * time_factor * contracted_diff_up)
        terms.append(manual_penalty * time_factor * contracted_diff_down)

        # Automated reserve penalties
        auto_penalty = getattr(self.parameters, "automated_unprocured_reserves_penalty", 1000)
        terms.append(auto_penalty * time_factor * auto_contracted_diff_up)
        terms.append(auto_penalty * time_factor * auto_contracted_diff_down)

        return terms

    def _get_or_create_variable(self, model: OptimisationModel, var_name: str) -> Any:
        """Get existing variable or create new one."""
        try:
            return model.get_variable(var_name)
        except ValueError:
            # Create new continuous variable if it doesn't exist
            return model.add_continuous_variable(var_name, lower_bound=0.0)
