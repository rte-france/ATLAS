"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

import atlas.config as cfg
from atlas.modules.day_ahead_orders.input_objects.storage import StorageDAO
from atlas.modules.day_ahead_orders.steps.abstract_step import AbstractOrderStep, StepResult
from atlas.modules.day_ahead_orders.steps.storage.optimisation import (
    StorageOptimisationResult,
    optimize_single_storage,
)
from atlas.modules.day_ahead_orders.steps.storage.orders import build_storage_bids
from atlas.timing import generate_datetimes


class StorageStep(AbstractOrderStep):
    def formulate(self) -> StepResult:
        local_timewindow = generate_datetimes(
            self.parameters.temporal.start_date,
            self.parameters.penultimate_date,
            self.parameters.temporal.timestep,
        )
        result = StepResult()

        for storage, unit_result in self.run_units(
            self.dataset.storage,
            optimize_single_storage,
            self.parameters,
            local_timewindow,
            label="storage",
        ):
            self._process_unit_result(result, unit_result, storage, local_timewindow)

        return result

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
