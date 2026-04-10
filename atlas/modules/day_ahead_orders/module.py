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
from atlas.modules.day_ahead_orders.steps.hydraulic_step import HydraulicStep
from atlas.modules.day_ahead_orders.steps.load_step import LoadStep
from atlas.modules.day_ahead_orders.steps.non_dispatchable_step import NonDispatchableStep
from atlas.modules.day_ahead_orders.steps.storage.storage_step import StorageStep
from atlas.modules.day_ahead_orders.steps.thermal.thermal_bidding_step import ThermalBiddingStep
from atlas.modules.day_ahead_orders.steps.wind_pv_step import WindPVStep
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
        self, parameters: DayAheadOrdersParameters, dataset: DayAheadOrdersInputDataset
    ) -> DayAheadOrdersOutput:
        """Executes the module's main logic."""
        cfg.logger.info("Initialization of the Day-Ahead Orders module...")
        output_dataset = DayAheadOrdersOutput(dataset)

        orders_time = generate_datetimes(
            parameters.temporal.start_date, parameters.penultimate_date, parameters.temporal.timestep
        )

        # ensure output folder exists
        if parameters.solver.export_lp:
            output_path = parameters.get_output_dir() / "lp_export"
            output_path.mkdir(parents=True, exist_ok=True)

        if len(orders_time) > 0:
            cfg.logger.info("Extraction completed, now starting the formulation of orders...")

            cfg.logger.info("Formulation of the load orders...")
            LoadStep.formulate_load_orders(output_dataset, orders_time, parameters)
            cfg.logger.info("Consumption orders formulated.")

            cfg.logger.info("Formulation of the non-dispatchable orders...")
            NonDispatchableStep.formulate_non_dispatchable_orders(output_dataset, orders_time, parameters)
            cfg.logger.info("Non-dispatchable orders formulated.")

            cfg.logger.info("Formulation of the storage orders...")
            storage = StorageStep(output_dataset, parameters)
            storage.formulate_storage_orders()
            cfg.logger.info("Storage orders formulated.")

            cfg.logger.info("Formulation of the hydraulic orders...")
            HydraulicStep.formulate_hydraulic_orders(output_dataset, orders_time, parameters)
            cfg.logger.info("Hydraulic orders formulated.")

            cfg.logger.info("Formulation of the wind/pv orders...")
            WindPVStep.formulate_wind_and_pv_orders(output_dataset, orders_time, parameters)
            cfg.logger.info("wind/pv orders formulated.")

            cfg.logger.info("Formulation of the thermic orders...")
            thermal_bidding = ThermalBiddingStep(output_dataset, orders_time, parameters)
            thermal_bidding.formulate_thermal_orders()
            cfg.logger.info("Thermic orders formulated.")

            cfg.logger.info("Formulation of orders successfully completed.")
        else:
            cfg.logger.warning("The time window to formulate orders is empty.")

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
