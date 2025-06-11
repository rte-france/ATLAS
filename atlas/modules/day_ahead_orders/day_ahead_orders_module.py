"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Any

import atlas.config as cfg
from atlas import BusinessModel
from atlas.abstract_class.abstract_module import AbstractModule
from atlas.modules.day_ahead_orders.day_ahead_orders_input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.day_ahead_orders_output_dataset import DayAheadOrdersOutputDataset
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.orders_formulation.day_ahead_load import DayAheadLoad
from atlas.modules.day_ahead_orders.orders_formulation.day_ahead_storage import DayAheadStorage
from atlas.modules.day_ahead_orders.orders_formulation.non_dispatchable import NonDispatchable
from atlas.modules.day_ahead_orders.tools.Utilities import Utilities


class DayAheadOrdersModule(
    AbstractModule[DayAheadOrdersParameters, DayAheadOrdersInputDataset, DayAheadOrdersOutputDataset]
):
    def create_parameters(self, raw_params: dict[str, Any]) -> DayAheadOrdersParameters:
        """Creates a concrete parameters object from raw dictionary."""
        return DayAheadOrdersParameters(**raw_params)

    def import_data(
        self, raw_data: dict[str, list[BusinessModel]], parameters: DayAheadOrdersParameters
    ) -> DayAheadOrdersInputDataset:
        """Imports data using business objects and parameters."""
        return DayAheadOrdersInputDataset(raw_data, parameters)

    def validate_data(self, parameters: DayAheadOrdersParameters, input_dataset: DayAheadOrdersInputDataset) -> bool:
        """Validates imported or generated data."""
        return True

    def validates_results(
        self,
        parameters: DayAheadOrdersParameters,
        input_dataset: DayAheadOrdersInputDataset,
        output_dataset: DayAheadOrdersOutputDataset,
    ) -> bool:
        """Validates results"""
        pass

    def export_results(
        self,
        parameters: DayAheadOrdersParameters,
        input_dataset: DayAheadOrdersInputDataset,
        output_dataset: DayAheadOrdersOutputDataset,
    ) -> None:
        """Exports results."""
        pass

    def execute(
        self, parameters: DayAheadOrdersParameters, dataset: DayAheadOrdersInputDataset
    ) -> DayAheadOrdersOutputDataset:
        """Executes the module's main logic."""

        # Formulation of bids and orders on the day-ahead market.
        # In practice, several functions are run. Each function extract data from the input marker
        # and formulates bids or offers in the output marker. The latter is of class "Offer".

        #### STEP 0 - INITIALIZATION ####
        cfg.logger.info("Initialization of the Day-Ahead Orders module...")

        # Create the sequence of orders times. In particular, this sequence is such that the endDate of the last order will be before
        # the endDate of the overall time frame.
        orders_time = Utilities.define_orders_time(parameters)
        if len(orders_time) > 0:
            cfg.logger.info("Extraction completed, now starting the formulation of orders...")

            #### STEP 1 - CONSUMPTION ####
            cfg.logger.info("Formulation of the load orders...")
            DayAheadLoad.formulate_load_orders(dataset, orders_time, parameters)
            cfg.logger.info("Consumption orders formulated.")

            #### STEP 2 - NON DISPATCHABLE UNITS ####
            cfg.logger.info("Formulation of the non-dispatchable orders...")
            NonDispatchable.formulate_non_dispatchable_orders(dataset, orders_time, parameters)
            cfg.logger.info("Non-dispatchable orders formulated.")

            #### STEP 3 - STORAGE UNITS ####
            cfg.logger.info("Formulation of the storage orders...")
            DayAheadStorage.formulate_storage_orders(dataset, parameters)
            cfg.logger.info("Storage orders formulated.")

            """
            #### STEP 4 - LAKES UNITS ####
            API.IO.Trace.Log("Formulation of the hydraulic orders...", API.IO.LogTypeInfo)
            hydraulic.formulate_hydraulic_orders(input_dataset, output_dataset, orders_time, parameters)
            API.IO.Trace.Log("Hydraulic orders formulated.", API.IO.LogTypeInfo)

            #### STEP 5 - WIND AND PV UNITS ####
            API.IO.Trace.Log("Formulation of the wind/pv orders...", API.IO.LogTypeInfo)
            wind_pv.formulate_wind_and_pv_orders(input_dataset, output_dataset, orders_time, parameters)
            API.IO.Trace.Log("Non-dispatchable orders formulated.", API.IO.LogTypeInfo)

            #### STEP 6 - THERMIC UNITS ####
            API.IO.Trace.Log("Formulation of the thermic orders...", API.IO.LogTypeInfo)
            thermic_bidding.formulate_thermic_orders(input_dataset, output_dataset, orders_time, parameters)
            API.IO.Trace.Log("Thermic orders formulated.", API.IO.LogTypeInfo)

            #### STEP - INDICATE TO THE USER THAT THE FORMULATION OF ORDERS IS COMPLETED.
            API.IO.Trace.Log("Formulation of orders successfully completed.", API.IO.LogTypeInfo)
            """
            # return output_dataset
        else:
            cfg.logger.error("orders_time is empty.")
