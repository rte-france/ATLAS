"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.modules.market_clearing.market_clearing_data.market_clearing_order import MCOrder

##################################
# Clearing Constants
##################################


# Clearing model
# Variables
def border_exchange_variable_name(border_name: str, time_index: int) -> str:
    return f"exchange_on_{border_name}_at_{time_index}"


def border_pos_exchange_variable_name(border_name: str, time_index: int) -> str:
    return f"positive_exchange_on_{border_name}_at_{time_index}"


def border_neg_exchange_variable_name(border_name: str, time_index: int) -> str:
    return f"negative_exchange_on_{border_name}_at_{time_index}"


def local_balance_variable_name(area_name: str, time_index: int) -> str:
    return f"balance_on_{area_name}_at_{time_index}"


def accepted_power_variable_name(order_name: str) -> str:
    return f"qo_{order_name}"


def order_status_variable_name(order_name: str) -> str:
    return f"stats_{order_name}"


def border_import_variable_name(border_name: str, time_index: int) -> str:
    return f"import_on_{border_name}_at_{time_index}"


def border_export_variable_name(border_name: str, time_index: int) -> str:
    return f"export_on_{border_name}_at_{time_index}"


def border_xsis_variable_name(border_name: str, time_index: int) -> str:
    return f"xsi_on_{border_name}_at_{time_index}"


def border_nus_variable_name(border_name: str, time_index: int) -> str:
    return f"nu_on_{border_name}_at_{time_index}"


# Constraints
def constraint_3_4_min_constraint_name(market_area_name: str, order_name: str) -> str:
    return f"Constraint_3_4_min_mkt_{market_area_name}_o_{order_name}"


def constraint_3_4_max_constraint_name(market_area_name: str, order_name: str) -> str:
    return f"Constraint_3_4_max_mkt_{market_area_name}_o_{order_name}"


def constraint_3_8_constraint_name(coupling_group_name: str, order_name: str) -> str:
    return f"Constraint_3_8_id_volume_o_n_{order_name}_group_n_{coupling_group_name}"


def constraint_3_8_1_constraint_name(coupling_group_name: str, order_name: str) -> str:
    return f"Constraint_3_8_1_id_ratio_o_n_{order_name}_group_n_{coupling_group_name}"


def constraint_3_9_constraint_name(coupling_group_name: str) -> str:
    return f"C_3_9_compl_o_group_{coupling_group_name}"


def constraint_3_10_constraint_name(coupling_group_name: str) -> str:
    return f"Constraint_3_10_exclusive_o_g_number_{coupling_group_name}"


def constraint_parent_child_constraint_name(coupling_group_name: str, order_name: str) -> str:
    return f"Constraint_parent_child_on_child_{order_name}_on_group{coupling_group_name}"


def constraint_3_2_1_constraint_name(market_area_name: str, time_index: int) -> str:
    return f"Constraint_3_2_1_t_{time_index}_mkt_{market_area_name}"


def constraint_3_2_2_constraint_name(market_area_name: str, time_index: int) -> str:
    return f"Constraint_3_2_2_t_{time_index}_mkt_{market_area_name}"


def constraint_3_5_sold_constraint_name(control_block_name: str, time_index: int) -> str:
    return f"Constraint_3_5_t_{time_index}_cblock_{control_block_name}_sold_TSO_powers"


def constraint_3_5_bought_constraint_name(control_block_name: str, time_index: int) -> str:
    return f"Constraint_3_5_t_{time_index}_cblock_{control_block_name}_bought_TSO_powers"


def constraint_3_6_1b_constraint_name(border_name: str, time_index: int) -> str:
    return f"Constraint_3_6_1b_t_{time_index}_mkt_border_{border_name}"


def constraint_3_6_1c_constraint_name(border_name: str, time_index: int) -> str:
    return f"Constraint_3_6_1c_t_{time_index}_mkt_border_{border_name}"


