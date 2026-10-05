"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

import itertools
import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

import pendulum

import atlas.modules.market_clearing.constants as constants
from atlas.config import logger
from atlas.enums import ComplementDirection, CouplingType, OrderType
from atlas.math.timeseries import Timeseries
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.input_objects.market_area import MarketAreaMC
from atlas.modules.market_clearing.input_objects.order import OrderMC
from atlas.modules.market_clearing.input_objects.order_coupling import OrderCouplingMC
from atlas.modules.market_clearing.parameters import MarketClearingParameters
from atlas.modules.market_clearing.phases._border_variables import (
    AbsoluteExchanges,
    add_absolute_exchanges,
    add_exchange_variables,
    add_loss_variables,
)
from atlas.objects.network_operator.control_block import ControlBlock
from atlas.solver.models import SolverOptions
from atlas.solver.solver_interface import OptimisationModel
from atlas.solver.temporal_variable import TemporalVariable

if TYPE_CHECKING:
    # ortools-stubs does not ship pywraplp (see the solver_interface mypy override)
    from ortools.linear_solver import pywraplp  # type: ignore[attr-defined]


def _sum_tso_orders(
    control_block: ControlBlock,
    market_areas: dict[str, MarketAreaMC],
    time: pendulum.DateTime,
    order_type: OrderType,
    value_of: Callable[[OrderMC], Any],
):
    """Sum `value_of(order)` over non-TSO orders of the given type, active at `time`, in a control block."""
    total = 0.0
    for market_area in market_areas.values():
        if control_block.name != market_area.control_block.name:
            continue
        for order in market_area.orders.values():
            is_available = order.start_date <= time <= order.end_date_processed
            not_tso = not order.is_agent_tso
            matches_direction = order.order_type == order_type
            if is_available and not_tso and matches_direction:
                total += value_of(order)
    return total


