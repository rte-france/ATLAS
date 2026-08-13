"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import itertools
from dataclasses import dataclass, field

import polars as pl
from pendulum import DateTime

import atlas.config as cfg
from atlas.enums import CouplingType
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
from atlas.modules.day_ahead_orders.input_objects.order_coupling import OrderCouplingDAO
from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.steps.thermal.dispatch.optimization_step import (
    ThermalDAOStep,
    ThermalOptimisationResult,
)
from atlas.modules.day_ahead_orders.steps.thermal.dispatch.state_sequence import (
    build_dispatch_state_sequence,
    build_intermediate_state_sequence,
)
from atlas.modules.day_ahead_orders.steps.thermal.orders.online_sequences import extract_online_sequences
from atlas.modules.day_ahead_orders.steps.thermal.orders.unit_orders import formulate_unit_orders
from atlas.objects.equipment.thermal import Thermal
from atlas.solver.models import SolverOptions
from atlas.solver.solver_interface import OptimisationModel


@dataclass
class IntermediateSolveResult:
    """
    LP solve output for an intermediate thermal unit, across all configured price scenarios.

    :param raw: LP results keyed by price type.
    :param dispatch_state_sequences: ``ThermalDispatchState`` time series per price type.
        Must be assigned to ``unit.state_sequence`` by the caller (see :class:`ThermalBidding`).
    """

    raw: dict[str, ThermalOptimisationResult] = field(default_factory=dict)
    dispatch_state_sequences: dict[str, Timeseries] = field(default_factory=dict)


