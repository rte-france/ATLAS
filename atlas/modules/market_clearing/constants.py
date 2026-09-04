"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Every LP name is built from the timestep's :class:`pendulum.DateTime` rather than its position in
``input_dataset.times``: a name is then self-describing and stays stable whatever the simulation
window, and the module never has to convert an index back into a datetime. The datetime is
interpolated as-is; the OR-Tools exporter turns its separators into underscores, so
``2028-09-27 13:00:00+00:00`` reads as ``2028_09_27_13_00_00_00_00`` in the exported LP.

Abbreviations used throughout this file's identifiers and the LP names they generate:

- lo: linked orders (an IDENTICAL_VOLUME/IDENTICAL_RATIO/COMPLEMENT/circular-PC group)
- pc: parent-child (an order coupling of type PARENT_CHILDREN)
- idv / idr: identical volume / identical ratio (order coupling types)
- compl: complement (the COMPLEMENT order coupling type)
- qo: quantity of an order (its accepted power)
- rej: rejected
- mkt: market
- o_n / g_n: order name / (order coupling) group name
- xsis / nus: xi / nu, the auxiliary variables from the loss-factor formulation in the spec
"""

import pendulum

##################################
# Clearing Constants
##################################


# Clearing model
# Variables
def border_exchange_variable_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"exchange_on_{border_name}_at_{time}"


def border_pos_exchange_variable_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"positive_exchange_on_{border_name}_at_{time}"


def border_neg_exchange_variable_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"negative_exchange_on_{border_name}_at_{time}"


def local_balance_variable_name(market_area_name: str, time: pendulum.DateTime) -> str:
    return f"balance_on_{market_area_name}_at_{time}"


def accepted_power_variable_name(market_area_name: str, order_name: str) -> str:
    return f"qo_{market_area_name}_{order_name}"


def order_status_variable_name(market_area_name: str, order_name: str) -> str:
    return f"status_{market_area_name}_{order_name}"


def border_import_variable_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"import_on_{border_name}_at_{time}"


def border_export_variable_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"export_on_{border_name}_at_{time}"


def border_xsis_variable_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"xsi_on_{border_name}_at_{time}"


def border_nus_variable_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"nu_on_{border_name}_at_{time}"


# Constraints
def min_accepted_power_constraint_name(market_area_name: str, order_name: str) -> str:
    return f"Constraint_3_4_min_mkt_{market_area_name}_o_{order_name}"


def max_accepted_power_constraint_name(market_area_name: str, order_name: str) -> str:
    return f"Constraint_3_4_max_mkt_{market_area_name}_o_{order_name}"


def identical_volume_order_coupling_constraint_name(order_coupling_name: str, order_name: str) -> str:
    return f"Constraint_3_8_id_volume_o_n_{order_name}_group_n_{order_coupling_name}"


def identical_ratio_order_coupling_constraint_name(order_coupling_name: str, order_name: str) -> str:
    return f"Constraint_3_8_1_id_ratio_o_n_{order_name}_group_n_{order_coupling_name}"


def constraint_3_9_constraint_name(order_coupling_name: str) -> str:
    return f"C_3_9_compl_o_group_{order_coupling_name}"


def exclusion_order_coupling_constraint_name(order_coupling_name: str) -> str:
    return f"Constraint_3_10_exclusive_o_g_number_{order_coupling_name}"


def parent_child_order_coupling_constraint_name(order_coupling_name: str, market_area_name: str) -> str:
    return f"Constraint_parent_child_on_child_{market_area_name}_on_group{order_coupling_name}"


def constraint_3_2_1_constraint_name(market_area_name: str, time: pendulum.DateTime) -> str:
    return f"Constraint_3_2_1_t_{time}_mkt_{market_area_name}"


def constraint_3_2_2_constraint_name(market_area_name: str, time: pendulum.DateTime) -> str:
    return f"Constraint_3_2_2_t_{time}_mkt_{market_area_name}"


def constraint_3_5_sold_constraint_name(control_block_name: str, time: pendulum.DateTime) -> str:
    return f"Constraint_3_5_t_{time}_cblock_{control_block_name}_sold_TSO_powers"


def constraint_3_5_bought_constraint_name(control_block_name: str, time: pendulum.DateTime) -> str:
    return f"Constraint_3_5_t_{time}_cblock_{control_block_name}_bought_TSO_powers"


def constraint_3_6_1b_constraint_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"Constraint_3_6_1b_t_{time}_mkt_border_{border_name}"


def constraint_3_6_1c_constraint_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"Constraint_3_6_1c_t_{time}_mkt_border_{border_name}"


def constraint_3_6_1d_constraint_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"Constraint_3_6_1d_t_{time}_mkt_border_{border_name}"


def constraint_3_6_1f_min_constraint_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"Constraint_3_6_1f_min_t_{time}_mkt_border_{border_name}"


def constraint_3_6_1f_max_constraint_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"Constraint_3_6_1f_max_t_{time}_mkt_border_{border_name}"


def constraint_3_6_1g_min_constraint_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"Constraint_3_6_1g_min_t_{time}_mkt_border_{border_name}"


def constraint_3_6_1g_max_constraint_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"Constraint_3_6_1g_max_t_{time}_mkt_border_{border_name}"


def constraint_3_6_2_constraint_name(branch_name: str, time: pendulum.DateTime) -> str:
    return f"Constraint_3_6_2_t_{time}_cb_{branch_name}"


def absolute_exchange_constraint_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"Pos_neg_def_t_{time}_mkt_border_{border_name}"


def exchange_across_border_constraint_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"Constraint_3_7_t_{time}_mkt_border_{border_name}"


##################################
# Exchange Fixing Constants
##################################


# Exchange Fixing model
# Constraint
def constraint_4_2_constraint_name(market_area_name: str, time: pendulum.DateTime) -> str:
    return f"Constraint_4.2_at_time_{time}_on_market_area_{market_area_name}"


def absolute_timed_exchanges_constraint_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"Positive_and_negative_parts_definition_at_time_{time}_on_market_border_{border_name}"


def constraint_4_4a_min_constraint_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"Constraint_4.4a_(min)_at_time_{time}_on_market_border_{border_name}"


def constraint_4_4a_max_constraint_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"Constraint_4.4a_(max)_at_time_{time}_on_market_border_{border_name}"


def constraint_4_3a_constraint_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"Constraint_4.3a_at_time_{time}_on_market_border_{border_name}"


def constraint_4_3b_constraint_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"Constraint_4.3b_at_time_{time}_on_market_border_{border_name}"


def constraint_4_3d_min_constraint_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"Constraint_4.3d_(min)_at_time_{time}_on_market_border {border_name}"


def constraint_4_3d_max_constraint_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"Constraint_4.3d_(max)_at_time_{time}_on_market_border_{border_name}"


def constraint_4_3e_min_constraint_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"Constraint_4.3e_(min)_at_time_{time}_on_market_border_{border_name}"


def constraint_4_3e_max_constraint_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"Constraint_4.3e_(max)_at_time_{time}_on_market_border_{border_name}"


def border_exchanges_constraint_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"Constraint_4.5_at_time_{time}_on_market_border_{border_name}"


##################################
# Pricing Constants
##################################


# First Pricing model
# Variables


def price_on_group_variable_name(id: int, time: pendulum.DateTime) -> str:
    return f"price_on_group_{id}_at_{time}"


def positive_price_on_group_variable_name(id: int, time: pendulum.DateTime) -> str:
    return f"positive_price_on_group_{id}_at_{time}"


def negative_price_on_group_variable_name(id: int, time: pendulum.DateTime) -> str:
    return f"negative_price_on_group_{id}_at_{time}"


def shadow_price_variable_name(critical_branch_name: str, time: pendulum.DateTime) -> str:
    return f"shadow_price_on_cb_{critical_branch_name}_at_{time}"


def positive_price_diff_on_group_variable_name(id: int, other_id: int, time: pendulum.DateTime) -> str:
    return f"positive_price_diff_of_groups_{id}_and_{other_id}_at_{time}"


def negative_price_diff_on_group_variable_name(id: int, other_id: int, time: pendulum.DateTime) -> str:
    return f"negative_price_diff_of_groups_{id}_and_{other_id}_at_{time}"


def link_child_to_pc(index_child: int, index_pc: int):
    return f"link_s_child_{index_child}_PC_{index_pc}"


# Constraints
def shadow_price_constraint_name(critical_branch_name: str, time: pendulum.DateTime) -> str:
    return f"Complementarity_shadow_price_t_{time}_cb_{critical_branch_name}"


def adverse_flow_constraint_name(border_name: str, time: pendulum.DateTime) -> str:
    return f"prevent_adv_flow_on_{border_name}_at_{time}"


def absolute_price_group_constraint_name(id: int, time: pendulum.DateTime) -> str:
    return f"Price_pos_neg_group_{id}_t_{time}"


def positive_slack_branch_load_variable_name(id: int, other_id: int, time: pendulum.DateTime) -> str:
    return f"Pos_slack_branch_load_btw_{id}_{other_id}_at_{time}"


def negative_slack_branch_load_variable_name(id: int, other_id: int, time: pendulum.DateTime) -> str:
    return f"Neg_slack_branch_load_btw_{id}_{other_id}_at_{time}"


def price_ptdf_constraint_name(id: int, other_id: int, time: pendulum.DateTime) -> str:
    return f"price_ptdf_time_{time}_areas_{id}-{other_id}"


def price_difference_constraint_name(id: int, other_id: int, time: pendulum.DateTime) -> str:
    return f"def_price_diff_groups_{id}_and_{other_id}_at_{time}"


def linked_bids_surplus_constraint_name(index_lo: int) -> str:
    return f"positive_surplus_LO_{index_lo}"


def positive_parent_child_surplus_constraint_name(index_child: int, index_pc: int, time: pendulum.DateTime) -> str:
    return f"pos_surplus_child_{index_child}_PC_{index_pc}_t_{time}"


def negative_parent_child_surplus_constraint_name(index_pc: int) -> str:
    return f"neg_surplus_parent_PC_{index_pc}"


def pos_surplus_order_constraint_name(
    order_name: str, equipment_name: str, market_area_name: str, time: pendulum.DateTime
) -> str:
    return f"pos_surplus_order_{order_name}_area_{market_area_name}_eqpt_{equipment_name}_t_{time}"


def null_marginal_order_constraint_name(
    order_name: str, equipment_name: str, market_area_name: str, time: pendulum.DateTime
) -> str:
    return f"s_null_marginal_order_{order_name}_area_{market_area_name}_eqpt_{equipment_name}_t_{time}"


# Second Pricing model
# Variables
def worst_rej_sale_group(current_index: int, time: pendulum.DateTime) -> str:
    return f"worst_rej_sale_group_{current_index}_at_{time}"


def worst_rej_buy_group(current_index: int, time: pendulum.DateTime) -> str:
    return f"worst_rej_buy_group_{current_index}_at_{time}"


# Constraints
def pos_min_rej_sale_group_constraint_name(current_index: int, time: pendulum.DateTime) -> str:
    return f"pos_min_rej_sale_group_{current_index}_at_{time}"


def pos_max_rej_buy_group_constraint_name(current_index: int, time: pendulum.DateTime) -> str:
    return f"pos_max_rej_buy_group_{current_index}_at_{time}"


# Third Pricing model
# Variables
def delta_p_lo(index_lo: int) -> str:
    return f"delta_p_LO_{index_lo}"


def delta_p_pc(index_pc: int) -> str:
    return f"delta_p_PC_{index_pc}"


def delta_p_order(order_name: str, market_area_name: str, time: pendulum.DateTime) -> str:
    return f"delta_p_order_{order_name}_area_{market_area_name}_t_{time}"


# Constraints
def paradoxical_delta_p_lo_constraint_name(index_lo: int) -> str:
    return f"paradoxical_delta_p_LO_{index_lo}"


def paradoxical_delta_p_pc_constraint_name(index_pc: int) -> str:
    return f"paradoxical_delta_p_PC_{index_pc}"


def paradoxical_delta_p_order_constraint_name(order_name: str, market_area_name: str, time: pendulum.DateTime) -> str:
    return f"paradoxical_delta_p_order_{order_name}_area_{market_area_name}_t_{time}"
