"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from itertools import groupby

from atlas import (
    BusinessModel,
    Hydro,
    Load,
    MarketArea,
    MarketBorder,
    Node,
    OtherNonDispatchable,
    Portfolio,
    Solar,
    Storage,
    Thermal,
    Wind,
)
from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.enum import LoadType
from atlas.models.equipment.equipment import Equipment
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.equipment import is_excluded_market_area, should_manually_activate


class PortfolioOptimisationInputDataset(AbstractDataset[PortfolioOptimisationParameters]):
    def __init__(
        self,
        input_data: dict[str, list[BusinessModel]],
        parameters: PortfolioOptimisationParameters,
    ):
        self.input_data = input_data
        self.parameters = parameters

        self.market_area: list[MarketArea] = input_data.get("market_area", [])
        self.market_border: list[MarketBorder] = input_data.get("market_border", [])
        self.node: list[Node] = input_data.get("node", [])
        self.portfolio: list[Portfolio] = input_data.get("portfolio", [])
        self.wind: list[Wind] = input_data.get("wind", [])
        self.storage: list[Storage] = input_data.get("storage", [])
        self.hydro: list[Hydro] = input_data.get("hydro", [])
        self.solar: list[Solar] = input_data.get("solar", [])
        self.thermal: list[Thermal] = input_data.get("thermal", [])
        self.other_non_dispatchable: list[OtherNonDispatchable] = input_data.get("other_non_dispatchable", [])

        self.load: list[Load] = input_data.get("load", [])

        self.equipments: dict[str, list[type[Equipment]]] = {
            "wind": self.wind,
            "storage": self.storage,
            "hydro": self.hydro,
            "solar": self.solar,
            "thermal": self.thermal,
            "other_non_dispatchable": self.other_non_dispatchable,
            "dispatchable_load": [load for load in self.load if load.load_type == LoadType.POWER_TO_GAS],
            "non_dispatchable_load": [load for load in self.load if load.load_type != LoadType.POWER_TO_GAS],
        }

        self.portfolios: dict[str, dict[str, list[type[Equipment]]]] = {}
        self.portfolios_manual_activation: dict[str, dict[str, list[type[Equipment]]]] = {}

        self._create_portfolios()


def _create_portfolios(self):
    """Collect and classify all equipment into portfolios with manual activation handling"""

    all_equipments_with_type_and_status = []

    for equipment_type, equipment_list in self.equipments.items():
        for equipment in equipment_list:
            if is_excluded_market_area(self.parameters, equipment.portfolio):
                continue

            is_manual = should_manually_activate(self.parameters, equipment)
            status = "manual" if is_manual else "included"

            all_equipments_with_type_and_status.append((equipment, equipment_type, status))

    # Votre tri original avec le statut ajouté
    all_equipments_with_type_and_status.sort(key=lambda x: (x[0].portfolio.name, x[1], x[2]))

    # Votre groupby original adapté
    for portfolio_name, portfolio_items in groupby(
        all_equipments_with_type_and_status, key=lambda x: x[0].portfolio.name
    ):
        portfolio_list = list(portfolio_items)

        equipment_by_type_included = {}
        equipment_by_type_manual = {}

        for equipment_type, type_items in groupby(portfolio_list, key=lambda x: x[1]):
            type_list = list(type_items)

            for status, status_items in groupby(type_list, key=lambda x: x[2]):
                equipments = [equipment for equipment, _, _ in status_items]

                if status == "included":
                    equipment_by_type_included[equipment_type] = equipments
                elif status == "manual":
                    equipment_by_type_manual[equipment_type] = equipments

        if equipment_by_type_included:
            self.portfolios[portfolio_name] = equipment_by_type_included
        if equipment_by_type_manual:
            self.portfolios_manual_activation[portfolio_name] = equipment_by_type_manual