class Clearing:
    def __init__(self, input_dataset: MarketClearingInputDataset, parameters: MarketClearingParameters):
        solver_options = SolverOptions(presolve=parameters.solver.use_presolve)

        self.model = OptimisationModel(parameters.solver.solver_name, options=solver_options, name="Clearing")
        self.input_dataset = input_dataset
        self.parameters = parameters

        # Variables only depend on the inputs: they are declared here so that the phase is complete
        # once built, and the optional ones are None rather than re-deduced from the parameters.
        self.exchange = add_exchange_variables(self.model, input_dataset)
        self.absolute = (
            add_absolute_exchanges(self.model, input_dataset) if parameters.flow_penalty_lambda_2 != 0.0 else None
        )
        self.losses = add_loss_variables(self.model, input_dataset, only_borders_with_losses=True)
        self.local_balance: dict[str, TemporalVariable] = {
            market_area_name: self.model.add_temporal_variable(f"balance_on_{market_area_name}", input_dataset.times)
            for market_area_name in input_dataset.market_areas
        }
        self.accepted_power = self.create_accepted_powers()
        self.status = self.create_orders_status()

    def compute(self) -> None:
        self.build()
        self.model.solve()
        if self.parameters.solver.export_lp:
            output_path = self.parameters.lp_dir
            output_path.mkdir(parents=True, exist_ok=True)
            self.model.export_model(str(output_path / "clearing_model.lp"))
            with open(output_path / "clearing_accepted_powers.json", "w") as f:
                json.dump([[ma, o, val] for (ma, o), val in self.get_accepted_powers().items()], f)
            with open(output_path / "clearing_local_balances.json", "w") as f:
                json.dump(
                    [
                        [ma, str(t), val]
                        for ma, balance in self.get_local_balances().items()
                        for t, val in balance.iter_rows()
                    ],
                    f,
                )
            with open(output_path / "clearing_saturated_critical_branches.json", "w") as f:
                json.dump(
                    [[cb, str(t), val] for (cb, t), val in self.get_saturated_critical_branch().items()],
                    f,
                )

    def build(self) -> None:
        self.build_constraints()
        self.build_objective()

    def build_constraints(self) -> None:
        """Create all constraints for the clearing phase model"""
        self.create_limited_accepted_power_constraints()
        self.create_order_couplings_constraints()
        self.create_local_balances_constraints()
        self.create_balance_exchange_constraints()
        if self.parameters.activate_constrained_tso_quantity:
            self.create_control_blocks_constraints()
        self.create_resolution_block_constraints()
        self.create_loss_constraints()

        if not self.input_dataset.is_atc:
            self.create_critical_branch_constraints()
        if self.absolute is not None:
            self.create_absolute_exchange_constraints(self.absolute)

    def build_objective(self) -> None:
        """Create objective function for the clearing phase model"""
        self.model.set_direction("maximize")
        self.add_accepted_powers_objective(self.parameters.price_modifier_lambda_1)
        if self.absolute is not None:
            self.add_absolute_exchanges_objective(self.absolute, self.parameters.flow_penalty_lambda_2)
        if self.input_dataset.is_atc:
            self.add_exchanges_objective(self.parameters.flow_penalty_lambda_3, self.parameters.flow_penalty_lambda_4)

    ##################################
    # Variables
    ##################################
    def create_accepted_powers(self) -> dict[str, pywraplp.Variable]:
        """Create the accepted power of each order, keyed by order name.

        Only an order without a minimum power is bounded here, by its maximum power: the others are
        left free, the status variable of those that have one bounds them (3.4).
        """
        accepted_power = {}
        for market_area in self.input_dataset.market_areas.values():
            for order in market_area.orders.values():
                lower_bound, upper_bound = (-float("inf"), float("inf")) if order.qmin else (0.0, order.qmax)
                accepted_power[order.name] = self.model.add_continuous_variable(
                    f"qo_{market_area.name}_{order.name}", lower_bound, upper_bound
                )
        return accepted_power

    def create_orders_status(self) -> dict[str, pywraplp.Variable]:
        """Create the acceptance status of each order that requires one, keyed by order name."""
        return {
            order.name: self.model.add_boolean_variable(f"status_{market_area.name}_{order.name}")
            for market_area in self.input_dataset.market_areas.values()
            for order in market_area.orders.values()
            if order.requires_status_variable
        }

    ##################################
    # Constraints
    ##################################
    def create_local_balances_constraints(self) -> None:
        for time in self.input_dataset.times:
            for market_area in self.input_dataset.market_areas.values():
                accepted_powers = []
                for order in market_area.orders.values():
                    # Focus on orders comprising the current time in their duration:
                    if order.start_date <= time < order.end_date_processed:
                        accepted_powers.append(order.production_sign * self.accepted_power[order.name])
                self.model.add_constraint(
                    sum(accepted_powers) == self.local_balance[market_area.name][time],
                    f"Constraint_3_2_1_t_{time}_mkt_{market_area.name}",
                )

    def create_balance_exchange_constraints(self) -> None:
        for time in self.input_dataset.times:
            for market_area_name in self.input_dataset.market_areas:
                exchanges_sum = []
                for border_name, border in self.input_dataset.market_borders.items():
                    if market_area_name not in [
                        border.uphill_market_area.name,
                        border.downhill_market_area.name,
                    ]:
                        continue
                    # Clearing only has loss variables for the ATC borders with losses
                    if losses := self.losses.get(border_name):
                        if border.uphill_market_area.name == market_area_name:
                            exchanges_sum.append(losses.exports[time])
                        elif border.downhill_market_area.name == market_area_name:
                            exchanges_sum.append(-losses.imports[time])
                    else:
                        border_sign = 1 if market_area_name == border.uphill_market_area.name else -1
                        exchanges_sum.append(border_sign * self.exchange[border_name][time])
                self.model.add_constraint(
                    self.local_balance[market_area_name][time] == sum(exchanges_sum),
                    f"Constraint_3_2_2_t_{time}_mkt_{market_area_name}",
                )

    def create_control_blocks_constraints(self) -> None:
        for time in self.input_dataset.times:
            for control_block_name, control_block in self.input_dataset.control_blocks.items():
                tso_sold_power = self.get_tso_sold_power(time, control_block)
                tso_bought_power = self.get_tso_bought_power(time, control_block)
                max_tso_sold_power = Clearing.get_max_tso_power_sold(
                    time, control_block, self.input_dataset.market_areas
                )
                max_tso_bought_power = Clearing.get_max_tso_power_bought(
                    time, control_block, self.input_dataset.market_areas
                )
                self.model.add_constraint(
                    tso_sold_power <= max_tso_sold_power,
                    f"Constraint_3_5_t_{time}_cblock_{control_block_name}_sold_TSO_powers",
                )
                self.model.add_constraint(
                    tso_bought_power <= max_tso_bought_power,
                    f"Constraint_3_5_t_{time}_cblock_{control_block_name}_bought_TSO_powers",
                )

    def create_resolution_block_constraints(self) -> None:
        """Hold a border's exchange constant over each of its resolution blocks.

        A border coarser than the clearing timestep can only carry one exchange value per resolution
        block, so every timestep inside a block is tied back to the timestep that opens it.
        """
        timestep_minutes = self.parameters.temporal.timestep.total_minutes()
        for time in self.input_dataset.times:
            for border_name, border in self.input_dataset.market_borders.items():
                if border.time_resolution is None or border.resolution_time <= timestep_minutes:
                    continue
                minutes_elapsed = (time - self.parameters.temporal.start_date).in_minutes()
                minutes_into_block = minutes_elapsed % border.resolution_time
                if not minutes_into_block:
                    continue
                block_start = time.subtract(minutes=minutes_into_block)
                exchange = self.exchange[border_name]
                self.model.add_constraint(
                    exchange[time] == exchange[block_start],
                    constants.exchange_across_border_constraint_name(border_name, time),
                )

    def create_loss_constraints(self) -> None:
        for time in self.input_dataset.times:
            for border_name, losses in self.losses.items():
                border = self.input_dataset.market_borders[border_name]
                loss_factor = border.loss_factor or 0.0
                exchange = self.exchange[border_name][time]
                imports = losses.imports[time]
                exports = losses.exports[time]
                xsis = losses.xsis[time]
                nus = losses.nus[time]
                # Loss variables only exist in ATC, where the exchange is bounded by the border flow limits
                min_flow = border.min_flow.get_value(time)
                max_flow = border.max_flow.get_value(time)

                self.model.add_constraint(
                    exchange == 0.5 * (imports + exports),
                    f"Constraint_3_6_1b_t_{time}_mkt_border_{border_name}",
                )

                import_after_losses = ((1.0 - loss_factor) - 1.0 / (1.0 - loss_factor)) * xsis + exports / (
                    1.0 - loss_factor
                )
                self.model.add_constraint(
                    imports == import_after_losses,
                    f"Constraint_3_6_1c_t_{time}_mkt_border_{border_name}",
                )
                self.model.add_constraint(xsis >= 0.5 * exports, f"Constraint_3_6_1d_t_{time}_mkt_border_{border_name}")

                if min_flow:
                    self.model.add_constraint(
                        nus * min_flow <= xsis,
                        f"Constraint_3_6_1f_min_t_{time}_mkt_border_{border_name}",
                    )
                    self.model.add_constraint(
                        (1 - nus) * min_flow >= exports - xsis,
                        f"Constraint_3_6_1g_min_t_{time}_mkt_border_{border_name}",
                    )

                if max_flow:
                    self.model.add_constraint(
                        nus * max_flow <= xsis,
                        f"Constraint_3_6_1f_max_t_{time}_mkt_border_{border_name}",
                    )
                    self.model.add_constraint(
                        (1 - nus) * max_flow >= exports - xsis,
                        f"Constraint_3_6_1g_max_t_{time}_mkt_border_{border_name}",
                    )

    def create_absolute_exchange_constraints(self, absolute: AbsoluteExchanges) -> None:
        for time in self.input_dataset.times:
            for border_name in self.input_dataset.market_borders.keys():
                border_exchange = self.exchange[border_name][time]
                border_pos_exchange = absolute.positive[border_name][time]
                border_neg_exchange = absolute.negative[border_name][time]
                absolute_exchange_constraint_name = f"Pos_neg_def_t_{time}_mkt_border_{border_name}"
                self.model.add_constraint(
                    border_pos_exchange + border_neg_exchange == border_exchange, absolute_exchange_constraint_name
                )

    def create_critical_branch_constraints(self) -> None:
        for time in self.input_dataset.times:
            for critical_branch_name, critical_branch in self.input_dataset.critical_branches.items():
                max_flow = critical_branch.max_flow
                if max_flow is None:
                    raise ValueError(f"Critical branch '{critical_branch_name}' has no maximum flow to constrain")
                branch_load = []
                for market_area_ptdf in critical_branch.market_area_ptdf:
                    da_ptdf = market_area_ptdf.day_ahead_ptdf
                    market_area = market_area_ptdf.market_area
                    relative_balance = self.local_balance[market_area.name][time] - market_area.ref_balance.get_value(
                        time
                    )

                    branch_load.append(da_ptdf.get_value(time) * relative_balance)
                self.model.add_constraint(
                    sum(branch_load) <= max_flow.get_value(time),
                    constants.critical_branch_constraint_name(critical_branch_name, time),
                )

    def create_limited_accepted_power_constraints(self) -> None:
        for market_area in self.input_dataset.market_areas.values():
            for order in market_area.orders.values():
                # Compute the constraints limiting the accepted powers of combined,
                # indivisible and/or mutually excluding orders and linked orders (3.4):
                if order.requires_status_variable:
                    order_status = self.status[order.name]
                    accepted_power = self.accepted_power[order.name]
                    self.create_accepted_power_constraint(
                        market_area.name, order.name, order_status, "min", order.qmin, accepted_power
                    )
                    self.create_accepted_power_constraint(
                        market_area.name, order.name, order_status, "max", order.qmax, accepted_power
                    )

    def create_accepted_power_constraint(
        self,
        market_area_name: str,
        order_name: str,
        order_status: Any,
        bound: Literal["min", "max"],
        power: float,
        accepted_power: Any,
    ) -> None:
        if bound == "min":
            self.model.add_constraint(
                order_status * max(self.parameters.allowed_round_off_error, power) <= accepted_power,
                f"Constraint_3_4_min_mkt_{market_area_name}_o_{order_name}",
            )
        else:
            self.model.add_constraint(
                order_status * power >= accepted_power,
                f"Constraint_3_4_max_mkt_{market_area_name}_o_{order_name}",
            )

    def create_order_couplings_constraints(self) -> None:
        for order_coupling in self.input_dataset.order_couplings.values():
            match order_coupling.coupling_type:
                case CouplingType.IDENTICAL_VOLUME:
                    self.create_identical_volume_order_coupling_constraints(order_coupling)
                case CouplingType.IDENTICAL_RATIO:
                    self.create_identical_ratio_order_coupling_constraints(order_coupling)
                case CouplingType.COMPLEMENT:
                    self.create_complement_order_coupling_constraints(order_coupling)
                case CouplingType.EXCLUSION:
                    self.create_exclusion_order_coupling_constraints(order_coupling)
                case CouplingType.PARENT_CHILDREN:
                    self.create_parent_children_order_coupling_constraints(order_coupling)

    def create_identical_volume_order_coupling_constraints(self, order_coupling: OrderCouplingMC) -> None:
        for prev_order, order in itertools.pairwise(order_coupling.orders):
            self.model.add_constraint(
                self.accepted_power[order.name] == self.accepted_power[prev_order.name],
                f"Constraint_3_8_id_volume_o_n_{order.name}_group_n_{order_coupling.name}",
            )

    def create_complement_order_coupling_constraints(self, order_coupling: OrderCouplingMC) -> None:
        if not order_coupling.complement_direction:
            logger.warning(
                f"Can't create constraint complement order coupling ('{order_coupling.name}') because there is not "
                f"complement_direction"
            )
            return
        aggregated_accepted_power = []
        for order in order_coupling.orders:
            accepted_power = self.accepted_power[order.name]
            if order.order_type == OrderType.Sell:
                aggregated_accepted_power.append(-accepted_power)
            else:
                aggregated_accepted_power.append(accepted_power)
        aggregated_proportion_accepted_power = (
            sum(aggregated_accepted_power) * self.parameters.temporal.timestep.total_minutes() / 60
        )
        constraint_name = f"C_3_9_compl_o_group_{order_coupling.name}"
        if order_coupling.complement_direction == ComplementDirection.EqualTo:
            self.model.add_constraint(
                aggregated_proportion_accepted_power == order_coupling.complement_energy, constraint_name
            )
        elif order_coupling.complement_direction == ComplementDirection.GreaterThan:
            self.model.add_constraint(
                aggregated_proportion_accepted_power >= order_coupling.complement_energy, constraint_name
            )
        elif order_coupling.complement_direction == ComplementDirection.LesserThan:
            self.model.add_constraint(
                aggregated_proportion_accepted_power <= order_coupling.complement_energy, constraint_name
            )

    def create_exclusion_order_coupling_constraints(self, order_coupling: OrderCouplingMC) -> None:
        self.model.add_constraint(
            sum(self.status[order.name] for order in order_coupling.orders) <= 1,
            f"Constraint_3_10_exclusive_o_g_number_{order_coupling.name}",
        )

    def create_parent_children_order_coupling_constraints(self, order_coupling: OrderCouplingMC) -> None:
        parent_order_status = self.status[order_coupling.orders[0].name]
        for order in order_coupling.orders[1:]:
            self.model.add_constraint(
                self.status[order.name] <= parent_order_status,
                f"Constraint_parent_child_on_child_{order.market_area.name}_on_group{order_coupling.name}",
            )

    def create_identical_ratio_order_coupling_constraints(self, order_coupling: OrderCouplingMC) -> None:
        for prev_order, order in itertools.pairwise(order_coupling.orders):
            prev_accepted_power = self.accepted_power[prev_order.name]
            accepted_power = self.accepted_power[order.name]
            if prev_order.qmin == prev_order.qmax:
                prev_ratio = prev_accepted_power / prev_order.qmax
            else:
                prev_ratio = (prev_accepted_power - prev_order.qmin) / (prev_order.qmax - prev_order.qmin)
            if order.qmin == order.qmax:
                ratio = accepted_power / order.qmax
            else:
                ratio = (accepted_power - order.qmin) / (order.qmax - order.qmin)

            self.model.add_constraint(
                ratio == prev_ratio,
                f"Constraint_3_8_1_id_ratio_o_n_{order.name}_group_n_{order_coupling.name}",
            )

    ##################################
    # Objective
    ##################################
    def add_accepted_powers_objective(self, lambda1: float) -> None:
        objective = []
        for market_area in self.input_dataset.market_areas.values():
            for order in market_area.orders.values():
                accepted_power = self.accepted_power[order.name]
                altered_price = order.price - order.production_sign * lambda1
                objective.append(
                    -order.production_sign * altered_price * order.duration.total_minutes() * accepted_power / 60
                )
        self.model.add_objective(sum(objective))

    def add_absolute_exchanges_objective(self, absolute: AbsoluteExchanges, lambda2: float) -> None:
        objective = []
        for time in self.input_dataset.times:
            for border_name in self.input_dataset.market_borders.keys():
                border_pos_exchanges = absolute.positive[border_name][time]
                border_neg_exchanges = absolute.negative[border_name][time]
                objective.append(border_pos_exchanges - border_neg_exchanges)
        self.model.add_objective(-lambda2 * sum(objective))

    def add_exchanges_objective(self, lambda3: float, lambda4: float) -> None:
        """Push every border exchange towards its maximum (lambda3) and its minimum (lambda4).

        Both penalties weigh the same exchanges with opposite signs, so they add up to a single
        coefficient, and nothing is added when they cancel out.
        """
        penalty = lambda3 - lambda4
        if not penalty:
            return
        self.model.add_objective(
            penalty * sum(exchange[time] for exchange in self.exchange.values() for time in self.input_dataset.times)
        )

    def get_tso_sold_power(self, time: pendulum.DateTime, control_block: ControlBlock) -> Any:
        return _sum_tso_orders(
            control_block,
            self.input_dataset.market_areas,
            time,
            OrderType.Buy,
            lambda order: self.accepted_power[order.name],
        )

    def get_tso_bought_power(self, time: pendulum.DateTime, control_block: ControlBlock) -> Any:
        return _sum_tso_orders(
            control_block,
            self.input_dataset.market_areas,
            time,
            OrderType.Sell,
            lambda order: self.accepted_power[order.name],
        )

    @staticmethod
    def get_max_tso_power_sold(
        time: pendulum.DateTime, control_block: ControlBlock, market_areas: dict[str, MarketAreaMC]
    ) -> float:
        return _sum_tso_orders(control_block, market_areas, time, OrderType.Buy, lambda order: order.qmax)

    @staticmethod
    def get_max_tso_power_bought(
        time: pendulum.DateTime, control_block: ControlBlock, market_areas: dict[str, MarketAreaMC]
    ) -> float:
        return _sum_tso_orders(control_block, market_areas, time, OrderType.Sell, lambda order: order.qmax)

    def get_local_balances(self) -> dict[str, Timeseries]:
        """Retrieve the power balance of each market area over the clearing horizon

        :rtype: dict[str, Timeseries]
        """
        return {
            market_area_name: local_balance.solution() for market_area_name, local_balance in self.local_balance.items()
        }

    def get_accepted_powers(self) -> dict[tuple[str, str], float]:
        """Retrieve the accepted powers of each order per area

        :rtype: dict[tuple[str, str], float]
        """
        self.model.require_solution()
        return {
            (order.market_area.name, order.name): self.accepted_power[order.name].solution_value()
            for market_area in self.input_dataset.market_areas.values()
            for order in market_area.orders.values()
        }

    def get_saturated_critical_branch(self) -> dict[tuple[str, pendulum.DateTime], float]:
        """Retrieve the slack value of each critical branch at each timestep

        :rtype: dict[tuple[str, pendulum.DateTime], float]
        """
        saturated_critical_branch = {}
        for time in self.input_dataset.times:
            for critical_branch_name in self.input_dataset.critical_branches:
                critical_branch_saturation = self.model.get_constraint_slack_value(
                    constants.critical_branch_constraint_name(critical_branch_name, time)
                )
                saturated_critical_branch[critical_branch_name, time] = critical_branch_saturation
        return saturated_critical_branch
