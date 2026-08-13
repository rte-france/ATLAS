"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed

import atlas.config as cfg
from atlas.enums import ThermalStrategy
from atlas.math.matrix import ScenarioMatrix
from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.steps.abstract_step import AbstractBiddingStep
from atlas.modules.day_ahead_orders.steps.result import BiddingResult
from atlas.modules.day_ahead_orders.steps.thermal.strategies.base import ThermalBaseLoadOrders
from atlas.modules.day_ahead_orders.steps.thermal.strategies.intermediate import (
    IntermediateSolveResult,
    ThermalIntermediateLoadOrders,
)
from atlas.modules.day_ahead_orders.steps.thermal.strategies.peak import ThermalPeakLoadOrders
from atlas.modules.day_ahead_orders.steps.thermal.submitted_volume import compute_da_sell_submitted_volume
from atlas.timing import generate_datetimes


def _optimize_single_thermal_unit(
    thermal: ThermalDAO,
    orders_time: list,
    parameters: DayAheadOrdersParameters,
) -> IntermediateSolveResult | None:
    """
    Worker function for thermal unit LP solve (INTERMEDIATE strategy only).

    Runs the LP via :class:`ThermalIntermediateLoadOrders` and returns the solve result
    (raw LP outputs + dispatch state sequences) keyed by price type. Returns ``None`` for
    BASE and PEAK strategies — their heuristics run directly in the main process.
    """
    try:
        cfg.logger.debug(f"Formulating orders for thermal unit {thermal.name} with strategy {thermal.strategy}")

        if thermal.strategy == ThermalStrategy.INTERMEDIATE:
            return ThermalIntermediateLoadOrders(orders_time, parameters).solve(thermal)

        if thermal.strategy in (ThermalStrategy.BASE, ThermalStrategy.PEAK):
            return None

        cfg.logger.warning(f"Unknown thermal strategy {thermal.strategy} for unit {thermal.name}")
        return None

    except Exception as e:
        cfg.logger.error(f"Order formulation failed for thermal unit {thermal.name}: {e}")
        cfg.logger.info(traceback.format_exc())
        return None


def _assign_state_sequence(
    thermal: ThermalDAO, solved: IntermediateSolveResult, parameters: DayAheadOrdersParameters
) -> None:
    """Write the LP-derived state sequence onto the thermal unit (in-place)."""
    if thermal.state_sequence is None:
        thermal.state_sequence = ScenarioMatrix()
    for price_type, sequence in solved.dispatch_state_sequences.items():
        thermal.state_sequence.add(sequence, f"{parameters.temporal.execution_date}-{price_type.upper()}_DAO")


class ThermalBidding(AbstractBiddingStep):
    def formulate(self) -> BiddingResult:
        if self.parameters.multiprocessing.enable:
            result = self._formulate_parallel()
        else:
            result = self._formulate_sequential()

        cfg.logger.info("Computing maximum sell volumes...")
        submitted_volumes = compute_da_sell_submitted_volume(
            result, self.dataset.thermal, self.orders_time, self.parameters
        )
        for equipment in self.dataset.thermal:
            equipment.da_sell_submitted_volume = submitted_volumes[equipment.name]
        cfg.logger.info("End of computation.")

        return result

    def _build_orders_for_unit(
        self,
        thermal: ThermalDAO,
        solved: IntermediateSolveResult | None,
        orders_time: list,
    ) -> tuple[list, list]:
        """Dispatch to the right strategy handler and return (orders, couplings)."""
        if thermal.strategy == ThermalStrategy.BASE:
            return ThermalBaseLoadOrders(orders_time, self.parameters).formulate(thermal)
        if thermal.strategy == ThermalStrategy.INTERMEDIATE:
            assert solved is not None, f"LP solve result required for INTERMEDIATE unit {thermal.name}"
            _assign_state_sequence(thermal, solved, self.parameters)
            return ThermalIntermediateLoadOrders(orders_time, self.parameters).build_orders(thermal, solved.raw)
        if thermal.strategy == ThermalStrategy.PEAK:
            return ThermalPeakLoadOrders(orders_time, self.parameters).formulate(thermal)
        cfg.logger.warning(f"Unknown thermal strategy {thermal.strategy} for unit {thermal.name}")
        return [], []

    def _formulate_parallel(self) -> BiddingResult:
        cfg.logger.info(f"Starting parallel thermal optimization for {len(self.dataset.thermal)} units")
        result = BiddingResult()
        orders_time = generate_datetimes(
            self.parameters.temporal.start_date,
            self.parameters.penultimate_date,
            self.parameters.temporal.timestep,
        )

        intermediate = [t for t in self.dataset.thermal if t.strategy == ThermalStrategy.INTERMEDIATE]
        heuristic = [t for t in self.dataset.thermal if t.strategy != ThermalStrategy.INTERMEDIATE]

        for thermal in heuristic:
            orders, couplings = self._build_orders_for_unit(thermal, None, orders_time)
            result.orders.extend(orders)
            result.order_couplings.extend(couplings)
            cfg.logger.info(
                f"Completed order formulation for thermal unit: {thermal.name} ({thermal.strategy.value if thermal.strategy else thermal.strategy})"
            )

        if not intermediate:
            return result

        thermal_by_name = {t.name: t for t in intermediate}
        with ProcessPoolExecutor(max_workers=self.parameters.multiprocessing.max_workers) as executor:
            future_to_name = {
                executor.submit(_optimize_single_thermal_unit, thermal, orders_time, self.parameters): thermal.name
                for thermal in intermediate
            }

            for future in as_completed(future_to_name):
                thermal_name = future_to_name[future]
                try:
                    solved = future.result()
                    thermal = thermal_by_name[thermal_name]
                    orders, couplings = self._build_orders_for_unit(thermal, solved, orders_time)
                    result.orders.extend(orders)
                    result.order_couplings.extend(couplings)
                    cfg.logger.info(
                        f"Completed order formulation for thermal unit: {thermal_name} ({ThermalStrategy.INTERMEDIATE.value})"
                    )
                except Exception as e:
                    cfg.logger.error(f"Error processing thermal unit {thermal_name}: {e}")

        return result

    def _formulate_sequential(self) -> BiddingResult:
        cfg.logger.info(f"Starting sequential thermal optimization for {len(self.dataset.thermal)} units")
        result = BiddingResult()
        orders_time = generate_datetimes(
            self.parameters.temporal.start_date,
            self.parameters.penultimate_date,
            self.parameters.temporal.timestep,
        )

        for thermal in self.dataset.thermal:
            solved = _optimize_single_thermal_unit(thermal, orders_time, self.parameters)
            orders, couplings = self._build_orders_for_unit(thermal, solved, orders_time)
            result.orders.extend(orders)
            result.order_couplings.extend(couplings)
            cfg.logger.info(
                f"Completed order formulation for thermal unit: {thermal.name} ({thermal.strategy.value if thermal.strategy else thermal.strategy})"
            )

        return result
