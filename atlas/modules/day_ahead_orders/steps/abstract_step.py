"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pendulum import DateTime

import atlas.config as cfg
from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
from atlas.modules.day_ahead_orders.input_objects.order_coupling import OrderCouplingDAO
from atlas.modules.day_ahead_orders.output_dataset import DayAheadOrdersOutput
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.objects.equipment.equipment import Equipment

U = TypeVar("U", bound=Equipment)
R = TypeVar("R")


@dataclass
class StepResult:
    orders: list[OrderDAO] = field(default_factory=list)
    order_couplings: list[OrderCouplingDAO] = field(default_factory=list)


class AbstractOrderStep(ABC):
    def __init__(
        self,
        dataset: DayAheadOrdersOutput,
        orders_time: list[DateTime],
        parameters: DayAheadOrdersParameters,
    ) -> None:
        self.dataset = dataset
        self.orders_time = orders_time
        self.parameters = parameters

    @abstractmethod
    def formulate(self) -> StepResult:
        """Formulates orders for this step and returns them as a StepResult."""

    def run_units(
        self,
        units: Sequence[U],
        worker: Callable[..., R],
        *worker_args: Any,
        label: str = "unit",
    ) -> Iterator[tuple[U, R]]:
        """
        Run *worker* over *units* and yield ``(unit, result)`` pairs as they complete.

        Dispatches to a process pool or to a plain loop depending on
        ``parameters.multiprocessing``. The worker is called as ``worker(unit, *worker_args)``
        and must return a picklable result — building business objects inside it would send
        the whole equipment graph back through pickle, and the caller would end up handling
        copies rather than the dataset's own objects. The *unit* yielded is always the
        caller's instance, so it can be mutated in place.

        A unit whose worker raises is logged and skipped: one failing unit must not abort
        the whole session.

        :param units: Units to process
        :type units: Sequence[U]
        :param worker: Module-level function, called as ``worker(unit, *worker_args)``
        :type worker: Callable[..., R]
        :param worker_args: Extra arguments forwarded to every worker call
        :param label: Technology name, used in the log lines
        :type label: str
        :return: ``(unit, result)`` pairs, in completion order when parallel
        :rtype: Iterator[tuple[U, R]]
        """
        if not self.parameters.multiprocessing.enable:
            cfg.logger.info(f"Starting sequential {label} optimization for {len(units)} units")
            for unit in units:
                yield unit, worker(unit, *worker_args)
            return

        cfg.logger.info(f"Starting parallel {label} optimization for {len(units)} units")
        with ProcessPoolExecutor(max_workers=self.parameters.multiprocessing.max_workers) as executor:
            future_to_unit = {executor.submit(worker, unit, *worker_args): unit for unit in units}

            for future in as_completed(future_to_unit):
                unit = future_to_unit[future]
                try:
                    result = future.result()
                except Exception as e:
                    cfg.logger.error(f"Error processing {label} {unit.name}: {e}")
                    continue
                yield unit, result
