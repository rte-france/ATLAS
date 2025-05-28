"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
from atlas.modules.market_clearing.phases.clearing.clearing_variables import ClearingVariables


class ClearingConstraints:
    def __init__(self, variables: ClearingVariables):
        self.variables = variables

        self.constraints_3_4_min = None
        self.constraints_3_4_max = None

        self.constraints_3_8 = None
        self.constraints_3_8_1 = None
        self.constraints_3_9 = None
        self.constraints_3_10 = None
        self.constraints_parent_child = None

        self.constraints_3_2_1 = None
        self.constraints_3_2_2 = None

        self.constraints_3_5_sold = None
        self.constraints_3_5_bought = None

        self.constraints_3_6_1b = None
        self.constraints_3_6_1c = None
        self.constraints_3_6_1d = None
        self.constraints_3_6_1f = None
        self.constraints_3_6_1g = None

        self.constraints_3_6_2 = None

        self.absolute_exchanges = None
        self.exchanges_across_borders = None

    def build(self):
        """ Create all constraints for the clearing phase model"""

    @staticmethod
    def constraint_3_4_min_constraint_name(market_area_name: str, order_name: str) -> str:
        return f"Constraint_3_4_min_mkt_{market_area_name}_o_{order_name}"

    @staticmethod
    def constraint_3_4_max_constraint_name(market_area_name: str, order_name: str) -> str:
        return f"Constraint_3_4_max_mkt_{market_area_name}_o_{order_name}"

    @staticmethod
    def constraint_3_8_constraint_name(coupling_group_name: str, order_name: str) -> str:
        return f"Constraint_3_8_id_volume_o_n_{order_name}_group_n_{coupling_group_name}"

    @staticmethod
    def constraint_3_8_1_constraint_name(coupling_group_name: str, order_name: str) -> str:
        return f"Constraint_3_8_1_id_ratio_o_n_{order_name}_group_n_{coupling_group_name}"

    @staticmethod
    def constraint_3_9_constraint_name(coupling_group_name: str) -> str:
        return f"C_3_9_compl_o_group_{coupling_group_name}"

    @staticmethod
    def constraint_3_10_constraint_name(coupling_group_name: str) -> str:
        return f"Constraint_3_10_exclusive_o_g_number_{coupling_group_name}"

    @staticmethod
    def constraint_parent_child_constraint_name(coupling_group_name: str, order_name: str) -> str:
        return f"Constraint_parent_child_on_child_{order_name}_on_group{coupling_group_name}"

    @staticmethod
    def constraint_3_2_1_constraint_name(market_area_name: str, time_index: int) -> str:
        return f"Constraint_3_2_1_t_{time_index}_mkt_{market_area_name}"

    @staticmethod
    def constraint_3_2_2_constraint_name(market_area_name: str, time_index: int) -> str:
        return f"Constraint_3_2_2_t_{time_index}_mkt_{market_area_name}"

    @staticmethod
    def constraint_3_5_sold_constraint_name(control_block_name: str, time_index: int) -> str:
        return f"Constraint_3_5_t_{time_index}_cblock_{control_block_name}_sold_TSO_powers"

    @staticmethod
    def constraint_3_5_bought_constraint_name(control_block_name: str, time_index: int) -> str:
        return f"Constraint_3_5_t_{time_index}_cblock_{control_block_name}_bought_TSO_powers"

    @staticmethod
    def constraint_3_6_1b_constraint_name(border_name: str, time_index: int) -> str:
        return f"Constraint_3_6_1b_t_{time_index}_mkt_border_{border_name}"

    @staticmethod
    def constraint_3_6_1c_constraint_name(border_name: str, time_index: int) -> str:
        return f"Constraint_3_6_1c_t_{time_index}_mkt_border_{border_name}"

    @staticmethod
    def constraint_3_6_1d_constraint_name(border_name: str, time_index: int) -> str:
        return f"Constraint_3_6_1d_t_{time_index}_mkt_border_{border_name}"

    @staticmethod
    def constraint_3_6_1f_constraint_name(border_name: str, time_index: int) -> str:
        return f"Constraint_3_6_1f_t_{time_index}_mkt_border_{border_name}"

    @staticmethod
    def constraint_3_6_1g_constraint_name(border_name: str, time_index: int) -> str:
        return f"Constraint_3_6_1g_t_{time_index}_mkt_border_{border_name}"

    @staticmethod
    def constraint_3_6_2_constraint_name(branch_name: str, time_index: int) -> str:
        return f"Constraint_3_6_2_t_{time_index}_cb_{branch_name}"

    @staticmethod
    def absolute_exchange_constraint_name(border_name: str, time_index: int) -> str:
        return f"Pos_neg_def_t_{time_index}_mkt_border_{border_name}"

    @staticmethod
    def exchange_across_border_constraint_name(border_name: str, time_index: int) -> str:
        return f"Pos_neg_def_t_{time_index}_mkt_border_{border_name}"