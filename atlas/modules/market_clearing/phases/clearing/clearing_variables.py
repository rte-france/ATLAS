"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
from atlas.modules.market_clearing.market_clearing_input_dataset import MarketClearingInputDataset


# Static definition of default bounds on exchanges (can be changed at will):
DEFAULT_MAX_FLOW = 10000.0
DEFAULT_MIN_FLOW = -10000.0


class ClearingVariables:
    def __init__(self):
        self.border_exchanges = None
        self.border_pos_exchanges = None
        self.border_neg_exchanges = None
        self.local_balances = None
        self.accepted_powers = None
        self.orders_status = None

        # Only on flow-based
        self.border_imports = None
        self.border_exports = None
        self.border_xsis = None
        self.border_nus = None

    def build(self, input_dataset: MarketClearingInputDataset):
        """ Create all variables for the clearing phase model"""
        is_atc = input_dataset.parameters.exchange_constraints_type == "atc"
        self.create_border_exchange_variables(input_dataset, is_atc)
        if input_dataset.parameters.flow_penalty_lambda_2 != 0.0:
            self.create_border_pos_exchanges_variables(input_dataset, is_atc)
            self.create_border_neg_exchange_variables(input_dataset, is_atc)

        if is_atc:
            self.create_border_imports_variables(input_dataset)
            self.create_border_exports_variables(input_dataset)
            self.create_border_xsis_variables(input_dataset)
            self.create_border_nus_variables(input_dataset)

        self.create_local_balances_variables(input_dataset)
        self.create_accepted_powers(input_dataset)
        self.create_orders_status(input_dataset)


    def create_border_exchange_variables(self, input_dataset: MarketClearingInputDataset, is_atc: bool):
        self.border_exchanges = {}
        for border in input_dataset.borders:
            exchanges = []
            for time_index, time in enumerate(input_dataset.times):
                relative_max_flow = border.max_flow.get_value(time).sum() if is_atc else DEFAULT_MAX_FLOW
                relative_min_flow = border.min_flow.get_value(time).sum() if is_atc else DEFAULT_MIN_FLOW
                variables = 1 # TODO
                exchanges.append(variables)
            self.border_exchanges[border.name] = exchanges


    def create_border_pos_exchanges_variables(self, input_dataset: MarketClearingInputDataset, is_atc: bool):
        self.border_pos_exchanges = {}
        for border in input_dataset.borders:
            pos_exchanges = []
            for time_index, time in enumerate(input_dataset.times):
                relative_max_flow = border.max_flow.get_value(time).sum() if is_atc else DEFAULT_MAX_FLOW
                variables = 1 # TODO
                pos_exchanges.append(variables)
            self.border_pos_exchanges[border.name] = pos_exchanges

    def create_border_neg_exchange_variables(self, input_dataset: MarketClearingInputDataset, is_atc: bool):
        self.border_neg_exchanges = {}
        for border in input_dataset.borders:
            neg_exchanges = []
            for time_index, time in enumerate(input_dataset.times):
                relative_min_flow = border.min_flow.get_value(time).sum() if is_atc else DEFAULT_MIN_FLOW
                variables = 1 # TODO
                neg_exchanges.append(variables)
            self.border_neg_exchanges[border.name] = neg_exchanges

    def create_border_imports_variables(self, input_dataset: MarketClearingInputDataset):
        self.border_imports = {}
        for border in input_dataset.borders:
            border_import = []
            for time_index, time in enumerate(input_dataset.times):
                variables = 1 # TODO
                border_import.append(variables)
            self.border_imports[border.name] = border_import

    def create_border_exports_variables(self, input_dataset: MarketClearingInputDataset):
        self.border_exports = {}
        for border in input_dataset.borders:
            exports = []
            for time_index, time in enumerate(input_dataset.times):
                variables = 1 # TODO
                exports.append(variables)
            self.border_exports[border.name] = exports

    def create_border_xsis_variables(self, input_dataset: MarketClearingInputDataset):
        self.border_xsis = {}
        for border in input_dataset.borders:
            xsis = []
            for time_index, time in enumerate(input_dataset.times):
                variables = 1 # TODO
                xsis.append(variables)
            self.border_xsis[border.name] = xsis

    def create_border_nus_variables(self, input_dataset: MarketClearingInputDataset):
        self.border_nus = {}
        for border in input_dataset.borders:
            nus = []
            for time_index, time in enumerate(input_dataset.times):
                variables = 1 # TODO
                nus.append(variables)
            self.border_nus[border.name] = nus

    def create_local_balances_variables(self, input_dataset: MarketClearingInputDataset):
        self.local_balances = {}
        for market_area in input_dataset.mc_market_areas:
            local_balance = []
            for time_index, time in enumerate(input_dataset.times):
                variables = 1 # TODO
                local_balance.append(variables)
            self.local_balances[market_area.market_area.name] = local_balance

    def create_accepted_powers(self, input_dataset: MarketClearingInputDataset):
        self.accepted_powers = {}
        for market_area in input_dataset.mc_market_areas:
            accepted_power = {}
            for mc_order in input_dataset.orders_per_market_area[market_area.market_area.name]:
                if mc_order.order.q_min:
                    min_power = 0.0
                    max_power = mc_order.order.q_max
                    variables = 1 # TODO
                else:
                    variable = 1 #TODO
                accepted_power.append(variables)
            self.accepted_powers[market_area.name] = accepted_power

    def create_orders_status(self, input_dataset: MarketClearingInputDataset):
        self.orders_status = {}
        for market_area in input_dataset.mc_market_areas:
            order_status = {}
            for mc_order in input_dataset.orders_per_market_area[market_area.market_area.name]:
                if mc_order.id_with_status:
                    variable = 1 #TODO
                    order_status.append(variable)
            self.orders_status[market_area.name] = order_status

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
    def local_balance_variable_name(area_id: int, time_index: int) -> str:
        return f"balance_on_{area_id}_at_{time_index}"

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
