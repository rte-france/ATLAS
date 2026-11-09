"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from collections import defaultdict
from datetime import datetime
from itertools import combinations

import atlas.config as cfg
from atlas.enums import CouplingType, Product
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.steps.abstract_step import AbstractOrderStep, StepResult
from atlas.modules.day_ahead_orders.steps.thermal.thermal_worker import optimize_single_thermal_unit
from atlas.objects.equipment.thermal import Thermal


class ThermalBiddingStep(AbstractOrderStep):
    def formulate(self) -> StepResult:
        result = StepResult()

        for thermal, unit_result in self.run_units(
            self.dataset.thermal,
            optimize_single_thermal_unit,
            self.orders_time,
            self.parameters,
            label="thermal",
        ):
            result.orders.extend(unit_result.orders)
            result.order_couplings.extend(unit_result.order_couplings)
            cfg.logger.info(
                f"Completed order formulation for thermal unit: {thermal.name} ({unit_result.strategy.value})"
            )

        cfg.logger.info("Computing maximum sell volumes...")
        self._compute_da_sell_submitted_volume(result)
        cfg.logger.info("End of computation.")

        return result

    @staticmethod
    def _find_block(block_of: dict[str, str], order_name: str) -> str:
        """
        Return the name identifying the block of an order (union-find with path halving).

        :param block_of: Link from each order name to another order of its block
        :type block_of: dict[str, str]
        :param order_name: Name of the order
        :type order_name: str
        :return: Name identifying the block
        :rtype: str
        """
        block_of.setdefault(order_name, order_name)
        while block_of[order_name] != order_name:
            block_of[order_name] = block_of[block_of[order_name]]
            order_name = block_of[order_name]
        return order_name

    @staticmethod
    def _max_compatible_volume(block_volumes: dict[str, float], exclusive_blocks: dict[str, set[str]]) -> float:
        """
        Return the largest volume reachable at one time step by a set of blocks that do not exclude each other.

        **Example**

            exclusive = {"a": {"b"}, "b": {"a", "c"}, "c": {"b"}}
            _max_compatible_volume({"a": 100.0, "b": 150.0, "c": 70.0}, exclusive)  # 170.0 (a + c)

        :param block_volumes: Volume of each block active at this time step
        :type block_volumes: dict[str, float]
        :param exclusive_blocks: Blocks excluded by each block
        :type exclusive_blocks: dict[str, set[str]]
        :return: The largest compatible volume
        :rtype: float
        """
        total = 0.0
        conflicting: dict[str, float] = {}
        for block, volume in block_volumes.items():
            if exclusive_blocks.get(block, set()).isdisjoint(block_volumes):
                total += volume
            else:
                conflicting[block] = volume

        if not conflicting:
            return total

        block, volume = conflicting.popitem()
        compatible = {other: q for other, q in conflicting.items() if other not in exclusive_blocks[block]}
        return total + max(
            volume + ThermalBiddingStep._max_compatible_volume(compatible, exclusive_blocks),
            ThermalBiddingStep._max_compatible_volume(conflicting, exclusive_blocks),
        )

    def _compute_da_sell_submitted_volume(self, result: StepResult) -> None:
        """
        Compute the largest volume that the orders of each thermal unit can sell at each time step.

        Orders linked by PARENT_CHILDREN, IDENTICAL_VOLUME or IDENTICAL_RATIO couplings form a block. At a given
        time step, a block offers its parents and independent orders, plus the largest child of each parent.
        Blocks linked by an EXCLUSION coupling cannot be accepted together, the others add up.

        :param result: Orders and couplings formulated for the thermal units
        :type result: StepResult
        """
        temporal = self.parameters.temporal
        grid = Timeseries.from_index(temporal.start_date, temporal.timestep, temporal.end_date, default_value=0)
        grid_index = grid.index
        orders_time = set(self.orders_time)

        # All the couplings of an order are used: blocks are built from every non exclusive link
        block_of: dict[str, str] = {}
        parent_of: dict[str, str] = {}
        exclusive_orders: list[tuple[str, str]] = []
        for coupling in result.order_couplings:
            names = [order.name for order in coupling.orders]
            if coupling.coupling_type == CouplingType.EXCLUSION:
                exclusive_orders.extend(combinations(names, 2))
            elif coupling.coupling_type in (
                CouplingType.PARENT_CHILDREN,
                CouplingType.IDENTICAL_VOLUME,
                CouplingType.IDENTICAL_RATIO,
            ):
                for name in names[1:]:
                    block_of[self._find_block(block_of, name)] = self._find_block(block_of, names[0])
                    if coupling.coupling_type == CouplingType.PARENT_CHILDREN:
                        parent_of[name] = names[0]
            else:
                cfg.logger.warning(f"{coupling.coupling_type} couplings are ignored in the sell submitted volumes")

        exclusive_blocks: dict[str, set[str]] = defaultdict(set)
        for first, second in exclusive_orders:
            first_block, second_block = self._find_block(block_of, first), self._find_block(block_of, second)
            if first_block == second_block:
                cfg.logger.warning(f"Orders {first} and {second} are both linked and exclusive: exclusion ignored")
                continue
            exclusive_blocks[first_block].add(second_block)
            exclusive_blocks[second_block].add(first_block)

        # At a time step, a parent only adds its largest child
        volumes_per_block: dict[tuple[str, datetime], dict[str, float]] = defaultdict(lambda: defaultdict(float))
        largest_children: dict[tuple[str, datetime, str], float] = {}
        for order in result.orders:
            if (
                order.product != Product.DayAhead
                or not isinstance(order.equipment, Thermal)
                or order.start_date not in orders_time
            ):
                continue

            qmax = order.qmax if order.qmax is not None else 0.0
            parent = parent_of.get(order.name)
            if parent is None:
                block = self._find_block(block_of, order.name)
                volumes_per_block[order.equipment.name, order.start_date][block] += qmax
            else:
                key = (order.equipment.name, order.start_date, parent)
                largest_children[key] = max(largest_children.get(key, 0.0), qmax)

        for (unit_name, t, parent), qmax in largest_children.items():
            volumes_per_block[unit_name, t][self._find_block(block_of, parent)] += qmax

        sell_submitted_volumes: dict[str, dict[datetime, float]] = defaultdict(dict)
        for (unit_name, t), block_volumes in volumes_per_block.items():
            sell_submitted_volumes[unit_name][t] = self._max_compatible_volume(block_volumes, exclusive_blocks)

        for equipment in self.dataset.thermal:
            volumes = sell_submitted_volumes[equipment.name]
            sell_submitted_volume = grid.with_values([volumes.get(t, 0.0) for t in grid_index])

            if equipment.da_sell_submitted_volume is None:
                equipment.da_sell_submitted_volume = sell_submitted_volume
            else:
                equipment.da_sell_submitted_volume = equipment.da_sell_submitted_volume.add_on_union(
                    sell_submitted_volume, inplace=False
                )