def constraint_3_6_1d_constraint_name(border_name: str, time_index: int) -> str:
    return f"Constraint_3_6_1d_t_{time_index}_mkt_border_{border_name}"


def constraint_3_6_1f_constraint_name(border_name: str, time_index: int) -> str:
    return f"Constraint_3_6_1f_t_{time_index}_mkt_border_{border_name}"


def constraint_3_6_1g_constraint_name(border_name: str, time_index: int) -> str:
    return f"Constraint_3_6_1g_t_{time_index}_mkt_border_{border_name}"


def constraint_3_6_2_constraint_name(branch_name: str, time_index: int) -> str:
    return f"Constraint_3_6_2_t_{time_index}_cb_{branch_name}"


def absolute_exchange_constraint_name(border_name: str, time_index: int) -> str:
    return f"Pos_neg_def_t_{time_index}_mkt_border_{border_name}"


def exchange_across_border_constraint_name(border_name: str, time_index: int) -> str:
    return f"Pos_neg_def_t_{time_index}_mkt_border_{border_name}"


##################################
# Exchange Fixing Constants
##################################


# Exchange Fixing model
# Constraint
def constraint_4_2_constraint_name(market_area_name: str, time_index: int) -> str:
    return f"Constraint 4.2 at time {time_index} on market area {market_area_name}"


def absolute_timed_exchanges_constraint_name(border_name: str, time_index: int) -> str:
    return f"Positive and negative parts definition at time {time_index} on market border {border_name}"


def constraint_4_4a_min_constraint_name(border_name: str, time_index: int) -> str:
    return f"Constraint 4.4a (min) at time {time_index} on market border {border_name}"


def constraint_4_4a_max_constraint_name(border_name: str, time_index: int) -> str:
    return f"Constraint 4.4a (max) at time {time_index} on market border {border_name}"


def constraint_4_3a_constraint_name(border_name: str, time_index: int) -> str:
    return f"Constraint 4.3a at time {time_index} on market border {border_name}"


def constraint_4_3b_constraint_name(border_name: str, time_index: int) -> str:
    return f"Constraint 4.3b at time {time_index} on market border {border_name}"


def constraint_4_3d_min_constraint_name(border_name: str, time_index: int) -> str:
    return f"Constraint 4.3d (min) at time {time_index} on market border {border_name}"


def constraint_4_3d_max_constraint_name(border_name: str, time_index: int) -> str:
    return f"Constraint 4.3d (max) at time {time_index} on market border {border_name}"


def constraint_4_3e_min_constraint_name(border_name: str, time_index: int) -> str:
    return f"Constraint 4.3e (min) at time {time_index} on market border {border_name}"


def constraint_4_3e_max_constraint_name(border_name: str, time_index: int) -> str:
    return f"Constraint 4.3e (max) at time {time_index} on market border {border_name}"


def border_exchanges_constraint_name(border_name: str, time_index: int) -> str:
    return f"Constraint 4.5 at time {time_index} on market border {border_name}"


##################################
# Pricing Constants
##################################


# First Pricing model
# Variables
def price_on_group(price_group: str) -> str:
    return f"price_on_group_{price_group.rank}_at_{price_group.time_index}"


def positive_price_on_group(price_group: str) -> str:
    return f"positive_price_on_group_{price_group.rank}_at_{price_group.time_index}"


def negative_price_on_group(price_group: str) -> str:
    return f"negative_price_on_group_{price_group.rank}_at_{price_group.time_index}"


def positive_price_diff_on_group(price_group: str, other_price_group: str) -> str:
    return f"positive_price_diff_of_groups_{price_group.rank}_and_{other_price_group.rank}_at_{other_price_group.time_index}"


def negative_price_diff_on_group(price_group: str, other_price_group: str) -> str:
    return f"negative_price_diff_of_groups_{price_group.rank}_and_{other_price_group.rank}_at_{other_price_group.time_index}"


