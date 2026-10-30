from atlas.abstract_class.dataset import ModuleResult
from atlas.modules.price_forecast_orders_creation.parameters import PriceForecastOrdersCreationParameters
from atlas.orchestrator.change_set import ChangeSet


class PriceForecastOrdersCreationResult(ModuleResult[PriceForecastOrdersCreationParameters]):
    def build_change_sets(self) -> list[ChangeSet]:
        pass
