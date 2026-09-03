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
from atlas.modules.day_ahead_orders.steps.storage.storage_worker import (
    StorageOptimizationResult,
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
        self, result: StepResult, unit_result: StorageOptimizationResult, storage: StorageDAO
    ) -> None:
        if unit_result.success:
            result.orders.extend(unit_result.orders)
            result.order_couplings.extend(unit_result.order_couplings)

            if storage.da_buy_submitted_volume is None:
                storage.da_buy_submitted_volume = unit_result.buy_submitted_volumes
            else:
                storage.da_buy_submitted_volume = storage.da_buy_submitted_volume.add_on_union(
                    unit_result.buy_submitted_volumes, inplace=False
                )

            if storage.da_sell_submitted_volume is None:
                storage.da_sell_submitted_volume = unit_result.sell_submitted_volumes
            else:
                storage.da_sell_submitted_volume = storage.da_sell_submitted_volume.add_on_union(
                    unit_result.sell_submitted_volumes, inplace=False
                )

            if unit_result.variable_cost is not None:
                storage.variable_cost = unit_result.variable_cost

            cfg.logger.info(f"Completed optimization for storage: {storage.name}")
        else:
            cfg.logger.warning(f"Optimization skipped or failed for storage: {storage.name}")

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
                    unit_result = future.result()
                    self._process_unit_result(result, unit_result, storage_by_name[unit_result.storage_name])
                except Exception as e:
                    cfg.logger.error(f"Error processing storage {storage_name}: {e}")

        return result

    def _formulate_sequential(self, local_timewindow) -> StepResult:
        cfg.logger.info(f"Starting sequential storage optimization for {len(self.dataset.storage)} units")
        result = StepResult()

        for storage in self.dataset.storage:
            unit_result = optimize_single_storage(storage, self.parameters, local_timewindow)
            self._process_unit_result(result, unit_result, storage)

        return result
