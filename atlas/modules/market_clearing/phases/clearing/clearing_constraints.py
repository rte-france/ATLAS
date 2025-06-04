"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
from atlas.modules.market_clearing.market_clearing_input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.market_clearing_parameters import MarketClearingParameters
from atlas.modules.market_clearing.phases.clearing.clearing_variables import ClearingVariables


class ClearingConstraints:
    @staticmethod
    def build(solver, input_dataset: MarketClearingInputDataset, parameters : MarketClearingParameters):
        """ Create all constraints for the clearing phase model"""
        ClearingConstraints.create_constraint_3_4_min_constraints(solver, input_dataset, parameters)
        ClearingConstraints.create_constraint_3_4_max_constraints(solver, input_dataset)
        ClearingConstraints.create_constraint_3_8_constraints(solver, input_dataset)
        ClearingConstraints.create_constraint_3_8_1_constraints(solver, input_dataset)
        ClearingConstraints.create_constraint_3_9_constraints(solver, input_dataset)
        ClearingConstraints.create_constraint_3_10_constraints(solver, input_dataset)
        ClearingConstraints.create_parent_child_constraints(solver, input_dataset)
        ClearingConstraints.create_constraint_3_2_1_constraints(solver, input_dataset)
        ClearingConstraints.create_constraint_3_2_2_constraints(solver, input_dataset)
        ClearingConstraints.create_constraint_3_5_sold_constraints(solver, input_dataset)
        ClearingConstraints.create_constraint_3_5_bought_constraints(solver, input_dataset)
        if parameters.flow_penalty_lambda_2 != 0.0:
            ClearingConstraints.create_constraint_3_6_1b_constraints(solver, input_dataset)
            ClearingConstraints.create_constraint_3_6_1c_constraints(solver, input_dataset)
            ClearingConstraints.create_constraint_3_6_1d_constraints(solver, input_dataset)
            ClearingConstraints.create_constraint_3_6_1f_constraints(solver, input_dataset)
            ClearingConstraints.create_constraint_3_6_1g_constraints(solver, input_dataset)
        if parameters.exchange_constraints_type != "atc":
            ClearingConstraints.create_constraint_3_6_2_constraints(solver, input_dataset)
        ClearingConstraints.create_absolute_exchange_constraints(solver, input_dataset)
        ClearingConstraints.create_exchange_across_border_constraints(solver, input_dataset)

    @staticmethod
    def create_constraint_3_4_min_constraints(solver, input_dataset: MarketClearingInputDataset, parameters : MarketClearingParameters):
        for market_area in input_dataset.mc_market_areas:
            for order in input_dataset.orders_per_market_area[market_area.market_area.name]:
                # Compute the constraints limiting the accepted powers of combined,
                # indivisible and/or mutually excluding orders and linked orders (3.4):
                if order.id_with_status is not None:
                    order_status = solver.LookupVariable(ClearingVariables.order_status_variable_name(order.order.name))
                    accepted_power = solver.LookupVariable(ClearingVariables.accepted_power_variable_name(order.order.name))
                    solver.Add(
                        order_status * max(parameters.allowed_round_off_error, order.min_power)
                        <= accepted_power,
                        ClearingConstraints.constraint_3_4_min_constraint_name(market_area.market_area.name, order.order.name)
                    )

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