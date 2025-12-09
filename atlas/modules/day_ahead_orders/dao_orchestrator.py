import pendulum

import atlas.config as cfg
from atlas.modules.day_ahead_orders.dao_input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.dao_output_dataset import DayAheadOrdersOutputDataset
from atlas.modules.day_ahead_orders.dao_parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.orders_formulation.dao_load import DAOLoad
from atlas.modules.day_ahead_orders.orders_formulation.dao_storage import DAOStorage
from atlas.modules.day_ahead_orders.orders_formulation.hydraulic import Hydraulic
from atlas.modules.day_ahead_orders.orders_formulation.non_dispatchable import NonDispatchable
from atlas.modules.day_ahead_orders.orders_formulation.thermal.thermal_bidding import ThermalBidding
from atlas.modules.day_ahead_orders.orders_formulation.wind_pv import WindPV
from atlas.timing import generate_datetimes


class DayAheadOrdersOrchestrator:
    def __init__(self, parameters: DayAheadOrdersParameters, dataset: DayAheadOrdersInputDataset):
        self.parameters = parameters
        self.dataset = dataset
        pass

    def execute(self) -> DayAheadOrdersOutputDataset:
        # Formulation of bids and orders on the day-ahead market.
        # In practice, several functions are run. Each function extract data from the dataset
        # and formulates bids or offers in the output dataset. The latter is of class "Offer".

        cfg.logger.info("Initialization of the Day-Ahead Orders module...")

        # Create the sequence of orders times. In particular, this sequence is such that the endDate of the last order will be before
        # the endDate of the overall time frame.
        orders_time = self._define_orders_time()
        if len(orders_time) > 0:
            cfg.logger.info("Extraction completed, now starting the formulation of orders...")

            #### STEP 1 - CONSUMPTION ####
            cfg.logger.info("Formulation of the load orders...")
            DAOLoad.formulate_load_orders(self.dataset, orders_time, self.parameters)
            cfg.logger.info("Consumption orders formulated.")

            #### STEP 2 - NON DISPATCHABLE UNITS ####
            cfg.logger.info("Formulation of the non-dispatchable orders...")
            NonDispatchable.formulate_non_dispatchable_orders(self.dataset, orders_time, self.parameters)
            cfg.logger.info("Non-dispatchable orders formulated.")

            #### STEP 3 - STORAGE UNITS ####
            cfg.logger.info("Formulation of the storage orders...")
            DAOStorage.formulate_storage_orders(self.dataset, self.parameters)
            cfg.logger.info("Storage orders formulated.")

            #### STEP 4 - LAKES UNITS ####
            cfg.logger.info("Formulation of the hydraulic orders...")
            Hydraulic.formulate_hydraulic_orders(self.dataset, orders_time, self.parameters)
            cfg.logger.info("Hydraulic orders formulated.")

            #### STEP 5 - WIND AND PV UNITS ####
            cfg.logger.info("Formulation of the wind/pv orders...")
            WindPV.formulate_wind_and_pv_orders(self.dataset, orders_time, self.parameters)
            cfg.logger.info("wind/pv orders formulated.")

            #### STEP 6 - THERMIC UNITS ####
            cfg.logger.info("Formulation of the thermic orders...")
            ThermalBidding.formulate_thermal_orders(self.dataset, orders_time, self.parameters)
            cfg.logger.info("Thermic orders formulated.")

            cfg.logger.info("Formulation of orders successfully completed.")

            # TODO
            return None
        else:
            cfg.logger.error("orders_time is empty.")

    def _define_orders_time(self) -> list[pendulum.DateTime]:
        """
        This function creates a sequence of timestamps between a start_date and a end_date
        with step deltaTime. It returns a list of DateTime objects.
        In particular, it makes sure that no time step crosses the end_date boundary.

        Arguments:
        - `parameters` an instance of DayAheadOrdersParameters.
        """
        orders_time = []
        if self.parameters.start_date < self.parameters.end_date:
            orders_time = generate_datetimes(
                self.parameters.start_date, self.parameters.penultimate_date, self.parameters.time_step
            )
        else:
            msg = "The end_date parameter must be posterior to the start_date parameter."
            cfg.logger.error(msg)
        return orders_time
