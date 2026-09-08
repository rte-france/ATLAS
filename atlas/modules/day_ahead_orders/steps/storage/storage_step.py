"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from concurrent.futures import ProcessPoolExecutor, as_completed

from pendulum import DateTime

import atlas.config as cfg
from atlas.modules.day_ahead_orders.input_objects.storage import StorageDAO
from atlas.modules.day_ahead_orders.steps.abstract_step import AbstractOrderStep, StepResult
from atlas.modules.day_ahead_orders.steps.storage.orders import build_storage_bids
from atlas.modules.day_ahead_orders.steps.storage.storage_worker import (
    StorageOptimisationResult,
    optimize_single_storage,
)
from atlas.timing import generate_datetimes


class StorageStep(AbstractOrderStep):
    def formulate(self) -> StepResult:
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
        result: StepResult,
        unit_result: StorageOptimisationResult | None,
        storage: StorageDAO,
        local_timewindow: list[DateTime],
    ) -> None:
        """Build the orders of a solved unit and merge them into the step result."""
        if unit_result is None:
            cfg.logger.warning(f"Optimization skipped or failed for storage: {storage.name}")
            return

        bids = build_storage_bids(storage, unit_result, self.parameters, local_timewindow)
        result.orders.extend(bids.orders)
        result.order_couplings.extend(bids.order_couplings)

        if storage.da_buy_submitted_volume is None:
            storage.da_buy_submitted_volume = bids.buy_submitted_volume
        else:
            storage.da_buy_submitted_volume = storage.da_buy_submitted_volume.add_on_union(
                bids.buy_submitted_volume, inplace=False
            )

        if storage.da_sell_submitted_volume is None:
            storage.da_sell_submitted_volume = bids.sell_submitted_volume
        else:
            storage.da_sell_submitted_volume = storage.da_sell_submitted_volume.add_on_union(
                bids.sell_submitted_volume, inplace=False
            )

        storage.variable_cost = bids.variable_cost

        cfg.logger.info(f"Completed optimization for storage: {storage.name}")

    def _formulate_parallel(self, local_timewindow: list[DateTime]) -> StepResult:
        cfg.logger.info(f"Starting parallel storage optimization for {len(self.dataset.storage)} units")
        result = StepResult()
        storage_by_name = {storage.name: storage for storage in self.dataset.storage}

        with ProcessPoolExecutor(max_workers=self.parameters.multiprocessing.max_workers) as executor:
            future_to_storage = {
                executor.submit(optimize_single_storage, storage, self.parameters, local_timewindow): storage.name
                for storage in self.dataset.storage
            }

            for future in as_completed(future_to_storage):
                storage_name = future_to_storage[future]
                try:
                    self._process_unit_result(result, future.result(), storage_by_name[storage_name], local_timewindow)
                except Exception as e:
                    cfg.logger.error(f"Error processing storage {storage_name}: {e}")

        return result

    def _formulate_sequential(self, local_timewindow: list[DateTime]) -> StepResult:
        cfg.logger.info(f"Starting sequential storage optimization for {len(self.dataset.storage)} units")
        result = StepResult()

        for storage in self.dataset.storage:
            unit_result = optimize_single_storage(storage, self.parameters, local_timewindow)
            self._process_unit_result(result, unit_result, storage, local_timewindow)

        return result