class ThermalIntermediateLoadOrders:
    """
    Order formulation for intermediate thermal units. Runs an LP per price scenario then
    builds orders from the resulting state sequences. Multiple online sub-windows can be
    produced under different price scenarios; overlapping windows are wired with EXCLUSION
    couplings to enforce mutual exclusion at the market layer.
    """

    def __init__(self, orders_time: list[DateTime], parameters: DayAheadOrdersParameters):
        self.orders_time = orders_time
        self.parameters = parameters

    def formulate(self, unit: ThermalDAO) -> tuple[list[OrderDAO], list[OrderCouplingDAO]]:
        """Convenience wrapper: ``solve`` then ``build_orders``. Returns ``(orders, couplings)``."""
        solved = self.solve(unit)
        return self.build_orders(unit, solved.raw)

    def solve(self, unit: ThermalDAO) -> IntermediateSolveResult:
        """
        Run the LP for each configured price scenario.

        Pure function: the caller is responsible for assigning
        ``unit.state_sequence`` from the returned ``dispatch_state_sequences``.
        """
        out = IntermediateSolveResult()
        solver_options = SolverOptions(
            presolve=self.parameters.solver.use_presolve,
            duality_gap=self.parameters.solver.duality_gap,
            time_limit=self.parameters.solver.timeout,
        )

        for price_type in self.parameters.price_forecasts_types:
            price = self._load_price_forecast(unit, price_type)
            step = ThermalDAOStep(unit, price, price_type)
            model = OptimisationModel(
                self.parameters.solver.solver_name,
                f"Optimization program for thermal unit {unit.name}",
                solver_options,
            )
            step.add_variables(model, self.parameters)
            step.add_constraints(model, self.parameters)
            step.add_objective(model, self.parameters)

            if self.parameters.solver.export_lp:
                lp_dir = self.parameters.get_lp_dir()
                lp_dir.mkdir(parents=True, exist_ok=True)
                model.export_model(str(lp_dir / f"{unit.name}_price_{price_type}.lp"))

            cfg.logger.info(f"Optimisation model for '{unit.name}' with price type '{price_type}'")
            model.solve()

            raw = step.extract_result(self.parameters)
            out.raw[price_type] = raw
            out.dispatch_state_sequences[price_type] = build_dispatch_state_sequence(raw, self.parameters)

        return out

    def build_orders(
        self, unit: ThermalDAO, raw: dict[str, ThermalOptimisationResult]
    ) -> tuple[list[OrderDAO], list[OrderCouplingDAO]]:
        """
        Build orders and couplings from LP results.

        Identifies unique scenarios (collapsing identical ones), formulates per-window orders
        with the same engine as the baseload strategy, then adds EXCLUSION couplings between
        scenarios whose online sub-windows overlap in time.
        """
        orders: list[OrderDAO] = []
        couplings: list[OrderCouplingDAO] = []

        cases = self.get_unique_cases(raw, unit)
        timestep = self.parameters.temporal.timestep

        online_timeframes: list[tuple[Timeseries, str]] = []
        for case in cases:
            states_sequence = build_intermediate_state_sequence(raw[case])
            for online_timeframe, case_name in extract_online_sequences(
                states_sequence, self.orders_time, timestep, case
            ):
                online_timeframes.append((online_timeframe, case_name))
                unit_orders, unit_couplings = formulate_unit_orders(
                    online_timeframe, unit, self.orders_time, self.parameters, case=case_name
                )
                orders.extend(unit_orders)
                couplings.extend(unit_couplings)

        overlapping_blocks = self.get_overlapping_timeframes(online_timeframes)

        if overlapping_blocks:
            if unit.minimum_power.timeseries.filter(pl.col("time").is_in(self.orders_time))["value"].sum() > 0.0:
                orders_names = [
                    f"order_at_{ts.first_date()}_for_unit_{unit.name}_under_price_{case}"
                    for (ts, case), _ in overlapping_blocks
                ] + [
                    f"order_at_{ts.first_date()}_for_unit_{unit.name}_under_price_{case}"
                    for _, (ts, case) in overlapping_blocks
                ]
                orders_list = [order for order in orders if order.name in orders_names]
                sorted_orders = [[o for o in orders_list if case in o.name] for case in cases]

                for orders_a, orders_b in itertools.combinations(sorted_orders, 2):
                    for order_1, order_2 in itertools.product(orders_a, orders_b):
                        couplings.append(
                            OrderCouplingDAO(
                                name=f"EXCLUSION_link_between_orders_{order_1.name}_and_{order_2.name}",
                                coupling_type=CouplingType.EXCLUSION,
                                orders=[order_1, order_2],  # type: ignore [arg-type]
                            )
                        )

        return orders, couplings

    def get_unique_cases(self, results: dict[str, ThermalOptimisationResult], thermal_unit: ThermalDAO) -> list[str]:
        """
        Collapse identical price scenarios down to one representative case name each.

        If three cases Low/Medium/High produce identical outcomes for Medium and High, the
        returned list will be ``["Low", "Medium"]`` (one of the duplicates kept arbitrarily).
        """
        if not isinstance(thermal_unit, Thermal):
            cfg.logger.error(f"Equipement {thermal_unit.name} is not of type thermic.")
            raise ValueError("Wrong equipment type for the thermic optimization program.")

        collapsed_outcomes: list[tuple[Timeseries, str]] = []
        for case in results.keys():
            unit_res = results[case]
            is_on = unit_res.on_up + unit_res.on_down
            if unit_res.on_flat is not None:
                is_on += unit_res.on_flat
            collapsed_outcomes.append((is_on, case))

        to_discard: list[tuple[Timeseries, str]] = []
        for pair in itertools.combinations(collapsed_outcomes, 2):
            if self.is_overlapping((pair[0][0], pair[1][0])):
                to_discard.append(pair[0])

        for scenario in to_discard:
            collapsed_outcomes.remove(scenario)

        # All scenarios identical → keep one arbitrarily.
        if len(collapsed_outcomes) == 0 and len(to_discard) > 0:
            collapsed_outcomes = [to_discard[0]]

        return [case_name for _, case_name in collapsed_outcomes]

    def get_overlapping_timeframes(
        self, online_timeframes: list[tuple[Timeseries, str]]
    ) -> list[tuple[tuple[Timeseries, str], tuple[Timeseries, str]]]:
        """Return pairs of online sub-windows whose date ranges overlap (across distinct cases)."""
        overlapping_blocks: list[tuple[tuple[Timeseries, str], tuple[Timeseries, str]]] = []
        for pair in itertools.combinations(online_timeframes, 2):
            (ts1, name1), (ts2, name2) = pair
            if name1 == name2:
                continue
            s1, e1 = ts1.first_date(), ts1.last_date()
            s2, e2 = ts2.first_date(), ts2.last_date()
            if s1 <= s2 <= e1 or s2 <= s1 <= e2:
                overlapping_blocks.append(pair)
        return overlapping_blocks

    def is_overlapping(self, pair: tuple[Timeseries, Timeseries]) -> bool:
        """Two aggregated ON-status series are considered overlapping iff equal element-wise."""
        if not len(pair) == 2:
            raise ValueError("The pair inputed in the is_overlapping function has not a length of 2.")

        return pair[0] == pair[1]

    def _load_price_forecast(self, unit: ThermalDAO, price_type: str) -> Timeseries:
        attr_name = f"price_forecast_{price_type.lower()}"
        forecast = getattr(unit.portfolio.market_area, attr_name)
        if forecast is None:
            raise AttributeError(f"{unit.portfolio.market_area.name} has no attribute '{attr_name}'")
        return forecast.get_forecast(
            self.parameters.temporal.execution_date,
            self.parameters.temporal.start_date,
            self.parameters.temporal.end_date + unit.additional_hours,
        )