# Constraints
def adverse_flow_constraint_name(border_name: str, time_index: int) -> str:
    return f"prevent_adv_flow_on_{border_name}_at_{time_index}"


def absolute_price_group_constraint_name(price_group: str, time_index: int) -> str:
    return f"Price_pos_neg_group_{price_group.rank}_t_{time_index}"


def positive_slack_branch_load_constraint_name(price_group: str, other_price_group: str, time_index: int) -> str:
    return f"Pos_slack_branch_load_btw_{price_group.rank}_{other_price_group.rank}_at_{time_index}"


def negative_slack_branch_load_constraint_name(price_group: str, other_price_group: str, time_index: int) -> str:
    return f"Neg_slack_branch_load_btw_{price_group.rank}_{other_price_group.rank}_at_{time_index}"


def price_ptdf_constraint_name(price_group: str, other_price_group: str, time_index: int) -> str:
    return f"price_ptdf_time_{time_index}_areas_{price_group.rank}-{other_price_group.rank}"


def price_difference_constraint_name(price_group: str, other_price_group: str, time_index: int) -> str:
    return f"def_price_diff_groups_{price_group.rank}_and_{other_price_group.rank}_at_{time_index}"


def linked_bids_surplus_constraint_name(index_lo: int) -> str:
    return f"positive_surplus_LO_{index_lo}"


def positive_parent_child_surplus_constraint_name(index_child: int, index_pc: int, time_index: int) -> str:
    return f"pos_surplus_child_{index_child}_PC_{index_pc}_t_{time_index}"


def negative_parent_child_surplus_constraint_name(index_pc: int) -> str:
    return f"neg_surplus_parent_PC_{index_pc}"


def pos_surplus_order_constraint_name(order: MCOrder, market_area_name: str, time_index: int) -> str:
    return f"pos_surplus_order_{order.id}_area_{market_area_name}_eqpt_{order.eqpt_name}_t_{time_index}"


def null_marginal_order_constraint_name(order: MCOrder, market_area_name: str, time_index: int) -> str:
    return f"s_null_marginal_order_{order.id}_area_{market_area_name}_eqpt_{order.eqpt_name}_t_{time_index}"


# Second Pricing model
# Variables
def worst_rej_sale_group(current_index: int, time_index: int) -> str:
    return f"worst_rej_sale_group_{current_index}_at_{time_index}"


def worst_rej_buy_group(current_index: int, time_index: int) -> str:
    return f"worst_rej_buy_group_{current_index}_at_{time_index}"


# Constraints
def pos_min_rej_sale_group_constraint_name(current_index: int, time_index: int) -> str:
    return f"pos_min_rej_sale_group_{current_index}_at_{time_index}"


def pos_min_rej_buy_group_constraint_name(current_index: int, time_index: int) -> str:
    return f"pos_min_rej_buy_group_{current_index}_at_{time_index}"


# Third Pricing model
# Variables
def delta_p_lo(index_lo: int) -> str:
    return f"delta_p_LO_{index_lo}"


def delta_p_pc(index_pc: int) -> str:
    return f"delta_p_PC_{index_pc}"


def delta_p_order(order: MCOrder, market_area_name: str, time_index: int) -> str:
    return f"delta_p_order_{order.id}_area_{market_area_name}_eqpt_{order.eqpt_name}_t_{time_index}"


# Constraints
def paradoxical_delta_p_lo_constraint_name(index_lo: int) -> str:
    return f"paradoxical_delta_p_LO_{index_lo}"


def paradoxical_delta_p_pc_constraint_name(index_pc: int) -> str:
    return f"paradoxical_delta_p_PC_{index_pc}"


def paradoxical_delta_p_order_constraint_name(order: MCOrder, market_area_name: str, time_index: int) -> str:
    return f"paradoxial_delta_p_order_{order.id}_area_{market_area_name}_eqpt_{order.eqpt_name}_t_{time_index}"
