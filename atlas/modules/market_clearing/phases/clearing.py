"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import itertools
import json
from collections.abc import Callable
from typing import Any, Literal

import pendulum

import atlas.modules.market_clearing.constants as constants
from atlas.config import logger
from atlas.enums import ComplementDirection, CouplingType, OrderType
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.input_objects.market_area import MarketAreaMC
from atlas.modules.market_clearing.input_objects.order import OrderMC
from atlas.modules.market_clearing.input_objects.order_coupling import OrderCouplingMC
from atlas.modules.market_clearing.parameters import MarketClearingParameters
from atlas.modules.market_clearing.phases import _border_variables
from atlas.objects.network_operator.control_block import ControlBlock
from atlas.solver.models import SolverOptions
from atlas.solver.solver_interface import OptimisationModel


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

    def compute(self):
        self.build()
        self.model.solve()
        if self.parameters.solver.export_lp:
            output_path = self.parameters.get_lp_dir()
            output_path.mkdir(parents=True, exist_ok=True)
            self.model.export_model(str(output_path / "clearing_model.lp"))
            with open(output_path / "clearing_accepted_powers.json", "w") as f:
                json.dump([[ma, o, val] for (ma, o), val in self.get_accepted_powers().items()], f)
            with open(output_path / "clearing_local_balances.json", "w") as f:
                json.dump(
                    [[ma, str(t), val] for (ma, t), val in self.get_local_balances().items()],
                    f,
                )
            with open(output_path / "clearing_saturated_critical_branches.json", "w") as f:
                json.dump(
                    [[cb, str(t), val] for (cb, t), val in self.get_saturated_critical_branch().items()],
                    f,
                )

    def build(self):
        self.build_variables()
        self.build_constraints()
        self.build_objective()

    def build_variables(self):
        """Create all variables for the clearing phase model"""
        is_atc = self.input_dataset.is_atc
        _border_variables.create_border_exchange_variables(self, is_atc)

        if self.input_dataset.parameters.flow_penalty_lambda_2 != 0.0:
            _border_variables.create_border_pos_exchanges_variables(self, is_atc)
            _border_variables.create_border_neg_exchanges_variables(self, is_atc)

        if is_atc:
            _border_variables.create_border_loss_variables(
                self, constants.border_import_variable_name, only_borders_with_losses=True
            )
            _border_variables.create_border_loss_variables(
                self, constants.border_export_variable_name, only_borders_with_losses=True
            )
            _border_variables.create_border_loss_variables(
                self, constants.border_xsis_variable_name, only_borders_with_losses=True
            )
            _border_variables.create_border_loss_variables(
                self, constants.border_nus_variable_name, only_borders_with_losses=True
            )

        self.create_local_balances_variables()
        self.create_accepted_powers()
        self.create_orders_status()

    def build_constraints(self):
        """Create all constraints for the clearing phase model"""
        is_atc = self.input_dataset.is_atc
        self.create_limited_accepted_power_constraints()
        self.create_order_couplings_constraints()
        self.create_local_balances_constraints()
        self.create_exchanges_and_local_balances_equality_constraints(is_atc)
        if self.parameters.activate_constrained_tso_quantity:
            self.create_control_blocks_constraints()
        self.create_exchange_across_border_constraints()
        if is_atc and self.get_n_borders_with_losses():
            self.create_import_export_constraints()

        if not is_atc:
            self.create_constraint_3_6_2_constraints()
        if self.parameters.flow_penalty_lambda_2 != 0.0:
            self.create_absolute_exchange_constraints()

    def build_objective(self):
        """Create objective function for the clearing phase model"""
        self.model.set_direction("maximize")
        self.add_accepted_powers_objective(self.parameters.price_modifier_lambda_1)
        if self.parameters.flow_penalty_lambda_2 != 0.0:
            self.add_global_exchanges_objective(self.parameters.flow_penalty_lambda_2)
        if self.input_dataset.is_atc:
            exchange_objective_dict = {}
            if self.parameters.flow_penalty_lambda_3 != 0.0:
                for key, value in self.build_max_exchange_coefficients(self.parameters.flow_penalty_lambda_3).items():
                    exchange_objective_dict[key.name()] = value
            if self.parameters.flow_penalty_lambda_4 != 0.0:
                for key, value in self.build_min_exchange_coefficients(self.parameters.flow_penalty_lambda_4).items():
                    if key.name() not in exchange_objective_dict:
                        exchange_objective_dict[key.name()] = value
                    else:
                        exchange_objective_dict[key.name()] += value
            self.model.add_objective(
                sum([self.model.get_variable(key) * value for key, value in exchange_objective_dict.items()])
            )

    ##################################
    # Variables
    ##################################
    def create_local_balances_variables(self):
        for market_area_name in self.input_dataset.market_areas:
            for time in self.input_dataset.times:
                self.model.add_continuous_variable(
                    constants.local_balance_variable_name(market_area_name, time), -float("inf"), float("inf")
                )

    def create_accepted_powers(self):
        for market_area in self.input_dataset.market_areas.values():
            for order in market_area.orders.values():
                if not order.qmin:
                    max_power = order.qmax
                    self.model.add_continuous_variable(
                        constants.accepted_power_variable_name(order.market_area.name, order.name), 0.0, max_power
                    )
                else:
                    self.model.add_continuous_variable(
                        constants.accepted_power_variable_name(order.market_area.name, order.name),
                        -float("inf"),
                        float("inf"),
                    )

    def create_orders_status(self):
        for market_area in self.input_dataset.market_areas.values():
            for order in market_area.orders.values():
                if order.requires_status_variable:
                    self.model.add_boolean_variable(constants.order_status_variable_name(market_area.name, order.name))

    ##################################
    # Constraints
    ##################################
    def create_local_balances_constraints(self):
        for time in self.input_dataset.times:
            for market_area in self.input_dataset.market_areas.values():
                accepted_powers = []
                for order in market_area.orders.values():
                    # Focus on orders comprising the current time in their duration:
                    if order.start_date <= time < order.end_date_processed:
                        accepted_power = self.model.get_variable(
                            constants.accepted_power_variable_name(order.market_area.name, order.name)
                        )
                        accepted_powers.append(order.production_sign * accepted_power)
                local_balance = self.model.get_variable(constants.local_balance_variable_name(market_area.name, time))
                self.model.add_constraint(
                    sum(accepted_powers) == local_balance,
                    constants.constraint_3_2_1_constraint_name(market_area.name, time),
                )

    def create_exchanges_and_local_balances_equality_constraints(self, is_atc):
        for time in self.input_dataset.times:
            for market_area_name in self.input_dataset.market_areas:
                exchanges_sum = []
                for border_name, border in self.input_dataset.market_borders.items():
                    if market_area_name not in [
                        border.uphill_market_area.name,
                        border.downhill_market_area.name,
                    ]:
                        continue
                    if is_atc and border.loss_factor and border.loss_factor != 0.0:
                        if border.uphill_market_area.name == market_area_name:
                            exchanges_sum.append(
                                self.model.get_variable(constants.border_export_variable_name(border_name, time))
                            )
                        elif border.downhill_market_area.name == market_area_name:
                            exchanges_sum.append(
                                -self.model.get_variable(constants.border_import_variable_name(border_name, time))
                            )
                    else:
                        border_sign = 1 if market_area_name == border.uphill_market_area.name else -1
                        exchanges_sum.append(
                            border_sign
                            * self.model.get_variable(constants.border_exchange_variable_name(border_name, time))
                        )
                self.model.add_constraint(
                    self.model.get_variable(constants.local_balance_variable_name(market_area_name, time))
                    == sum(exchanges_sum),
                    constants.constraint_3_2_2_constraint_name(market_area_name, time),
                )

    def create_control_blocks_constraints(self):
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
                    constants.constraint_3_5_sold_constraint_name(control_block_name, time),
                )
                self.model.add_constraint(
                    tso_bought_power <= max_tso_bought_power,
                    constants.constraint_3_5_bought_constraint_name(control_block_name, time),
                )

    def create_exchange_across_border_constraints(self):
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
                self.model.add_constraint(
                    self.model.get_variable(constants.border_exchange_variable_name(border_name, time))
                    == self.model.get_variable(constants.border_exchange_variable_name(border_name, block_start)),
                    constants.exchange_across_border_constraint_name(border_name, time),
                )

    def create_import_export_constraints(self):
        for time in self.input_dataset.times:
            for border_name, border in self.input_dataset.market_borders.items():
                if border.loss_factor is None or border.loss_factor == 0:
                    continue
                exchange = self.model.get_variable(constants.border_exchange_variable_name(border_name, time))
                _import = self.model.get_variable(constants.border_import_variable_name(border_name, time))
                _export = self.model.get_variable(constants.border_export_variable_name(border_name, time))
                xsis = self.model.get_variable(constants.border_xsis_variable_name(border_name, time))
                nus = self.model.get_variable(constants.border_nus_variable_name(border_name, time))

                self.model.add_constraint(
                    exchange == 0.5 * (_import + _export),
                    constants.constraint_3_6_1b_constraint_name(border_name, time),
                )

                import_after_losses = (
                    (1.0 - border.loss_factor) - 1.0 / (1.0 - border.loss_factor)
                ) * xsis + _export / (1.0 - border.loss_factor)
                self.model.add_constraint(
                    _import == import_after_losses,
                    constants.constraint_3_6_1c_constraint_name(border_name, time),
                )
                self.model.add_constraint(
                    xsis >= 0.5 * _export, constants.constraint_3_6_1d_constraint_name(border_name, time)
                )

                if exchange.Lb():
                    self.model.add_constraint(
                        nus * exchange.Lb() <= xsis,
                        constants.constraint_3_6_1f_min_constraint_name(border_name, time),
                    )
                    self.model.add_constraint(
                        (1 - nus) * exchange.Lb() >= _export - xsis,
                        constants.constraint_3_6_1g_min_constraint_name(border_name, time),
                    )

                if exchange.Ub():
                    self.model.add_constraint(
                        nus * exchange.Ub() <= xsis,
                        constants.constraint_3_6_1f_max_constraint_name(border_name, time),
                    )
                    self.model.add_constraint(
                        (1 - nus) * exchange.Ub() >= _export - xsis,
                        constants.constraint_3_6_1g_max_constraint_name(border_name, time),
                    )

    def create_absolute_exchange_constraints(self):
        for time in self.input_dataset.times:
            for border_name in self.input_dataset.market_borders.keys():
                border_exchange = self.model.get_variable(constants.border_exchange_variable_name(border_name, time))
                border_pos_exchange = self.model.get_variable(
                    constants.border_pos_exchange_variable_name(border_name, time)
                )
                border_neg_exchange = self.model.get_variable(
                    constants.border_neg_exchange_variable_name(border_name, time)
                )
                absolute_exchange_constraint_name = constants.absolute_exchange_constraint_name(border_name, time)
                self.model.add_constraint(
                    border_pos_exchange + border_neg_exchange == border_exchange, absolute_exchange_constraint_name
                )

    def create_constraint_3_6_2_constraints(self):
        for time in self.input_dataset.times:
            for critical_branch_name, critical_branch in self.input_dataset.critical_branches.items():
                branch_load = []
                for market_area_ptdf in critical_branch.market_area_ptdf:
                    da_ptdf = market_area_ptdf.day_ahead_ptdf
                    relative_balance = self.model.get_variable(
                        constants.local_balance_variable_name(market_area_ptdf.market_area.name, time)
                    ) - market_area_ptdf.market_area.ref_balance.get_value(time)

                    branch_load.append(da_ptdf.get_value(time) * relative_balance)
                self.model.add_constraint(
                    sum(branch_load) <= critical_branch.max_flow.get_value(time),
                    constants.constraint_3_6_2_constraint_name(critical_branch_name, time),
                )

    def create_limited_accepted_power_constraints(self):
        for market_area in self.input_dataset.market_areas.values():
            for order in market_area.orders.values():
                # Compute the constraints limiting the accepted powers of combined,
                # indivisible and/or mutually excluding orders and linked orders (3.4):
                if order.requires_status_variable:
                    order_status = self.model.get_variable(
                        constants.order_status_variable_name(market_area.name, order.name)
                    )
                    accepted_power = self.model.get_variable(
                        constants.accepted_power_variable_name(order.market_area.name, order.name)
                    )
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
        order_status,
        bound: Literal["min", "max"],
        power: float,
        accepted_power,
    ):
        if bound == "min":
            self.model.add_constraint(
                order_status * max(self.parameters.allowed_round_off_error, power) <= accepted_power,
                constants.min_accepted_power_constraint_name(market_area_name, order_name),
            )
        else:
            self.model.add_constraint(
                order_status * power >= accepted_power,
                constants.max_accepted_power_constraint_name(market_area_name, order_name),
            )

    def create_order_couplings_constraints(self):
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

    def create_identical_volume_order_coupling_constraints(self, order_coupling: OrderCouplingMC):
        for prev_order, order in itertools.pairwise(order_coupling.orders):
            prev_accepted_power = self.model.get_variable(
                constants.accepted_power_variable_name(prev_order.market_area.name, prev_order.name)
            )
            accepted_power = self.model.get_variable(
                constants.accepted_power_variable_name(order.market_area.name, order.name)
            )

            self.model.add_constraint(
                accepted_power == prev_accepted_power,
                constants.identical_volume_order_coupling_constraint_name(order_coupling.name, order.name),
            )

    def create_complement_order_coupling_constraints(self, order_coupling: OrderCouplingMC):
        if not order_coupling.complement_direction:
            logger.warning(
                f"Can't create constraint complement order coupling ('{order_coupling.name}') because there is not "
                f"complement_direction"
            )
            return
        aggregated_accepted_power = []
        for order in order_coupling.orders:
            accepted_power = self.model.get_variable(
                constants.accepted_power_variable_name(order.market_area.name, order.name)
            )
            if order.order_type == OrderType.Sell:
                aggregated_accepted_power.append(-accepted_power)
            else:
                aggregated_accepted_power.append(accepted_power)
        aggregated_proportion_accepted_power = (
            sum(aggregated_accepted_power) * self.parameters.temporal.timestep.total_minutes() / 60
        )
        constraint_name = constants.constraint_3_9_constraint_name(order_coupling.name)
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

    def create_exclusion_order_coupling_constraints(self, order_coupling: OrderCouplingMC):
        aggregated_status = []
        for order in order_coupling.orders:
            order_status = self.model.get_variable(
                constants.order_status_variable_name(order.market_area.name, order.name)
            )
            aggregated_status.append(order_status)
        self.model.add_constraint(
            sum(aggregated_status) <= 1, constants.exclusion_order_coupling_constraint_name(order_coupling.name)
        )

    def create_parent_children_order_coupling_constraints(self, order_coupling: OrderCouplingMC):
        parent_order = order_coupling.orders[0]
        parent_order_status = self.model.get_variable(
            constants.order_status_variable_name(parent_order.market_area.name, parent_order.name)
        )
        for order in order_coupling.orders[1:]:
            order_status = self.model.get_variable(
                constants.order_status_variable_name(order.market_area.name, order.name)
            )
            self.model.add_constraint(
                order_status <= parent_order_status,
                constants.parent_child_order_coupling_constraint_name(order_coupling.name, order.market_area.name),
            )

    def create_identical_ratio_order_coupling_constraints(self, order_coupling: OrderCouplingMC):
        for prev_order, order in itertools.pairwise(order_coupling.orders):
            prev_accepted_power = self.model.get_variable(
                constants.accepted_power_variable_name(prev_order.market_area.name, prev_order.name)
            )
            accepted_power = self.model.get_variable(
                constants.accepted_power_variable_name(order.market_area.name, order.name)
            )
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
                constants.identical_ratio_order_coupling_constraint_name(order_coupling.name, order.name),
            )

    ##################################
    # Objective
    ##################################
    def add_accepted_powers_objective(self, lambda1: float):
        objective = []
        for market_area in self.input_dataset.market_areas.values():
            for order in market_area.orders.values():
                accepted_power = self.model.get_variable(
                    constants.accepted_power_variable_name(order.market_area.name, order.name)
                )
                altered_price = order.price - order.production_sign * lambda1
                objective.append(
                    -order.production_sign * altered_price * order.duration.total_minutes() * accepted_power / 60
                )
        return self.model.add_objective(sum(objective))

    def add_global_exchanges_objective(self, lambda2: float):
        objective = []
        for time in self.input_dataset.times:
            for border_name in self.input_dataset.market_borders.keys():
                border_pos_exchanges = self.model.get_variable(
                    constants.border_pos_exchange_variable_name(border_name, time)
                )
                border_neg_exchanges = self.model.get_variable(
                    constants.border_neg_exchange_variable_name(border_name, time)
                )
                objective.append(border_pos_exchanges - border_neg_exchanges)
        return self.model.add_objective(-lambda2 * sum(objective))

    def build_max_exchange_coefficients(self, penalty: float) -> dict:
        objective = {}
        constant = 0.0
        for time in self.input_dataset.times:
            for border_name in self.input_dataset.market_borders.keys():
                border_exchange = self.model.get_variable(constants.border_exchange_variable_name(border_name, time))
                objective[border_exchange] = penalty
                constant -= penalty * border_exchange.Lb()
        return objective

    def build_min_exchange_coefficients(self, penalty: float) -> dict:
        objective = {}
        constant = 0.0
        for time in self.input_dataset.times:
            for border_name in self.input_dataset.market_borders.keys():
                border_exchange = self.model.get_variable(constants.border_exchange_variable_name(border_name, time))
                objective[border_exchange] = -penalty
                constant += penalty * border_exchange.Lb()
        return objective

    def get_tso_sold_power(self, time: pendulum.DateTime, control_block: ControlBlock):
        return _sum_tso_orders(
            control_block,
            self.input_dataset.market_areas,
            time,
            OrderType.Buy,
            lambda order: self.model.get_variable(
                constants.accepted_power_variable_name(order.market_area.name, order.name)
            ),
        )

    def get_tso_bought_power(self, time: pendulum.DateTime, control_block: ControlBlock):
        return _sum_tso_orders(
            control_block,
            self.input_dataset.market_areas,
            time,
            OrderType.Sell,
            lambda order: self.model.get_variable(
                constants.accepted_power_variable_name(order.market_area.name, order.name)
            ),
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

    def get_n_borders_with_losses(self) -> int:
        """get the number of border that have a loss factor

        :rtype: int
        """
        n_borders_with_losses = 0
        for market_border in self.input_dataset.market_borders.values():
            if market_border.loss_factor and market_border.loss_factor != 0.0:
                n_borders_with_losses += 1
        return n_borders_with_losses

    def get_local_balances(self) -> dict[tuple[str, pendulum.DateTime], float]:
        """Retrieve the power balance for each market area at each timestep

        :rtype: dict[tuple[str, str], float]
        """
        local_balances = {}
        for market_area_name in self.input_dataset.market_areas:
            for time in self.input_dataset.times:
                accepted_power_name = constants.local_balance_variable_name(market_area_name, time)
                local_balances[market_area_name, time] = self.model.get_variable(accepted_power_name).solution_value()
        return local_balances

    def get_accepted_powers(self) -> dict[tuple[str, str], float]:
        """Retrieve the accepted powers of each order per area

        :rtype: dict[tuple[str, str], float]
        """
        accepted_powers = {}
        for market_area in self.input_dataset.market_areas.values():
            for order in market_area.orders.values():
                accepted_power_name = constants.accepted_power_variable_name(order.market_area.name, order.name)
                accepted_powers[order.market_area.name, order.name] = self.model.get_variable(
                    accepted_power_name
                ).solution_value()
        return accepted_powers

    def get_saturated_critical_branch(self) -> dict[tuple[str, pendulum.DateTime], float]:
        """Retrieve the slack value of each critical branch at each timestep

        :rtype: dict[tuple[str, pendulum.DateTime], float]
        """
        saturated_critical_branch = {}
        for time in self.input_dataset.times:
            for critical_branch_name in self.input_dataset.critical_branches:
                critical_branch_saturation = self.model.get_constraint_slack_value(
                    constants.constraint_3_6_2_constraint_name(critical_branch_name, time)
                )
                saturated_critical_branch[critical_branch_name, time] = critical_branch_saturation
        return saturated_critical_branch
