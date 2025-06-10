"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
##################################
# Clearing Constants
##################################

# Clearing model
# Variables
def border_exchange_variable_name(border_name: str, time_index: int) -> str:
    return f"balance_on_{border_name}_at_{time_index}"

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