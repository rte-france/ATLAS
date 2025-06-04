"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
from atlas.modules.market_clearing.market_clearing_input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.market_clearing_parameters import MarketClearingParameters

# Static definition of default bounds on exchanges (can be changed at will):
DEFAULT_MAX_FLOW = 10000.0
DEFAULT_MIN_FLOW = -10000.0


class ClearingVariables:
    @staticmethod
    def build(solver, input_dataset: MarketClearingInputDataset, parameters : MarketClearingParameters):
        """ Create all variables for the clearing phase model"""
        is_atc = input_dataset.parameters.exchange_constraints_type == "atc"
        ClearingVariables.create_border_exchange_variables(solver, input_dataset, is_atc)
        if input_dataset.parameters.flow_penalty_lambda_2 != 0.0:
            ClearingVariables.create_border_pos_exchanges_variables(solver, input_dataset, is_atc)
            ClearingVariables.create_border_neg_exchange_variables(solver, input_dataset, is_atc)

        if is_atc:
            ClearingVariables.create_border_imports_variables(solver, input_dataset)
            ClearingVariables.create_border_exports_variables(solver, input_dataset)
            ClearingVariables.create_border_xsis_variables(solver, input_dataset)
            ClearingVariables.create_border_nus_variables(solver, input_dataset)

        ClearingVariables.create_local_balances_variables(solver, input_dataset)
        ClearingVariables.create_accepted_powers(solver, input_dataset)
        ClearingVariables.create_orders_status(solver, input_dataset)


    @staticmethod
    def create_border_exchange_variables(solver, input_dataset: MarketClearingInputDataset, is_atc: bool):
        for border in input_dataset.borders:
            for time_index, time in enumerate(input_dataset.times):
                relative_max_flow = border.max_flow.get_value(time).sum() if is_atc else DEFAULT_MAX_FLOW
                relative_min_flow = border.min_flow.get_value(time).sum() if is_atc else DEFAULT_MIN_FLOW
                solver.NumVar(
                    relative_min_flow,
                    relative_max_flow,
                    ClearingVariables.border_exchange_variable_name(border.name, time_index)
                )

    @staticmethod
    def create_border_pos_exchanges_variables(solver, input_dataset: MarketClearingInputDataset, is_atc: bool):
        for border in input_dataset.borders:
            for time_index, time in enumerate(input_dataset.times):
                relative_max_flow = border.max_flow.get_value(time).sum() if is_atc else DEFAULT_MAX_FLOW
                solver.NumVar(
                    0.0,
                    relative_max_flow,
                    ClearingVariables.border_pos_exchange_variable_name(border.name, time_index)
                )

    @staticmethod
    def create_border_neg_exchange_variables(solver, input_dataset: MarketClearingInputDataset, is_atc: bool):
        for border in input_dataset.borders:
            for time_index, time in enumerate(input_dataset.times):
                relative_min_flow = border.min_flow.get_value(time).sum() if is_atc else DEFAULT_MIN_FLOW
                solver.NumVar(
                    relative_min_flow,
                    0.0,
                    ClearingVariables.border_pos_exchange_variable_name(border.name, time_index)
                )
    @staticmethod
    def create_border_imports_variables(solver, input_dataset: MarketClearingInputDataset):
        for border in input_dataset.borders:
            for time_index, time in enumerate(input_dataset.times):
                solver.NumVar(
                    -float("inf"), float("inf"), ClearingVariables.border_import_variable_name(border.name, time_index)
                )

    @staticmethod
    def create_border_exports_variables(solver, input_dataset: MarketClearingInputDataset):
        for border in input_dataset.borders:
            for time_index, time in enumerate(input_dataset.times):
                solver.NumVar(
                    -float("inf"), float("inf"), ClearingVariables.border_export_variable_name(border.name, time_index)
                )

    @staticmethod
    def create_border_xsis_variables(solver, input_dataset: MarketClearingInputDataset):
        for border in input_dataset.borders:
            for time_index, time in enumerate(input_dataset.times):
                solver.NumVar(
                    -float("inf"), float("inf"), ClearingVariables.border_xsis_variable_name(border.name, time_index)
                )

    @staticmethod
    def create_border_nus_variables(solver, input_dataset: MarketClearingInputDataset):
        for border in input_dataset.borders:
            for time_index, time in enumerate(input_dataset.times):
                solver.NumVar(
                    -float("inf"), float("inf"), ClearingVariables.border_nus_variable_name(border.name, time_index)
                )

    @staticmethod
    def create_local_balances_variables(solver, input_dataset: MarketClearingInputDataset):
        for market_area in input_dataset.mc_market_areas:
            for time_index, time in enumerate(input_dataset.times):
                solver.NumVar(
                    -float("inf"), float("inf"),
                    ClearingVariables.local_balance_variable_name(market_area.name, time_index)
                )

    @staticmethod
    def create_accepted_powers(solver, input_dataset: MarketClearingInputDataset):
        for market_area in input_dataset.mc_market_areas:
            for mc_order in input_dataset.orders_per_market_area[market_area.market_area.name]:
                if mc_order.order.q_min:
                    min_power = 0.0
                    max_power = mc_order.order.q_max
                    solver.NumVar(
                        min_power, max_power, ClearingVariables.accepted_power_variable_name(mc_order.order.name)
                    )
                else:
                    solver.NumVar(
                        -float("inf"), float("inf"), ClearingVariables.accepted_power_variable_name(mc_order.order.name)
                    )

    @staticmethod
    def create_orders_status(solver, input_dataset: MarketClearingInputDataset):
        for market_area in input_dataset.mc_market_areas:
            for mc_order in input_dataset.orders_per_market_area[market_area.market_area.name]:
                if mc_order.id_with_status:
                    solver.BoolVar(ClearingVariables.order_status_variable_name(mc_order.order.name))

    @staticmethod
    def border_exchange_variable_name(border_name: str, time_index: int) -> str:
        return f"balance_on_{border_name}_at_{time_index}"

    @staticmethod
    def border_pos_exchange_variable_name(border_name: str, time_index: int) -> str:
        return f"positive_exchange_on_{border_name}_at_{time_index}"

    @staticmethod
    def border_neg_exchange_variable_name(border_name: str, time_index: int) -> str:
        return f"negative_exchange_on_{border_name}_at_{time_index}"

    @staticmethod
    def local_balance_variable_name(area_name: str, time_index: int) -> str:
        return f"balance_on_{area_name}_at_{time_index}"

    @staticmethod
    def accepted_power_variable_name(order_name: str) -> str:
        return f"qo_{order_name}"

    @staticmethod
    def order_status_variable_name(order_name: str) -> str:
        return f"stats_{order_name}"

    @staticmethod
    def border_import_variable_name(border_name: str, time_index: int) -> str:
        return f"import_on_{border_name}_at_{time_index}"

    @staticmethod
    def border_export_variable_name(border_name: str, time_index: int) -> str:
        return f"export_on_{border_name}_at_{time_index}"

    @staticmethod
    def border_xsis_variable_name(border_name: str, time_index: int) -> str:
        return f"xsi_on_{border_name}_at_{time_index}"

    @staticmethod
    def border_nus_variable_name(border_name: str, time_index: int) -> str:
        return f"nu_on_{border_name}_at_{time_index}"
