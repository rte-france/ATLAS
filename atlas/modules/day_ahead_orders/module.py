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
from atlas.modules.day_ahead_orders.output_dataset import DayAheadOrdersOutput
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.steps.abstract_step import AbstractBiddingStep
from atlas.modules.day_ahead_orders.steps.hydro import HydraulicBidding
from atlas.modules.day_ahead_orders.steps.load import LoadBidding
from atlas.modules.day_ahead_orders.steps.non_dispatchable import NonDispatchableBidding
from atlas.modules.day_ahead_orders.steps.renewables import WindPVBidding
from atlas.modules.day_ahead_orders.steps.storage.bidding import StorageBidding
from atlas.modules.day_ahead_orders.steps.thermal.thermal_bidding import ThermalBidding
from atlas.timing import generate_datetimes


class DayAheadOrdersModule(AbstractModule[DayAheadOrdersParameters, DayAheadOrdersInputDataset, DayAheadOrdersOutput]):
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
        output_dataset: DayAheadOrdersOutput,
    ) -> bool:
        """Validates results"""
        return True

    def export_results(
        self,
        parameters: DayAheadOrdersParameters,
        input_dataset: DayAheadOrdersInputDataset,
        output_dataset: DayAheadOrdersOutput,
    ) -> None:
        """Exports results."""
        pass

    def execute(
        self, parameters: DayAheadOrdersParameters, input_dataset: DayAheadOrdersInputDataset
    ) -> DayAheadOrdersOutput:
        """Executes the module's main logic."""
        cfg.logger.info("Initialization of the Day-Ahead Orders module...")
        output_dataset = DayAheadOrdersOutput(input_dataset)

        orders_time = generate_datetimes(
            parameters.temporal.start_date, parameters.penultimate_date, parameters.temporal.timestep
        )

        if parameters.solver.export_lp:
            output_path = parameters.get_lp_dir()
            output_path.mkdir(parents=True, exist_ok=True)

        if len(orders_time) == 0:
            cfg.logger.warning("The time window to formulate orders is empty.")
            return output_dataset

        cfg.logger.info("Extraction completed, now starting the formulation of orders...")

        steps: list[tuple[str, AbstractBiddingStep]] = [
            ("load", LoadBidding(output_dataset, orders_time, parameters)),
            ("non-dispatchable", NonDispatchableBidding(output_dataset, orders_time, parameters)),
            ("storage", StorageBidding(output_dataset, orders_time, parameters)),
            ("hydraulic", HydraulicBidding(output_dataset, orders_time, parameters)),
            ("wind/pv", WindPVBidding(output_dataset, orders_time, parameters)),
            ("thermic", ThermalBidding(output_dataset, orders_time, parameters)),
        ]

        for name, step in steps:
            cfg.logger.info(f"Formulation of the {name} orders...")
            step_result = step.formulate()
            output_dataset.order.extend(step_result.orders)
            output_dataset.order_coupling.extend(step_result.order_couplings)
            cfg.logger.info(f"{name.capitalize()} orders formulated.")

        cfg.logger.info("Formulation of orders successfully completed.")
        return output_dataset

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
