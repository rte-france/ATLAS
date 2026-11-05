import atlas.config as cfg
from atlas import AtlasDataset, generate_datetimes
from atlas.abstract_class.module import AbstractModule
from atlas.modules.day_ahead_orders.steps.hydro import HydraulicStep
from atlas.modules.price_forecast_orders_creation.input_dataset import PriceForecastOrdersCreationInputDataset
from atlas.modules.price_forecast_orders_creation.parameters import PriceForecastOrdersCreationParameters
from atlas.modules.price_forecast_orders_creation.result import PriceForecastOrdersCreationResult
from atlas.modules.price_forecast_orders_creation.steps.abstract_step import AbstractOrderStep
from atlas.modules.price_forecast_orders_creation.steps.non_dispatchable import NonDispatchableStep
from atlas.modules.price_forecast_orders_creation.steps.storage import StorageStep


class PriceForecastOrdersCreationModule(
    AbstractModule[
        PriceForecastOrdersCreationParameters,
        PriceForecastOrdersCreationInputDataset,
        PriceForecastOrdersCreationResult,
    ]
):
    @classmethod
    def get_parameters_class(cls) -> type[PriceForecastOrdersCreationParameters]:
        return PriceForecastOrdersCreationParameters

    def import_data(
        self, input_data: AtlasDataset, parameters: PriceForecastOrdersCreationParameters
    ) -> PriceForecastOrdersCreationInputDataset:
        """Imports data using business objects and parameters."""
        pass

    def validate_data(
        self, parameters: PriceForecastOrdersCreationParameters, input_dataset: PriceForecastOrdersCreationInputDataset
    ) -> bool:
        """Validates imported or generated data."""
        pass

    def validates_results(
        self,
        parameters: PriceForecastOrdersCreationParameters,
        input_dataset: PriceForecastOrdersCreationInputDataset,
        result: PriceForecastOrdersCreationResult,
    ) -> bool:
        """Validates results"""
        pass

    def export_results(
        self,
        parameters: PriceForecastOrdersCreationParameters,
        input_dataset: PriceForecastOrdersCreationInputDataset,
        result: PriceForecastOrdersCreationResult,
    ) -> None:
        """Exports results."""
        pass

    def execute(
        self, parameters: PriceForecastOrdersCreationParameters, input_dataset: PriceForecastOrdersCreationInputDataset
    ) -> PriceForecastOrdersCreationResult:

        orders_time = generate_datetimes(
            parameters.temporal.start_date, parameters.penultimate_date, parameters.temporal.timestep
        )
        result = PriceForecastOrdersCreationResult(input_dataset)

        steps: list[tuple[str, AbstractOrderStep]] = [
            ("non-dispatchable", NonDispatchableStep(result, orders_time, parameters)),
            ("storage", StorageStep(result, orders_time, parameters)),
            ("hydro", HydraulicStep(result, orders_time, parameters)),
            ("wind/solar", WindAndSolarStep(result, orders_time, parameters)),
        ]

        for name, step in steps:
            cfg.logger.info(f"Formulation of the {name} orders...")
            step_result = step.formulate()
            result.order.extend(step_result.orders)
            result.order_coupling.extend(step_result.order_couplings)
            cfg.logger.info(f"{name.capitalize()} orders formulated.")
        """Executes the module's main logic."""
        pass
