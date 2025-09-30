import pendulum

import atlas.modules.market_clearing.market_clearing_constants as constants
from atlas import OptimisationModel
from atlas.modules.market_clearing.PriceGroup import PriceGroup
from atlas.modules.market_clearing.market_clearing_input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.market_clearing_parameters import MarketClearingParameters
from atlas.modules.market_clearing.models.market_area_mc import MarketAreaMC
from atlas.modules.market_clearing.models.market_border_mc import MarketBorderMC, DEFAULT_MIN_FLOW


class Pricing(OptimisationModel):
    def __init__(self,
                 input_dataset: MarketClearingInputDataset,
                 parameters: MarketClearingParameters,
                 saturated_critical_branch: dict[tuple[str, int], float],
                 exchange_fixing_border_exchanges: dict[tuple[str, int], float],
                 clearing_local_balances: dict[tuple[str, int], float],
                 clearing_accepted_powers: dict[tuple[str, int], float]):
        super().__init__(parameters.solver_name)
        self.input_dataset = input_dataset
        self.parameters = parameters
        self.saturated_critical_branch = saturated_critical_branch
        self.clearing_border_exchanges = exchange_fixing_border_exchanges
        self.clearing_local_balances = clearing_local_balances
        self.clearing_accepted_powers = clearing_accepted_powers
        self.price_groups = self.create_price_groups()
        self.first_pricing = None
        self.second_pricing = None
        self.third_pricing = None

    def run(self):
        self.build_first()
        self.solve()
        self.export_model("pricing_1_model.lp")

        self.build_second()
        self.solve()
        self.export_model("pricing_2_model.lp")

        self.build_third()
        self.solve()
        self.export_model("pricing_3_model.lp")

    def build_first(self):
        self.build_first_variables()
        self.build_first_constraints()
        self.build_first_objective()

    def build_first_variables(self):
        """Create all variables for the first pricing phase model"""
        self.create_price_variables()
        self.create_positive_price_variables()
        self.create_negative_price_variables()
        self.create_positive_diff_price_variables()
        self.create_negative_diff_price_variables()
        if self.parameters.fb_branch_load_slack_penalty:
            self.create_positive_slack_branch_load_variables()
            self.create_negative_slack_branch_load_variables()
        self.create_shadow_price_variables()

    def build_first_constraints(self):
        """Create all constraints for the first pricing phase model"""
        if self.parameters.prevent_adverse_flows:
            self.create_adverse_flow_constraint()
        if self.parameters.market_price_penalty_beta:
            self.create_absolute_price_group_constraint()
        if not self.input_dataset.is_atc:
            self.create_branch_load_constraint()
        self.create_add_price_difference_constraint()
        self.create_shadow_price_constraints()

    def build_first_objective(self):
        """Create objective function for the first pricing phase model"""
        objective = []
        if self.parameters.market_price_penalty_alpha:
            self.create_groups_prices_objective()
        if self.parameters.market_price_penalty_beta:
            self.create_absolute_price_objective()
        if not self.input_dataset.is_atc and self.parameters.fb_branch_load_slack_penalty:
            self.create_branch_load_objective()
        self.create_groups_price_diff_objective()
        self.solver.Maximize(sum(objective))

    def build_second(self):
        self.build_second_variables()
        self.build_second_constraints()
        self.build_second_objective()

    def build_second_variables(self):
        """Create all variables for the second pricing phase model"""

    def build_second_constraints(self):
        """Create all constraints for the exchange fixing phase model"""

    def build_second_objective(self):
        """Create objective function for the second pricing phase model"""
        objective = []
        self.solver.Maximize(sum(objective))

    def build_third(self):
        self.build_third_variables()
        self.build_third_constraints()
        self.build_third_objective()

    def build_third_variables(self):
        """Create all variables for the third pricing phase model"""

    def build_third_constraints(self):
        """Create all constraints for the third pricing phase model"""

    def build_third_objective(self):
        """Create objective function for the third pricing phase model"""
        objective = []
        self.solver.Maximize(sum(objective))

    ##################################
    # Variables
    ##################################
    def create_price_variables(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            for price_group in self.price_groups[time_index]:
                # FC: Louis reinitialisait les bornes de prix ici, car pour lui ca aboutissait forcement a des
                # probleme infaisable. Pour moi, il ne faut pas, car ces bornes empechent de creer une autre offre
                # paradoxalement acceptee.
                # On peut aussi les redefinir en les contraignant moins ?
                self.add_continuous_variable(
                    constants.price_on_group_variable_name(price_group.id, time_index),
                    -float("inf"),
                    float("inf"),
                )

    def create_positive_price_variables(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            for price_group in self.price_groups[time_index]:
                self.add_continuous_variable(
                    constants.positive_price_on_group_variable_name(price_group.id, time_index),
                    0.0,
                    float("inf"),
                )

    def create_negative_price_variables(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            for price_group in self.price_groups[time_index]:
                self.add_continuous_variable(
                    constants.negative_price_on_group_variable_name(price_group.id, time_index),
                    -float("inf"),
                    0.0,
                )

    def create_positive_diff_price_variables(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            price_groups = self.price_groups[time_index]
            for i in range(len(price_groups) - 1):
                for j in range(i+1,len(price_groups)):
                    self.add_continuous_variable(
                        constants.positive_price_diff_on_group_variable_name(price_groups[i].id, price_groups[j].id, time_index),
                        0.0,
                        float("inf"),
                    )

    def create_negative_diff_price_variables(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            price_groups = self.price_groups[time_index]
            for i in range(len(price_groups) - 1):
                for j in range(i+1,len(price_groups)):
                    self.add_continuous_variable(
                        constants.negative_price_diff_on_group_variable_name(price_groups[i].id, price_groups[j].id, time_index),
                        -float("inf"),
                        0.0,
                    )

    def create_shadow_price_variables(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            for critical_branch_name in self.input_dataset.mc_critical_branches:
                self.add_continuous_variable(
                    constants.shadow_price_variable_name(critical_branch_name, time_index),
                    -float("inf"),
                    0.0,
                )

    def create_positive_slack_branch_load_variables(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            price_groups = self.price_groups[time_index]
            nb_saturated = len([1 for (_, cb_time_index), value in self.saturated_critical_branch.items()
                                if value <= self.parameters.allowed_round_off_error and cb_time_index == time_index])
            if nb_saturated != 0:
                continue
            for i in range(len(price_groups) - 1):
                for j in range(i+1,len(price_groups)):
                    self.add_continuous_variable(
                        constants.positive_slack_branch_load_constraint_name(price_groups[i].id, price_groups[j].id, time_index),
                        0.0,
                        float("inf"),
                    )

    def create_negative_slack_branch_load_variables(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            price_groups = self.price_groups[time_index]
            nb_saturated = len([1 for (_, cb_time_index), value in self.saturated_critical_branch.items()
                                if value <= self.parameters.allowed_round_off_error and cb_time_index == time_index])
            if nb_saturated != 0:
                continue
            for i in range(len(price_groups) - 1):
                for j in range(i+1,len(price_groups)):
                    self.add_continuous_variable(
                        constants.negative_slack_branch_load_constraint_name(price_groups[i].id, price_groups[j].id, time_index),
                        -float("inf"),
                        0.0,
                    )

    ##################################
    # Constraints
    ##################################
    def create_shadow_price_constraints(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            for critical_branch_name in self.input_dataset.mc_critical_branches:
                shadow_price = self.get_variable(constants.shadow_price_variable_name(critical_branch_name, time_index))
                saturated_critical_branch = self.saturated_critical_branch[critical_branch_name, time_index]
                if saturated_critical_branch > 0.01:
                    self.add_constraint(
                        saturated_critical_branch * shadow_price
                        == 0.0,
                        constants.shadow_price_constraint_name(critical_branch_name, time_index),
                    )

    def create_adverse_flow_constraint(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            for border_name, mc_border in self.input_dataset.mc_market_borders.items():
                for price_group in self.price_groups[time_index]:
                    if mc_border.upstream_market.name in price_group.market_area_names:
                        price_in = self.get_variable(constants.price_on_group_variable_name(price_group.id, time_index))
                    if mc_border.downstream_market.name in price_group.market_area_names:
                        price_out = self.get_variable(constants.price_on_group_variable_name(price_group.id, time_index))
                    self.add_constraint(
                        self.clearing_border_exchanges[border_name, time_index] * (price_out - price_in)
                        >= 0.0,
                        constants.adverse_flow_constraint_name(border_name, time_index),
                    )

    def create_absolute_price_group_constraint(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            for price_group in self.price_groups[time_index]:
                positive_price = self.get_variable(constants.positive_price_on_group_variable_name(price_group.id, time_index))
                negative_price = self.get_variable(constants.negative_price_on_group_variable_name(price_group.id, time_index))
                price = self.get_variable(constants.price_on_group_variable_name(price_group.id, time_index))
                self.add_constraint(
                    positive_price + negative_price - price
                    == 0.0,
                    constants.absolute_price_group_constraint_name(price_group.id, time_index),
                )
        return

    def create_branch_load_constraint(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            price_groups = self.price_groups[time_index]
            nb_saturated = len([1 for (_, cb_time_index), value in self.saturated_critical_branch.items()
                                if value <= self.parameters.allowed_round_off_error and cb_time_index == time_index])
            if nb_saturated != 0:
                continue
            for i in range(len(price_groups) - 1):
                for j in range(i+1,len(price_groups)):
                    price = self.get_variable(constants.price_on_group_variable_name(price_groups[i].id, time_index))
                    other_price = self.get_variable(constants.price_on_group_variable_name(price_groups[j].id, time_index))
                    branch_load = price - other_price
                    if self.parameters.fb_branch_load_slack_penalty:
                        positive_slack = self.get_variable(constants.negative_slack_branch_load_constraint_name(
                            price_groups[i].id, price_groups[j].id, time_index))
                        negative_slack = self.get_variable(constants.negative_slack_branch_load_constraint_name(
                            price_groups[i].id, price_groups[j].id, time_index))
                        branch_load += positive_slack + negative_slack
                    for critical_branch_name, mc_critical_branch in self.input_dataset.mc_critical_branches.items():
                        for market_area_name in self.input_dataset.mc_market_areas:
                            if market_area_name in price_groups[i].market_area_names:
                                coeff = 1.0
                            elif market_area_name in price_groups[j].market_area_names:
                                coeff = -1.0
                            else:
                                continue

                            if market_area_name in mc_critical_branch.ptdf:
                                branch_ptdf = mc_critical_branch.ptdf[market_area_name]
                                shadow_prices_fb = self.get_variable(constants.shadow_price_variable_name(
                                    critical_branch_name, time_index))
                                branch_load += (coeff *
                                                branch_ptdf.get_value(self.convert_time_index_to_time(time_index)) *
                                                shadow_prices_fb)

                    self.add_constraint(
                        branch_load == 0.0,
                        constants.price_ptdf_constraint_name(price_groups[i].id, price_groups[j].id, time_index),
                    )

    def create_add_price_difference_constraint(self):
        for time_index, _time in enumerate(self.input_dataset.times):
            price_groups = self.price_groups[time_index]
            for i in range(len(price_groups) - 1):
                for j in range(i+1,len(price_groups)):
                    if not self.is_neighbour(price_groups[i], price_groups[j]):
                        continue
                    price = self.get_variable(constants.price_on_group_variable_name(price_groups[i].id, time_index))
                    other_price = self.get_variable(constants.price_on_group_variable_name(price_groups[j].id, time_index))
                    positive_price_diff = self.get_variable(constants.positive_price_diff_on_group_variable_name(
                            price_groups[i].id, price_groups[j].id, time_index))
                    negative_price_diff = self.get_variable(constants.negative_price_diff_on_group_variable_name(
                            price_groups[i].id, price_groups[j].id, time_index))

                    self.add_constraint(
                        positive_price_diff + negative_price_diff== price - other_price,
                        constants.price_difference_constraint_name(price_groups[i].id, price_groups[j].id, time_index),
                    )

    def create_groups_prices_objective(self):
        objective = []
        for time_index, _time in enumerate(self.input_dataset.times):
            for price_group in self.price_groups[time_index]:
                price = self.get_variable(constants.price_on_group_variable_name(price_group.id, time_index))
                objective.append(self.parameters.market_price_penalty_alpha * price)
        return self.add_objective(sum(objective), direction="maximize")

    def create_absolute_price_objective(self):
        objective = []
        for time_index, _time in enumerate(self.input_dataset.times):
            for price_group in self.price_groups[time_index]:
                positive_price = self.get_variable(
                    constants.positive_price_on_group_variable_name(price_group.id, time_index))
                negative_price = self.get_variable(
                    constants.negative_price_on_group_variable_name(price_group.id, time_index))
                objective.append(self.parameters.market_price_penalty_beta * (positive_price - negative_price))
        return self.add_objective(sum(objective), direction="maximize")

    def create_branch_load_objective(self):
        objective = []
        for time_index, _time in enumerate(self.input_dataset.times):
            nb_saturated = len([1 for (_, cb_time_index), value in self.saturated_critical_branch.items()
                                if value <= self.parameters.allowed_round_off_error and cb_time_index == time_index])
            if nb_saturated == 0:
                continue
            price_groups = self.price_groups[time_index]
            for i in range(len(price_groups) - 1):
                for j in range(i+1,len(price_groups)):
                    positive_load_slack = self.get_variable(constants.positive_slack_branch_load_constraint_name(
                        price_groups[i].id, price_groups[j].id, time_index))
                    negative_load_slack = self.get_variable(constants.negative_slack_branch_load_constraint_name(
                        price_groups[i].id, price_groups[j].id, time_index))
                    objective.append(self.parameters.fb_branch_load_slack_penalty *
                                     (positive_load_slack - negative_load_slack))
        return self.add_objective(sum(objective), direction="maximize")

    def create_groups_price_diff_objective(self):
        objective = []
        for time_index, _time in enumerate(self.input_dataset.times):
            price_groups = self.price_groups[time_index]
            for i in range(len(price_groups) - 1):
                for j in range(i+1,len(price_groups)):
                    if not self.is_neighbour(price_groups[i], price_groups[j]):
                        continue
                    positive_price_diff = self.get_variable(constants.positive_price_diff_on_group_variable_name(
                            price_groups[i].id, price_groups[j].id, time_index))
                    negative_price_diff = self.get_variable(constants.negative_price_diff_on_group_variable_name(
                            price_groups[i].id, price_groups[j].id, time_index))
                    objective.append(self.parameters.fb_branch_load_slack_penalty *
                                     (positive_price_diff - negative_price_diff))
        return self.add_objective(sum(objective), direction="maximize")

    def convert_time_index_to_time(self, time_index: int) -> pendulum.DateTime:
        return self.parameters.start_date + time_index * self.parameters.time_step

    # Generator of border ranks and names of neighbour area for each border of a given market area:
    def get_market_area_neighbours(self, mc_market_area_name: str) -> list[tuple[MarketBorderMC, str]]:
        neighbours_area = []
        for border_name, mc_border in self.input_dataset.mc_market_borders.items():
            neighbour_area = mc_border.downhill_market_area if mc_border.uphill_market_area.name == mc_market_area_name \
                else mc_border.uphill_market_area
            neighbours_area.append((mc_border, neighbour_area.name))
        return neighbours_area

    # Append all neighbour areas recursively as long as they are not already part of the group and the connection is not
    # saturated:
    def propagate_through_unsaturated(self, mc_market_area: MarketAreaMC, time_index: int,
                                      area_price_group: dict[str, int], price_group: PriceGroup):
        for mc_border, neightbour_market_area_name in self.get_market_area_neighbours(mc_market_area):
            if neightbour_market_area_name in price_group.market_area_names:
                continue
            flow = self.clearing_border_exchanges[mc_border.name, time_index]
            relative_max_flow = mc_border.max_flow.get_value(self.convert_time_index_to_time(time_index))
            relative_min_flow = mc_border.min_flow.get_value(self.convert_time_index_to_time(time_index))
            if (relative_min_flow + self.parameters.allowed_round_off_error <=
                    flow <=
                    relative_max_flow - self.parameters.allowed_round_off_error):
                area_price_group[neightbour_market_area_name] = price_group.id
                price_group.market_area_names.append(neightbour_market_area_name)
                neightbour_market_area = self.input_dataset.mc_market_areas[neightbour_market_area_name]
                self.propagate_through_unsaturated(time_index, neightbour_market_area, area_price_group, price_group)

    def create_price_groups(self) -> dict[int, list[PriceGroup]]:
        price_groups = {}
        for time_index, _time in enumerate(self.input_dataset.times):
            price_groups[time_index] = []
            if self.input_dataset.is_atc:
                # Initialize a dict linking each market area with a price group number:
                areas_price_group = {}
                for market_area_name in self.input_dataset.mc_market_areas:
                    areas_price_group[market_area_name] = None

                for id, (market_area_name, mc_market_area) in enumerate(self.input_dataset.mc_market_areas.items()):
                    # If the current area is already allocated to a price group, go to the next one:
                    if areas_price_group[market_area_name] is not None:
                        continue
                    price_group = PriceGroup(id, time_index)
                    price_group.market_area_names.append(market_area_name)
                    areas_price_group[market_area_name] = id
                    price_groups[time_index].append(price_group)

                    # Loop over borders that are not saturated and link all possible areas inside the current group in a
                    # recursive way:
                    self.propagate_through_unsaturated(mc_market_area, time_index, areas_price_group, price_group)
            else:
                nb_saturated = len([1 for (_, cb_time_index), value in self.saturated_critical_branch.items()
                                    if value <= self.parameters.allowed_round_off_error and cb_time_index == time_index])
                if nb_saturated == 0:
                    unique_price_group = PriceGroup(0, time_index)
                    unique_price_group.market_area_names = [market_area_name for market_area_name in
                                                            self.input_dataset.mc_market_areas]
                    price_groups[time_index].append(unique_price_group)
                else:
                    for id, market_area_name in enumerate(self.input_dataset.mc_market_areas):
                        new_price_group = PriceGroup(id, time_index)
                        new_price_group.market_area_names = [market_area_name]
                        price_groups[time_index].append(new_price_group)
        for price_group_list in price_groups.values():
            for price_group in price_group_list:
                self.compute_price_bounds(price_group, 1)
        return price_groups

    def is_neighbour(self, price_group: PriceGroup, other_price_group: PriceGroup) -> bool:
        """ Check if two group are neighbour

        :param price_group: PriceGroup.
        :param other_price_group: PriceGroup. The PriceGroup to check
        :return: bool. True if there are neighbour otherwise False
        """
        # Count the number of occurrences of each market border inside the
        # current group (self):
        current_borders_counts = {}
        for border_name, mc_market_border in self.input_dataset.mc_market_borders.items():
            for market_area_name in price_group.market_area_names:
                if (market_area_name == mc_market_border.uphill_market_area.name or
                        market_area_name == mc_market_border.downhill_market_area.name):
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
                if (market_area_name == mc_market_border.uphill_market_area.name or
                        market_area_name == mc_market_border.downhill_market_area.name):
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
            time = self.convert_time_index_to_time(price_group.time_index)
            mc_market_area = self.input_dataset.mc_market_areas[market_area_name]
            # Initialize the local bounds on order prices:
            max_accepted_sale_price = max_rejected_purchase_price = mc_market_area.min_price.get_value(time)
            min_rejected_sale_price = min_accepted_purchase_price = mc_market_area.max_price.get_value(time)

            # Select orders involved during the current time step (generator):
            current_orders = (mc_order for mc_order in mc_market_area.mc_orders.values()
                              if mc_order.start_date <= time < mc_order.end_date)

            # count if there are accepted orders:
            count_accepted_sales = 0
            count_accepted_buys = 0

            for mc_order in current_orders:
                current_power = self.clearing_accepted_powers[market_area_name, mc_order.name]
                # Skip complex orders to compute price bounds
                # Linked order
                if mc_order.is_linked:
                    continue

                    # Other complex order
                if mc_order.id_with_status is not None:
                    continue

                    # Combined accepted at their min:
                if (abs(current_power - mc_order.qmin) <= self.parameters.allowed_round_off_error) and (
                        mc_order.qmin != 0.0
                ):
                    continue

                # Compute the relevant bound:
                if mc_order.is_sale:
                    if abs(current_power) >= self.parameters.allowed_round_off_error:
                        count_accepted_sales += 1
                        max_accepted_sale_price = max(max_accepted_sale_price, mc_order.price)
                    else:
                        min_rejected_sale_price = min(min_rejected_sale_price, mc_order.price)
                else:
                    if abs(current_power) >= self.parameters.allowed_round_off_error:
                        count_accepted_buys += 1
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
