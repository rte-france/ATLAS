"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import atlas.config as cfg
from atlas.modules.day_ahead_orders.input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.orders_formulation.hydraulic_step import HydraulicStep
from atlas.modules.day_ahead_orders.orders_formulation.load_step import LoadStep
from atlas.modules.day_ahead_orders.orders_formulation.non_dispatchable_step import NonDispatchableStep
from atlas.modules.day_ahead_orders.orders_formulation.storage_step import StorageStep
from atlas.modules.day_ahead_orders.orders_formulation.thermal_bidding_step import ThermalBiddingStep
from atlas.modules.day_ahead_orders.orders_formulation.wind_pv_step import WindPVStep
from atlas.modules.day_ahead_orders.output_dataset import DayAheadOrdersOutput
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.timing import generate_datetimes


class DayAheadOrdersOrchestrator:
    def __init__(self, parameters: DayAheadOrdersParameters, dataset: DayAheadOrdersInputDataset):
        """
        :param parameters: the parameters
        :type parameters: DayAheadOrdersParameters
        :param dataset: the input dataset
        :type dataset: DayAheadOrdersInputDataset
        """
        self.parameters = parameters
        self.input_dataset = dataset
        self.output_dataset = DayAheadOrdersOutput(dataset)

    def execute(self) -> DayAheadOrdersOutput:
        """
        Formulation of bids and orders on the day-ahead market.
        In practice, several functions are run. Each function extract data from the dataset
        and formulates bids or offers in the output dataset. The latter is of class "Offer".
        :return: the output dataset
        :rtype: DayAheadOrdersOutput
        """

        cfg.logger.info("Initialization of the Day-Ahead Orders module...")

        # Create the sequence of orders times. In particular, this sequence is such that the end date of the last order will be before
        # the end date of the overall time frame.
        orders_time = generate_datetimes(
            self.parameters.date.start_date, self.parameters.penultimate_date, self.parameters.date.timestep
        )

        # ensure output folder exists
        if self.parameters.solver.export_lp:
            path = self.parameters.get_output_dir() / "lp_exports"
            path.mkdir(parents=True, exist_ok=True)

        if len(orders_time) > 0:
            cfg.logger.info("Extraction completed, now starting the formulation of orders...")

            #### STEP 1 - CONSUMPTION ####
            cfg.logger.info("Formulation of the load orders...")
            LoadStep.formulate_load_orders(self.output_dataset, orders_time, self.parameters)
            cfg.logger.info("Consumption orders formulated.")

            #### STEP 2 - NON DISPATCHABLE UNITS ####
            cfg.logger.info("Formulation of the non-dispatchable orders...")
            NonDispatchableStep.formulate_non_dispatchable_orders(self.output_dataset, orders_time, self.parameters)
            cfg.logger.info("Non-dispatchable orders formulated.")

            #### STEP 3 - STORAGE UNITS ####
            cfg.logger.info("Formulation of the storage orders...")
            storage = StorageStep(self.output_dataset, self.parameters)
            storage.formulate_storage_orders()
            cfg.logger.info("Storage orders formulated.")

            #### STEP 4 - LAKES UNITS ####
            cfg.logger.info("Formulation of the hydraulic orders...")
            HydraulicStep.formulate_hydraulic_orders(self.output_dataset, orders_time, self.parameters)
            cfg.logger.info("Hydraulic orders formulated.")

            #### STEP 5 - WIND AND PV UNITS ####
            cfg.logger.info("Formulation of the wind/pv orders...")
            WindPVStep.formulate_wind_and_pv_orders(self.output_dataset, orders_time, self.parameters)
            cfg.logger.info("wind/pv orders formulated.")

            #### STEP 6 - THERMAL UNITS ####
            cfg.logger.info("Formulation of the thermic orders...")
            thermal_bidding = ThermalBiddingStep(self.output_dataset, orders_time, self.parameters)
            thermal_bidding.formulate_thermal_orders()
            cfg.logger.info("Thermic orders formulated.")

            cfg.logger.info("Formulation of orders successfully completed.")
        else:
            cfg.logger.error("orders_time is empty.")

        return self.output_dataset
