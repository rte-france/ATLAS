"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from collections.abc import Iterable

import atlas.config as cfg
from atlas.abstract_class.module import AbstractModule
from atlas.enums import BusinessModelName
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.day_ahead_orders.input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.result import DayAheadOrdersResult
from atlas.modules.day_ahead_orders.steps.abstract_step import AbstractOrderStep
from atlas.modules.day_ahead_orders.steps.hydro import HydraulicStep
from atlas.modules.day_ahead_orders.steps.load import LoadStep
from atlas.modules.day_ahead_orders.steps.non_dispatchable import NonDispatchableStep
from atlas.modules.day_ahead_orders.steps.renewables import WindPVStep
from atlas.modules.day_ahead_orders.steps.storage.storage_step import StorageStep
from atlas.modules.day_ahead_orders.steps.thermal.thermal_bidding_step import ThermalBiddingStep
from atlas.timing import generate_datetimes


class DayAheadOrdersModule(AbstractModule[DayAheadOrdersParameters, DayAheadOrdersInputDataset, DayAheadOrdersResult]):
    def get_parameters_class(self):
        return DayAheadOrdersParameters

    def import_data(self, input_data: AtlasDataset, parameters: DayAheadOrdersParameters) -> DayAheadOrdersInputDataset:
        """Imports data using business objects and parameters."""
        return DayAheadOrdersInputDataset(
            input_data.set_frequency_all(parameters.temporal.timestep, inplace=True), parameters
        )

    def validate_data(self, parameters: DayAheadOrdersParameters, input_dataset: DayAheadOrdersInputDataset) -> bool:
        """Validates imported or generated data."""
        return True

    def validates_results(
        self,
        parameters: DayAheadOrdersParameters,
        input_dataset: DayAheadOrdersInputDataset,
        result: DayAheadOrdersResult,
    ) -> bool:
        """Validates results"""
        return True

    def export_results(
        self,
        parameters: DayAheadOrdersParameters,
        input_dataset: DayAheadOrdersInputDataset,
        result: DayAheadOrdersResult,
    ) -> None:
        """Exports results."""
        pass

    def execute(
        self, parameters: DayAheadOrdersParameters, input_dataset: DayAheadOrdersInputDataset
    ) -> DayAheadOrdersResult:
        """Executes the module's main logic."""
        cfg.logger.info("Initialization of the Day-Ahead Orders module...")
        result = DayAheadOrdersResult(input_dataset)

        orders_time = generate_datetimes(
            parameters.temporal.start_date, parameters.penultimate_date, parameters.temporal.timestep
        )

        if parameters.solver.export_lp:
            output_path = parameters.lp_dir
            output_path.mkdir(parents=True, exist_ok=True)

        if len(orders_time) == 0:
            cfg.logger.warning("The time window to formulate orders is empty.")
            return result

        cfg.logger.info("Extraction completed, now starting the formulation of orders...")

        steps: list[tuple[str, AbstractOrderStep]] = [
            ("load", LoadStep(result, orders_time, parameters)),
            ("non-dispatchable", NonDispatchableStep(result, orders_time, parameters)),
            ("storage", StorageStep(result, orders_time, parameters)),
            ("hydraulic", HydraulicStep(result, orders_time, parameters)),
            ("wind/pv", WindPVStep(result, orders_time, parameters)),
            ("thermic", ThermalBiddingStep(result, orders_time, parameters)),
        ]

        for name, step in steps:
            cfg.logger.info(f"Formulation of the {name} orders...")
            step_result = step.formulate()
            result.order.extend(step_result.orders)
            result.order_coupling.extend(step_result.order_couplings)
            cfg.logger.info(f"{name.capitalize()} orders formulated.")

        cfg.logger.info("Formulation of orders successfully completed.")
        return result

    @staticmethod
    def get_business_model_class_used() -> Iterable[BusinessModelName]:
        return [
            BusinessModelName.CONTROL_BLOCK,
            BusinessModelName.MARKET_AREA,
            BusinessModelName.MARKET_BORDER,
            BusinessModelName.NODE,
            BusinessModelName.PORTFOLIO,
            BusinessModelName.WIND,
            BusinessModelName.STORAGE,
            BusinessModelName.HYDRO,
            BusinessModelName.SOLAR,
            BusinessModelName.THERMAL,
            BusinessModelName.LOAD,
            BusinessModelName.ORDER,
            BusinessModelName.ORDER_COUPLING,
        ]
