from atlas.models.equipment.equipment import Equipment
from atlas.models.equipment.thermal import Thermal
from atlas.models.portfolio import Portfolio
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


def is_excluded_technology(parameters: PortfolioOptimisationParameters, equipment: type[Equipment]) -> bool:
    """Check if equipment technology is excluded."""
    return equipment.__class__ in parameters.excluded_technologies


def is_excluded_thermal_strategy(parameters: PortfolioOptimisationParameters, equipment: Thermal) -> bool:
    """Check if thermal equipment strategy is excluded."""
    return equipment.strategy in parameters.excluded_thermal_strategies


def is_excluded_market_area(parameters: PortfolioOptimisationParameters, portfolio: Portfolio) -> bool:
    """Check if portfolio market area is excluded."""
    return not parameters.use_forecast and portfolio.market_area.name in parameters.excluded_market_areas


def should_manually_activate(equipment: type[Equipment]) -> bool:
    """Determine if equipment should be manually activated."""
    return is_excluded_technology(equipment) or is_excluded_thermal_strategy(equipment)
