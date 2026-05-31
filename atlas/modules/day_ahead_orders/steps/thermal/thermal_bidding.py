"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed

import atlas.config as cfg
from atlas.enums import ThermalStrategy
from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.steps.abstract_step import AbstractBiddingStep
from atlas.modules.day_ahead_orders.steps.result import BiddingResult
from atlas.modules.day_ahead_orders.steps.thermal.base_orders import ThermalBaseLoadOrders
from atlas.modules.day_ahead_orders.steps.thermal.intermediate_orders import ThermalIntermediateLoadOrders
from atlas.modules.day_ahead_orders.steps.thermal.thermal_dao_step import ThermalOptimisationResult
from atlas.modules.day_ahead_orders.steps.thermal.peak_orders import ThermalPeakLoadOrders
from atlas.modules.day_ahead_orders.steps.thermal.submitted_volume import compute_da_sell_submitted_volume
from atlas.timing import generate_datetimes


def _optimize_single_thermal_unit(
    thermal: ThermalDAO,
    orders_time: list,
    parameters: DayAheadOrdersParameters,
) -> dict[str, ThermalOptimisationResult] | None:
    """
    Worker function for thermal unit LP solve (INTERMEDIATE strategy only).

    Runs the LP via :class:`ThermalIntermediateLoadOrders` and returns raw results
    keyed by price type. Returns ``None`` for BASE and PEAK strategies — their
    heuristics run directly in the main process.

    :param thermal: Thermal unit to optimise.
    :param orders_time: List of datetimes for order formulation.
    :param parameters: Order formulation parameters.
    :return: LP outputs keyed by price type, or ``None`` for rule-based strategies.
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


class ThermalBidding(AbstractBiddingStep):
    def formulate(self) -> BiddingResult:
        if self.parameters.multiprocessing.enable:
            result = self._formulate_parallel()
        else:
            result = self._formulate_sequential()

        cfg.logger.info("Computing maximum sell volumes...")
        compute_da_sell_submitted_volume(result, self.dataset.thermal, self.orders_time, self.parameters)
        cfg.logger.info("End of computation.")

        return result

    def _build_orders_for_unit(
        self,
        thermal: ThermalDAO,
        raw: dict[str, ThermalOptimisationResult] | None,
        orders_time: list,
    ) -> tuple[list, list]:
        """Dispatch to the right strategy handler and return (orders, couplings)."""
        if thermal.strategy == ThermalStrategy.BASE:
            return ThermalBaseLoadOrders(orders_time, self.parameters).formulate(thermal)
        if thermal.strategy == ThermalStrategy.INTERMEDIATE:
            assert raw is not None, f"raw LP results required for INTERMEDIATE unit {thermal.name}"
            return ThermalIntermediateLoadOrders(orders_time, self.parameters).build_orders(thermal, raw)
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
                    raw = future.result()
                    thermal = thermal_by_name[thermal_name]
                    orders, couplings = self._build_orders_for_unit(thermal, raw, orders_time)
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
            raw = _optimize_single_thermal_unit(thermal, orders_time, self.parameters)
            orders, couplings = self._build_orders_for_unit(thermal, raw, orders_time)
            result.orders.extend(orders)
            result.order_couplings.extend(couplings)
            cfg.logger.info(
                f"Completed order formulation for thermal unit: {thermal.name} ({thermal.strategy.value if thermal.strategy else thermal.strategy})"
            )

        return result
