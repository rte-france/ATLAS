"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from concurrent.futures import ProcessPoolExecutor, as_completed

import atlas.config as cfg
from atlas.modules.day_ahead_orders.orders_formulation.storage_worker import optimize_single_storage
from atlas.modules.day_ahead_orders.output_dataset import DayAheadOrdersOutput
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters


class StorageStep:
    def __init__(self, dataset: DayAheadOrdersOutput, parameters: DayAheadOrdersParameters) -> None:
        """
        :param dataset: the dataset
        :type dataset: DayAheadOrdersOutput
        :param parameters: the parameters
        :type parameters: DayAheadOrdersParameters
        :return: None
        """
        self.dataset = dataset
        self.parameters = parameters

    def formulate_storage_orders(self) -> None:
        """
        Formulates storage bids on the spot market.
        Uses the parameters specified by the user and the dataset to create bids based on the forecast
        stored in the Power forecasting matrix of a "Storage" equipment.

        Supports both sequential and parallel processing based on use_multiprocessing parameter.
        :return: None
        """
        if self.parameters.use_multiprocessing:
            self._formulate_storage_orders_parallel()
        else:
            self._formulate_storage_orders_sequential()

    def _formulate_storage_orders_parallel(self) -> None:
        """
        Formulate storage orders using multiprocessing for parallel execution.
        """
        cfg.logger.info(f"Starting parallel storage optimization for {len(self.dataset.storage)} units")

        with ProcessPoolExecutor(max_workers=self.parameters.max_workers) as executor:
            future_to_storage = {
                executor.submit(optimize_single_storage, storage, self.parameters): storage.name
                for storage in self.dataset.storage
            }

            for future in as_completed(future_to_storage):
                storage_name = future_to_storage[future]
                try:
                    result = future.result()

                    if result.success:
                        # Add orders and couplings to the dataset
                        self.dataset.order.extend(result.orders)
                        self.dataset.order_coupling.extend(result.order_couplings)

                        # Update the storage unit in the dataset with submitted volumes and variable cost
                        for storage in self.dataset.storage:
                            if storage.name == result.storage_name:
                                if storage.da_buy_submitted_volume is None:
                                    storage.da_buy_submitted_volume = result.buy_submitted_volumes
                                else:
                                    storage.da_buy_submitted_volume += result.buy_submitted_volumes

                                if storage.da_sell_submitted_volume is None:
                                    storage.da_sell_submitted_volume = result.sell_submitted_volumes
                                else:
                                    storage.da_sell_submitted_volume += result.sell_submitted_volumes

                                if result.variable_cost is not None:
                                    storage.variable_cost = result.variable_cost
                                break

                        cfg.logger.info(f"Completed optimization for storage: {storage_name}")
                    else:
                        cfg.logger.warning(f"Optimization skipped or failed for storage: {storage_name}")

                except Exception as e:
                    cfg.logger.error(f"Error processing storage {storage_name}: {e}")

    def _formulate_storage_orders_sequential(self) -> None:
        """
        Formulate storage orders using sequential processing.
        """
        cfg.logger.info(f"Starting sequential storage optimization for {len(self.dataset.storage)} units")

        for storage in self.dataset.storage:
            result = optimize_single_storage(storage, self.parameters)

            if result.success:
                # Add orders and couplings to the dataset
                self.dataset.order.extend(result.orders)
                self.dataset.order_coupling.extend(result.order_couplings)

                # Update the storage unit in the dataset with submitted volumes and variable cost
                if storage.da_buy_submitted_volume is None:
                    storage.da_buy_submitted_volume = result.buy_submitted_volumes
                else:
                    storage.da_buy_submitted_volume += result.buy_submitted_volumes

                if storage.da_sell_submitted_volume is None:
                    storage.da_sell_submitted_volume = result.sell_submitted_volumes
                else:
                    storage.da_sell_submitted_volume += result.sell_submitted_volumes

                if result.variable_cost is not None:
                    storage.variable_cost = result.variable_cost

                cfg.logger.info(f"Completed optimization for storage: {storage.name}")
            else:
                cfg.logger.warning(f"Optimization skipped or failed for storage: {storage.name}")
