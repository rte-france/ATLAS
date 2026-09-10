"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import json

import pendulum

import atlas.modules.market_clearing.constants as constants
from atlas.enums import SolverStatus
from atlas.modules.market_clearing.data_classes import ClearingOutputs, PriceGroup
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.input_objects.market_area import MarketAreaMC
from atlas.modules.market_clearing.input_objects.market_border import MarketBorderMC
from atlas.modules.market_clearing.order_links import OrderLinkResolver
from atlas.modules.market_clearing.parameters import MarketClearingParameters
from atlas.modules.market_clearing.phases._helpers import count_saturated
from atlas.modules.market_clearing.phases.pricing import first_attempt, second_attempt, third_attempt
from atlas.modules.market_clearing.phases.pricing._types import PricingAttempt
from atlas.solver.models import SolverOptions
from atlas.solver.solver_interface import OptimisationModel


class Pricing:
    def __init__(
        self,
        input_dataset: MarketClearingInputDataset,
        parameters: MarketClearingParameters,
        clearing_outputs: ClearingOutputs,
    ):
        solver_options = SolverOptions(presolve=parameters.solver.use_presolve)

        self.model = OptimisationModel(parameters.solver.solver_name, options=solver_options, name="Pricing")
        self.input_dataset = input_dataset
        self.parameters = parameters
        self.saturated_critical_branch = clearing_outputs.saturated_critical_branch
        self.clearing_border_exchanges = clearing_outputs.border_exchanges
        self.clearing_local_balances = clearing_outputs.local_balances
        self.clearing_accepted_powers = clearing_outputs.accepted_powers
        self.price_groups = self.create_price_groups()
        order_links = OrderLinkResolver(self.input_dataset.orders, self.input_dataset.order_couplings).resolve()
        self.dict_linked_orders = order_links.linked_orders
        self.dict_parent_child_orders = order_links.parent_child_orders
        self._full_link_id_by_order = order_links.full_link_id_by_order

    def compute(self):
        self.build_first()
        solver_info = self.model.solve()
        output_path = self.parameters.get_lp_dir()
        if self.parameters.solver.export_lp:
            output_path.mkdir(parents=True, exist_ok=True)
            self.model.export_model(str(output_path / "pricing_1_model.lp"))
        if solver_info.status not in [SolverStatus.OPTIMAL, SolverStatus.FEASIBLE]:
            self.build_second()
            solver_info = self.model.solve()
            if self.parameters.solver.export_lp:
                self.model.export_model(str(output_path / "pricing_2_model.lp"))

        if solver_info.status not in [SolverStatus.OPTIMAL, SolverStatus.FEASIBLE]:
            self.build_third()
            _ = self.model.solve()
            if self.parameters.solver.export_lp:
                self.model.export_model(str(output_path / "pricing_3_model.lp"))
        if self.parameters.solver.export_lp:
            with open(output_path / "pricing_market_prices.json", "w") as f:
                json.dump(
                    [
                        [market_area_name, str(time), val]
                        for (market_area_name, time), val in self.get_market_prices().items()
                    ],
                    f,
                )

    def build_first(self):
        first_attempt.instantiate_order_group_index(self)
        first_attempt.build_variables(self)
        first_attempt.build_constraints(self)
        first_attempt.build_objective(self)

    def build_second(self):
        # Update PriceGroup
        second_attempt.update_price_bound(self)
        second_attempt.compute_min_max_rejected_sale_buy(self)
        second_attempt.build_variables(self)
        # If the order is accepted, check if it is partially accepted. If so, delete the marginal surplus constraint.
        second_attempt.build_constraints(self)
        second_attempt.build_objective(self)

    def build_third(self):
        opposite_delta_p_dict = third_attempt.compute_opposite_delta_p(self)
        third_attempt.build_variables(self, opposite_delta_p_dict)
        third_attempt.build_constraints(self, opposite_delta_p_dict)
        third_attempt.build_objective(self, opposite_delta_p_dict)

    ##################################
    # Price groups — shared across the three attempts
    ##################################
    # Generator of border ranks and names of neighbour area for each border of a given market area:
    def get_market_area_neighbours(self, market_area_name: str) -> list[tuple[MarketBorderMC, str]]:
        neighbours_area = []
        for border in self.input_dataset.market_borders.values():
            neighbour_area = (
                border.downhill_market_area
                if border.uphill_market_area.name == market_area_name
                else border.uphill_market_area
            )
            neighbours_area.append((border, neighbour_area.name))
        return neighbours_area

    # Append all neighbour areas recursively as long as they are not already part of the group and the connection is not
    # saturated:
    def propagate_through_unsaturated(
        self,
        market_area: MarketAreaMC,
        time: pendulum.DateTime,
        area_price_group: dict[str, int | None],
        price_group: PriceGroup,
    ):
        for border, neighbour_market_area_name in self.get_market_area_neighbours(market_area.name):
            if neighbour_market_area_name in price_group.market_area_names:
                continue
            flow = self.clearing_border_exchanges[border.name, time]
            relative_max_flow = border.max_flow.get_value(time)
            relative_min_flow = border.min_flow.get_value(time)
            if (
                relative_min_flow + self.parameters.allowed_round_off_error
                <= flow
                <= relative_max_flow - self.parameters.allowed_round_off_error
            ):
                area_price_group[neighbour_market_area_name] = price_group.id
                price_group.market_area_names.append(neighbour_market_area_name)
                neighbour_market_area = self.input_dataset.market_areas[neighbour_market_area_name]
                self.propagate_through_unsaturated(neighbour_market_area, time, area_price_group, price_group)

    def create_price_groups(self) -> dict[pendulum.DateTime, list[PriceGroup]]:
        price_groups: dict[pendulum.DateTime, list[PriceGroup]] = {}
        for time in self.input_dataset.times:
            price_groups[time] = []
            if self.input_dataset.is_atc:
                # Initialize a dict linking each market area with a price group number:
                areas_price_group: dict[str, int | None] = {}
                for market_area_name in self.input_dataset.market_areas:
                    areas_price_group[market_area_name] = None

                for group_id, (market_area_name, market_area) in enumerate(self.input_dataset.market_areas.items()):
                    # If the current area is already allocated to a price group, go to the next one:
                    if areas_price_group[market_area_name] is not None:
                        continue
                    price_group = PriceGroup(id=group_id, time=time)
                    price_group.market_area_names.append(market_area_name)
                    areas_price_group[market_area_name] = group_id
                    price_groups[time].append(price_group)

                    # Loop over borders that are not saturated and link all possible areas inside the current group in a
                    # recursive way:
                    self.propagate_through_unsaturated(market_area, time, areas_price_group, price_group)
            else:
                if count_saturated(self.saturated_critical_branch, time, self.parameters.allowed_round_off_error) == 0:
                    unique_price_group = PriceGroup(id=0, time=time)
                    unique_price_group.market_area_names = list(self.input_dataset.market_areas)
                    price_groups[time].append(unique_price_group)
                else:
                    for group_id, market_area_name in enumerate(self.input_dataset.market_areas):
                        new_price_group = PriceGroup(id=group_id, time=time)
                        new_price_group.market_area_names = [market_area_name]
                        price_groups[time].append(new_price_group)
        for price_group_list in price_groups.values():
            for price_group in price_group_list:
                self.compute_price_bounds(price_group, PricingAttempt.FIRST)
        return price_groups

    def is_neighbour(self, price_group: PriceGroup, other_price_group: PriceGroup) -> bool:
        """Check if two group are neighbour

        :param price_group: PriceGroup.
        :param other_price_group: PriceGroup. The PriceGroup to check
        :return: bool. True if there are neighbour otherwise False
        """
        # Count the number of occurrences of each market border inside the
        # current group (self):
        current_borders_counts = {}
        for border_name, border in self.input_dataset.market_borders.items():
            for market_area_name in price_group.market_area_names:
                if (
                    market_area_name == border.uphill_market_area.name
                    or market_area_name == border.downhill_market_area.name
                ):
                    if border_name not in current_borders_counts:
                        current_borders_counts[border_name] = 0
                    current_borders_counts[border_name] += 1

        # Deduce the list of borders that appear only once, as they define the external border of the group:
        current_external_borders = [
            border_name for border_name, border_count in current_borders_counts.items() if border_count == 1
        ]

        # Count the number of occurrences of each market border inside the
        # other group (self):
        other_borders_counts = {}
        for border_name, border in self.input_dataset.market_borders.items():
            for market_area_name in other_price_group.market_area_names:
                if (
                    market_area_name == border.uphill_market_area.name
                    or market_area_name == border.downhill_market_area.name
                ):
                    if border_name not in other_borders_counts:
                        other_borders_counts[border_name] = 0
                    other_borders_counts[border_name] += 1

        # Deduce the list of borders that appear only once, as they define the external border of the group:
        other_external_borders = [
            border_name for border_name, border_count in other_borders_counts.items() if border_count == 1
        ]

        # Check if there is at least one common external border between both
        # groups. If so, they are neighbours, otherwise they are not:
        for other_border_name in other_external_borders:
            if other_border_name in current_external_borders:
                return True
        return False

    def compute_price_bounds(self, price_group: PriceGroup, pricing_type: PricingAttempt):
        for market_area_name in price_group.market_area_names:
            time = price_group.time
            market_area = self.input_dataset.market_areas[market_area_name]
            # Initialize the local bounds on order prices:
            max_accepted_sale_price = max_rejected_purchase_price = market_area.min_price.get_value(time)
            min_rejected_sale_price = min_accepted_purchase_price = market_area.max_price.get_value(time)

            # Select orders involved during the current time step (generator):
            current_orders = (
                order for order in market_area.orders.values() if order.start_date <= time < order.end_date
            )

            for order in current_orders:
                current_power = self.clearing_accepted_powers[market_area_name, order.name]
                # Skip complex orders to compute price bounds
                # Linked order
                if order.is_linked:
                    continue

                    # Other complex order
                if order.requires_status_variable is not None:
                    continue

                    # Combined accepted at their min:
                if (abs(current_power - order.qmin) <= self.parameters.allowed_round_off_error) and (order.qmin != 0.0):
                    continue

                # Compute the relevant bound:
                if order.is_sale:
                    if abs(current_power) >= self.parameters.allowed_round_off_error:
                        max_accepted_sale_price = max(max_accepted_sale_price, order.price)
                    else:
                        min_rejected_sale_price = min(min_rejected_sale_price, order.price)
                else:
                    if abs(current_power) >= self.parameters.allowed_round_off_error:
                        min_accepted_purchase_price = min(min_accepted_purchase_price, order.price)
                    else:
                        max_rejected_purchase_price = max(max_rejected_purchase_price, order.price)

                # Once done with orders, deduce the bounds on the group price:
                # In the first pricing, these bounds are computed taking into account both accepted and rejected orders
            if pricing_type == PricingAttempt.FIRST:
                price_group.min_price = max(price_group.min_price, max_accepted_sale_price, max_rejected_purchase_price)
                price_group.max_price = min(price_group.max_price, min_rejected_sale_price, min_accepted_purchase_price)
                # In the second, rejected orders are not taken into account to compute the price bounds
            else:
                price_group.min_price = max(price_group.min_price, max_accepted_sale_price)
                price_group.max_price = min(price_group.max_price, min_accepted_purchase_price)

    def get_market_prices(self) -> dict[tuple[str, pendulum.DateTime], float]:
        """
        :rtype: dict[tuple[str, pendulum.DateTime], float]
        """
        market_prices = {}
        for time, price_groups in self.price_groups.items():
            for price_group in price_groups:
                for market_area_name in price_group.market_area_names:
                    market_price_name = constants.price_on_group_variable_name(price_group.id, time)
                    market_prices[market_area_name, time] = self.model.get_variable(market_price_name).solution_value()
        return market_prices
