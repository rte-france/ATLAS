"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import atlas.config as cfg
from atlas import BusinessModel
from atlas.abstract_class.abstract_module import AbstractModule
from atlas.abstract_class.abstract_parameters import module_parameters_type_var
from atlas.modules.day_ahead_orders.day_ahead_orders_input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.day_ahead_orders_output_dataset import DayAheadOrdersOutputDataset
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.orders_formulation.dao_load import DAOLoad
from atlas.modules.day_ahead_orders.orders_formulation.dao_storage import DAOStorage
from atlas.modules.day_ahead_orders.orders_formulation.hydraulic import Hydraulic
from atlas.modules.day_ahead_orders.orders_formulation.non_dispatchable import NonDispatchable
from atlas.modules.day_ahead_orders.orders_formulation.thermic_bidding import ThermicBidding
from atlas.modules.day_ahead_orders.orders_formulation.wind_pv import WindPV
from atlas.timing import generate_datetimes
from atlas.modules.day_ahead_orders.tools.Utilities import Utilities


class DayAheadOrdersModule(
    AbstractModule[DayAheadOrdersParameters, DayAheadOrdersInputDataset, DayAheadOrdersOutputDataset]
):
    def get_parameters_class(self) -> type[module_parameters_type_var]:
        return DayAheadOrdersParameters

    def import_data(
        self, raw_data: dict[str, list[type[BusinessModel]]], parameters: DayAheadOrdersParameters
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
        return True

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
        orders_time = self._define_orders_time(parameters)
        if len(orders_time) > 0:
            cfg.logger.info("Extraction completed, now starting the formulation of orders...")

            #### STEP 1 - CONSUMPTION ####
            cfg.logger.info("Formulation of the load orders...")
            DAOLoad.formulate_load_orders(dataset, orders_time, parameters)
            cfg.logger.info("Consumption orders formulated.")

            #### STEP 2 - NON DISPATCHABLE UNITS ####
            cfg.logger.info("Formulation of the non-dispatchable orders...")
            NonDispatchable.formulate_non_dispatchable_orders(dataset, orders_time, parameters)
            cfg.logger.info("Non-dispatchable orders formulated.")

            #### STEP 3 - STORAGE UNITS ####
            cfg.logger.info("Formulation of the storage orders...")
            DAOStorage.formulate_storage_orders(dataset, parameters)
            cfg.logger.info("Storage orders formulated.")

            #### STEP 4 - LAKES UNITS ####
            cfg.logger.info("Formulation of the hydraulic orders...")
            Hydraulic.formulate_hydraulic_orders(dataset, orders_time, parameters)
            cfg.logger.info("Hydraulic orders formulated.")

            #### STEP 5 - WIND AND PV UNITS ####
            cfg.logger.info("Formulation of the wind/pv orders...")
            WindPV.formulate_wind_and_pv_orders(dataset, orders_time, parameters)
            cfg.logger.info("wind/pv orders formulated.")

            #### STEP 6 - THERMIC UNITS ####
            cfg.logger.info("Formulation of the thermic orders...")
            ThermicBidding.formulate_thermic_orders(dataset, orders_time, parameters)
            cfg.logger.info("Thermic orders formulated.")

            #### STEP - INDICATE TO THE USER THAT THE FORMULATION OF ORDERS IS COMPLETED.
            cfg.logger.info("Formulation of orders successfully completed.")

            # return output_dataset
        else:
            cfg.logger.error("orders_time is empty.")
        return DayAheadOrdersOutputDataset(dataset)

    def _define_orders_time(self, parameters: DayAheadOrdersParameters) -> list[DateTime]:
        """
        This function creates a sequence of timestamps between a start_date and a end_date
        with step deltaTime. It returns a list of DateTime objects.
        In particular, it makes sure that no time step crosses the end_date boundary.

        Arguments:
        - `parameters` an instance of DayAheadOrdersParameters.
        """
        orders_time = []
        if parameters.start_date < parameters.end_date:
            orders_time = generate_datetimes(
                parameters.start_date, parameters.end_date - parameters.time_step, parameters.time_step
            )
        else:
            msg = "The end_date parameter must be posterior to the start_date parameter."
            cfg.logger.error(msg)
        return orders_time
