"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""


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

    def build(self):
        """ Create all variables for the clearing phase model"""

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
