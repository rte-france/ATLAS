"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pendulum

from atlas.config import logger
from atlas.custom_errors import SolverError
from atlas.math.timeseries import Timeseries
from atlas.modules.market_clearing.data_classes import ClearingOutputs, PriceGroup
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.input_objects.market_area import MarketAreaMC
from atlas.modules.market_clearing.input_objects.market_border import MarketBorderMC
from atlas.modules.market_clearing.input_objects.order import OrderMC
from atlas.modules.market_clearing.order_links import OrderLinkResolver
from atlas.modules.market_clearing.parameters import MarketClearingParameters
from atlas.modules.market_clearing.phases._helpers import count_saturated
from atlas.modules.market_clearing.phases.pricing import first_attempt, second_attempt, third_attempt
from atlas.modules.market_clearing.phases.pricing._types import (
    PricingAttempt,
    PricingVariables,
    RelaxableConstraints,
)
from atlas.solver.models import SolverOptions
from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    # ortools-stubs does not ship pywraplp (see the solver_interface mypy override)
    from ortools.linear_solver import pywraplp  # type: ignore[attr-defined]


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
        self.clearing_accepted_powers = clearing_outputs.accepted_powers
        self.price_groups = self.create_price_groups()
        order_links = OrderLinkResolver(self.input_dataset.orders, self.input_dataset.order_couplings).resolve()
        self.linked_orders = order_links.linked_orders
        self.parent_child_orders = order_links.parent_child_orders
        self.full_link_id_by_order = order_links.full_link_id_by_order

        # Variables only depend on the clearing outputs and the price groups: they are declared here
        # so that the attempts always find them. Nothing is relaxable until the first attempt is built.
        self.variables: PricingVariables = first_attempt.build_variables(self)
        self.relaxable = RelaxableConstraints()

    def compute(self):
        """Price the cleared market, relaxing the model over up to three attempts.

        Each attempt is only built if the previous one failed. The third one is the last resort:
        if it fails too there is no price to report, so the phase raises rather than returning
        the solver's default zeros.

        :raises SolverError: If none of the three attempts produced a solution
        """
        self.build_first()
        solver_info = self.model.solve()
        output_path = self.parameters.lp_dir
        if self.parameters.solver.export_lp:
            output_path.mkdir(parents=True, exist_ok=True)
            self.model.export_model(str(output_path / "pricing_1_model.lp"))
        attempt_statuses = [solver_info.status]

        if not solver_info.is_successful:
            logger.warning(f"First pricing attempt failed ({solver_info.status.name}), trying the second one")
            self.build_second()
            solver_info = self.model.solve()
            attempt_statuses.append(solver_info.status)
            if self.parameters.solver.export_lp:
                self.model.export_model(str(output_path / "pricing_2_model.lp"))

        if not solver_info.is_successful:
            logger.warning(f"Second pricing attempt failed ({solver_info.status.name}), trying the third one")
            self.build_third()
            solver_info = self.model.solve()
            attempt_statuses.append(solver_info.status)
            if self.parameters.solver.export_lp:
                self.model.export_model(str(output_path / "pricing_3_model.lp"))

        if not solver_info.is_successful:
            raise SolverError(
                "Pricing failed: all pricing attempts finished without a solution "
                f"({', '.join(status.name for status in attempt_statuses)}). Market prices cannot be computed."
            )

        if self.parameters.solver.export_lp:
            with open(output_path / "pricing_market_prices.json", "w") as f:
                json.dump(
                    [
                        [market_area_name, str(time), val]
                        for market_area_name, prices in self.get_market_prices().items()
                        for time, val in prices.iter_rows()
                    ],
                    f,
                )

    def build_first(self) -> None:
        first_attempt.instantiate_order_group_index(self)
        self.relaxable = first_attempt.build_constraints(self)
        first_attempt.build_objective(self)

    def build_second(self) -> None:
        # Update PriceGroup
        second_attempt.tighten_price_bounds(self)
        second_attempt.compute_worst_rejected_prices(self)
        rejection = second_attempt.build_variables(self)
        # Relax the null surplus of the marginally accepted orders, penalize the worst rejected ones instead
        second_attempt.build_constraints(self, rejection)
        second_attempt.build_objective(self, rejection)

    def build_third(self) -> None:
        opposite_delta_p_dict = third_attempt.compute_opposite_delta_p(self)
        paradox = third_attempt.build_variables(self, opposite_delta_p_dict)
        third_attempt.build_constraints(self, paradox, opposite_delta_p_dict)
        third_attempt.build_objective(self, paradox)

    ##################################
    # Orders — shared across the three attempts
    ##################################
    def is_accepted(self, order: OrderMC) -> bool:
        """Tell whether the clearing accepted a power above the round-off error for *order*."""
        return (
            self.clearing_accepted_powers[order.market_area.name, order.name] > self.parameters.allowed_round_off_error
        )

    def order_price(self, order: OrderMC) -> pywraplp.Variable:
        """Get the price variable of the group *order* belongs to, at the time the order starts.

        :raises ValueError: If the order belongs to no price group
        """
        if order.group_index is None:
            raise ValueError(f"Order '{order.name}' belongs to no price group")
        return self.variables.price[order.group_index][order.start_date]

    def standalone_orders(self) -> Iterator[OrderMC]:
        """Iterate over the orders that belong to neither a group of linked orders nor a parent-child group."""
        for order in self.input_dataset.orders.values():
            if order.name not in self.full_link_id_by_order and order.parent_child_id is None:
                yield order

    ##################################
    # Price groups — shared across the three attempts
    ##################################
    # Borders touching a given market area, paired with the area on the other end:
    def get_market_area_neighbours(self, market_area_name: str) -> list[tuple[MarketBorderMC, str]]:
        """List the borders connected to a market area and the area on the other side of each.

        Borders that do not touch ``market_area_name`` are skipped: on a network with three areas
        or more, a border between two unrelated areas is not a connection of the queried area, and
        treating it as one would merge price groups across a link that does not exist.

        :param market_area_name: Name of the market area whose connections are looked up
        :type market_area_name: str
        :return: One ``(border, neighbour area name)`` pair per border touching the area
        :rtype: list[tuple[MarketBorderMC, str]]
        """
        neighbours_area = []
        for border in self.input_dataset.market_borders.values():
            if border.uphill_market_area.name == market_area_name:
                neighbours_area.append((border, border.downhill_market_area.name))
            elif border.downhill_market_area.name == market_area_name:
                neighbours_area.append((border, border.uphill_market_area.name))
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
            flow = self.clearing_border_exchanges[border.name].get_value(time)
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

    def get_market_prices(self) -> dict[str, Timeseries]:
        """Retrieve the price of each market area over the clearing horizon

        Price groups are rebuilt at every timestep: at each one, an area takes the price of the
        group it belongs to.

        :rtype: dict[str, Timeseries]
        """
        group_prices = {
            group_id: dict(zip(price.model_times, price.solution_values(), strict=True))
            for group_id, price in self.variables.price.items()
        }
        area_prices: dict[str, list[float]] = {name: [] for name in self.input_dataset.market_areas}
        for time in self.input_dataset.times:
            for price_group in self.price_groups[time]:
                price = group_prices[price_group.id][time]
                for market_area_name in price_group.market_area_names:
                    area_prices[market_area_name].append(price)
        times = self.input_dataset.times
        timezone = times[0].timezone_name or "UTC"
        return {
            name: Timeseries({"time": times, "value": prices}, timezone=timezone)
            for name, prices in area_prices.items()
        }
