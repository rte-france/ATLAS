"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import json

import atlas.modules.market_clearing.constants as constants
from atlas.enums import SolverStatus
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.input_objects.market_area import MarketAreaMC, get_max_price, get_min_price
from atlas.modules.market_clearing.input_objects.market_border import MarketBorderMC, get_max_flow, get_min_flow
from atlas.modules.market_clearing.order_links import OrderLinkResolver
from atlas.modules.market_clearing.parameters import MarketClearingParameters
from atlas.modules.market_clearing.phases._helpers import count_saturated
from atlas.modules.market_clearing.phases.pricing import first_pass, second_pass, third_pass
from atlas.modules.market_clearing.price_group import PriceGroup
from atlas.solver.models import SolverOptions
from atlas.solver.solver_interface import OptimisationModel


class Pricing:
    def __init__(
        self,
        input_dataset: MarketClearingInputDataset,
        parameters: MarketClearingParameters,
        saturated_critical_branch: dict[tuple[str, int], float],
        exchange_fixing_border_exchanges: dict[tuple[str, int], float],
        clearing_local_balances: dict[tuple[str, int], float],
        clearing_accepted_powers: dict[tuple[str, str], float],
    ):
        solver_options = SolverOptions(presolve=parameters.solver.use_presolve)

        self.model = OptimisationModel(parameters.solver.solver_name, options=solver_options, name="Pricing")
        self.input_dataset = input_dataset
        self.parameters = parameters
        self.saturated_critical_branch = saturated_critical_branch
        self.clearing_border_exchanges = exchange_fixing_border_exchanges
        self.clearing_local_balances = clearing_local_balances
        self.clearing_accepted_powers = clearing_accepted_powers
        self.price_groups = self.create_price_groups()
        order_links = OrderLinkResolver(self.input_dataset.mc_orders, self.input_dataset.mc_order_couplings).resolve()
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
                        [market_area_name, time_index, val]
                        for (market_area_name, time_index), val in self.get_market_prices().items()
                    ],
                    f,
                )

    def build_first(self):
        first_pass.instantiate_order_group_index(self)
        first_pass.build_variables(self)
        first_pass.build_constraints(self)
        first_pass.build_objective(self)

    def build_second(self):
        # Update PriceGroup
        second_pass.update_price_bound(self)
        second_pass.compute_min_max_rejected_sale_buy(self)
        second_pass.build_variables(self)
        # If the order is accepted, check if it is partially accepted. If so, delete the marginal surplus constraint.
        second_pass.build_constraints(self)
        second_pass.build_objective(self)

    def build_third(self):
        opposite_delta_p_dict = third_pass.compute_opposite_delta_p(self)
        third_pass.build_variables(self, opposite_delta_p_dict)
        third_pass.build_constraints(self, opposite_delta_p_dict)
        third_pass.build_objective(self, opposite_delta_p_dict)

    ##################################
    # Price groups — shared across the three passes
    ##################################
    # Generator of border ranks and names of neighbour area for each border of a given market area:
    def get_market_area_neighbours(self, mc_market_area_name: str) -> list[tuple[MarketBorderMC, str]]:
        neighbours_area = []
        for mc_border in self.input_dataset.mc_market_borders.values():
            neighbour_area = (
                mc_border.downhill_market_area
                if mc_border.uphill_market_area.name == mc_market_area_name
                else mc_border.uphill_market_area
            )
            neighbours_area.append((mc_border, neighbour_area.name))
        return neighbours_area

    # Append all neighbour areas recursively as long as they are not already part of the group and the connection is not
    # saturated:
    def propagate_through_unsaturated(
        self,
        mc_market_area: MarketAreaMC,
        time_index: int,
        area_price_group: dict[str, int | None],
        price_group: PriceGroup,
    ):
        for mc_border, neighbour_market_area_name in self.get_market_area_neighbours(mc_market_area.name):
            if neighbour_market_area_name in price_group.market_area_names:
                continue
            flow = self.clearing_border_exchanges[mc_border.name, time_index]
            time = self.input_dataset.times[time_index]
            relative_max_flow = get_max_flow(mc_border, time)
            relative_min_flow = get_min_flow(mc_border, time)
            if (
                relative_min_flow + self.parameters.allowed_round_off_error
                <= flow
                <= relative_max_flow - self.parameters.allowed_round_off_error
            ):
                area_price_group[neighbour_market_area_name] = price_group.id
                price_group.market_area_names.append(neighbour_market_area_name)
                neighbour_market_area = self.input_dataset.mc_market_areas[neighbour_market_area_name]
                self.propagate_through_unsaturated(neighbour_market_area, time_index, area_price_group, price_group)

    def create_price_groups(self) -> dict[int, list[PriceGroup]]:
        price_groups: dict[int, list[PriceGroup]] = {}
        for time_index, _time in enumerate(self.input_dataset.times):
            price_groups[time_index] = []
            if self.input_dataset.is_atc:
                # Initialize a dict linking each market area with a price group number:
                areas_price_group: dict[str, int | None] = {}
                for market_area_name in self.input_dataset.mc_market_areas:
                    areas_price_group[market_area_name] = None

                for group_id, (market_area_name, mc_market_area) in enumerate(
                    self.input_dataset.mc_market_areas.items()
                ):
                    # If the current area is already allocated to a price group, go to the next one:
                    if areas_price_group[market_area_name] is not None:
                        continue
                    price_group = PriceGroup(group_id, time_index)
                    price_group.market_area_names.append(market_area_name)
                    areas_price_group[market_area_name] = group_id
                    price_groups[time_index].append(price_group)

                    # Loop over borders that are not saturated and link all possible areas inside the current group in a
                    # recursive way:
                    self.propagate_through_unsaturated(mc_market_area, time_index, areas_price_group, price_group)
            else:
                if (
                    count_saturated(self.saturated_critical_branch, time_index, self.parameters.allowed_round_off_error)
                    == 0
                ):
                    unique_price_group = PriceGroup(0, time_index)
                    unique_price_group.market_area_names = list(self.input_dataset.mc_market_areas)
                    price_groups[time_index].append(unique_price_group)
                else:
                    for group_id, market_area_name in enumerate(self.input_dataset.mc_market_areas):
                        new_price_group = PriceGroup(group_id, time_index)
                        new_price_group.market_area_names = [market_area_name]
                        price_groups[time_index].append(new_price_group)
        for price_group_list in price_groups.values():
            for price_group in price_group_list:
                self.compute_price_bounds(price_group, 1)
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
        for border_name, mc_market_border in self.input_dataset.mc_market_borders.items():
            for market_area_name in price_group.market_area_names:
                if (
                    market_area_name == mc_market_border.uphill_market_area.name
                    or market_area_name == mc_market_border.downhill_market_area.name
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
        for border_name, mc_market_border in self.input_dataset.mc_market_borders.items():
            for market_area_name in other_price_group.market_area_names:
                if (
                    market_area_name == mc_market_border.uphill_market_area.name
                    or market_area_name == mc_market_border.downhill_market_area.name
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

    def compute_price_bounds(self, price_group: PriceGroup, pricing_type: int):
        for market_area_name in price_group.market_area_names:
            time = self.input_dataset.times[price_group.time_index]
            mc_market_area = self.input_dataset.mc_market_areas[market_area_name]
            # Initialize the local bounds on order prices:
            max_accepted_sale_price = max_rejected_purchase_price = get_min_price(mc_market_area, time)
            min_rejected_sale_price = min_accepted_purchase_price = get_max_price(mc_market_area, time)

            # Select orders involved during the current time step (generator):
            current_orders = (
                mc_order
                for mc_order in mc_market_area.mc_orders.values()
                if mc_order.start_date <= time < mc_order.end_date
            )

            for mc_order in current_orders:
                current_power = self.clearing_accepted_powers[market_area_name, mc_order.name]
                # Skip complex orders to compute price bounds
                # Linked order
                if mc_order.is_linked:
                    continue

                    # Other complex order
                if mc_order.requires_status_variable is not None:
                    continue

                    # Combined accepted at their min:
                if (abs(current_power - mc_order.qmin) <= self.parameters.allowed_round_off_error) and (
                    mc_order.qmin != 0.0
                ):
                    continue

                # Compute the relevant bound:
                if mc_order.is_sale:
                    if abs(current_power) >= self.parameters.allowed_round_off_error:
                        max_accepted_sale_price = max(max_accepted_sale_price, mc_order.price)
                    else:
                        min_rejected_sale_price = min(min_rejected_sale_price, mc_order.price)
                else:
                    if abs(current_power) >= self.parameters.allowed_round_off_error:
                        min_accepted_purchase_price = min(min_accepted_purchase_price, mc_order.price)
                    else:
                        max_rejected_purchase_price = max(max_rejected_purchase_price, mc_order.price)

                # Once done with orders, deduce the bounds on the group price:
                # In the first pricing, these bounds are computed taking into account both accepted and rejected orders
            if pricing_type == 1:
                price_group.min_price = max(price_group.min_price, max_accepted_sale_price, max_rejected_purchase_price)
                price_group.max_price = min(price_group.max_price, min_rejected_sale_price, min_accepted_purchase_price)
                # In the second, rejected orders are not taken into account to compute the price bounds
            else:
                price_group.min_price = max(price_group.min_price, max_accepted_sale_price)
                price_group.max_price = min(price_group.max_price, min_accepted_purchase_price)

    def get_market_prices(self) -> dict[tuple[str, int], float]:
        """
        :rtype: dict[tuple[str, int], float]
        """
        market_prices = {}
        for time_index, price_groups in self.price_groups.items():
            for price_group in price_groups:
                for market_area_name in price_group.market_area_names:
                    market_price_name = constants.price_on_group_variable_name(price_group.id, time_index)
                    market_prices[market_area_name, time_index] = self.model.get_variable(
                        market_price_name
                    ).solution_value()
        return market_prices
