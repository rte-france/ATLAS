"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed

from pendulum import DateTime

import atlas.config as cfg
from atlas.modules.day_ahead_orders.input_objects.storage import StorageDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.steps.abstract_step import AbstractBiddingStep
from atlas.modules.day_ahead_orders.steps.result import BiddingResult
from atlas.modules.day_ahead_orders.steps.storage.optimisation_result import StorageOptimisationResult
from atlas.modules.day_ahead_orders.steps.storage.orders import StorageOrders
from atlas.timing import generate_datetimes


class StorageBidding(AbstractBiddingStep):
    def formulate(self) -> BiddingResult:
        local_timewindow = generate_datetimes(
            self.parameters.temporal.start_date,
            self.parameters.penultimate_date,
            self.parameters.temporal.timestep,
        )
        if self.parameters.multiprocessing.enable:
            return self._formulate_parallel(local_timewindow)
        return self._formulate_sequential(local_timewindow)

    def _process_unit_result(
        self,
        result: BiddingResult,
        raw: StorageOptimisationResult | None,
        storage: StorageDAO,
        local_timewindow: list[DateTime],
    ) -> None:
        if raw is None:
            cfg.logger.warning(f"Optimization skipped or failed for storage: {storage.name}")
            return

        storage_orders = StorageOrders(self.parameters, local_timewindow)
        orders, couplings = storage_orders.build_orders(storage, raw)
        result.orders.extend(orders)
        result.order_couplings.extend(couplings)

        buy_volumes, sell_volumes = storage_orders.compute_submitted_volumes(raw)

        if storage.da_buy_submitted_volume is None:
            storage.da_buy_submitted_volume = buy_volumes
        else:
            storage.da_buy_submitted_volume += buy_volumes

        if storage.da_sell_submitted_volume is None:
            storage.da_sell_submitted_volume = sell_volumes
        else:
            storage.da_sell_submitted_volume += sell_volumes

        storage.variable_cost = storage_orders.compute_variable_cost(storage, raw)
        cfg.logger.info(f"Completed optimization for storage: {storage.name}")

    def _formulate_parallel(self, local_timewindow: list[DateTime]) -> BiddingResult:
        cfg.logger.info(f"Starting parallel storage optimization for {len(self.dataset.storage)} units")
        result = BiddingResult()
        storage_by_name = {storage.name: storage for storage in self.dataset.storage}

        with ProcessPoolExecutor(max_workers=self.parameters.multiprocessing.max_workers) as executor:
            future_to_name = {
                executor.submit(optimize_single_storage, storage, self.parameters, local_timewindow): storage.name
                for storage in self.dataset.storage
            }

            for future in as_completed(future_to_name):
                storage_name = future_to_name[future]
                try:
                    raw = future.result()
                    self._process_unit_result(result, raw, storage_by_name[storage_name], local_timewindow)
                except Exception as e:
                    cfg.logger.error(f"Error processing storage {storage_name}: {e}")

        return result

    def _formulate_sequential(self, local_timewindow: list[DateTime]) -> BiddingResult:
        cfg.logger.info(f"Starting sequential storage optimization for {len(self.dataset.storage)} units")
        result = BiddingResult()

        for storage in self.dataset.storage:
            raw = optimize_single_storage(storage, self.parameters, local_timewindow)
            self._process_unit_result(result, raw, storage, local_timewindow)

        return result


def optimize_single_storage(
    storage: StorageDAO,
    parameters: DayAheadOrdersParameters,
    local_timewindow: list[DateTime],
) -> StorageOptimisationResult | None:
    """
    Worker function for storage LP solve.

    Runs the LP via :class:`StorageOrders` and returns the raw solver output.
    Returns ``None`` when the unit should be skipped (zero capacity) or on failure.
    Order building is deferred to the main process.

    :param storage: Storage unit to optimise.
    :param parameters: Optimisation parameters.
    :param local_timewindow: Timesteps within the local optimisation window.
    :return: Raw LP output, or ``None`` if the unit was skipped or failed.
    """
    try:
        local_max_energy = storage.maximum_energy.filter(item=local_timewindow, inplace=False).max()
        if local_max_energy <= 0:
            cfg.logger.debug(f"Equipment {storage.name} avoided, as its maximum_energy is 0")
            return None

        cfg.logger.debug(f"Optimizing storage equipment {storage.name}")
        return StorageOrders(parameters, local_timewindow).solve(storage)

    except Exception as e:
        cfg.logger.error(f"Optimization failed for storage {storage.name}: {e}")
        return None
