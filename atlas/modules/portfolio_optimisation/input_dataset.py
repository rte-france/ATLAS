"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from itertools import groupby
from typing import cast

from pendulum import DateTime

from atlas import BusinessModel, Portfolio
from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.enum import LoadType
from atlas.models.control_block import ControlBlock
from atlas.models.equipment.hydro import Hydro
from atlas.models.equipment.load import Load
from atlas.models.equipment.other_non_dispatchable import OtherNonDispatchable
from atlas.models.equipment.solar import Solar
from atlas.models.equipment.storage import Storage
from atlas.models.equipment.thermal import Thermal
from atlas.models.equipment.wind import Wind
from atlas.models.market.market_area import MarketArea
from atlas.modules.portfolio_optimisation.models import EquipmentPO
from atlas.modules.portfolio_optimisation.models.hydro import HydroPO
from atlas.modules.portfolio_optimisation.models.load import LoadPO
from atlas.modules.portfolio_optimisation.models.other_non_dispatchable import OtherNonDispatchablePO
from atlas.modules.portfolio_optimisation.models.portfolio import PortfolioPO
from atlas.modules.portfolio_optimisation.models.solar import SolarPO
from atlas.modules.portfolio_optimisation.models.storage import StoragePO
from atlas.modules.portfolio_optimisation.models.thermal.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.models.wind import WindPO
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.manual_activation import (
    is_excluded_market_area,
    should_manually_activate,
)


class PortfolioOptimisationInputDataset(AbstractDataset[PortfolioOptimisationParameters]):
    def __init__(
        self,
        input_data: dict[str, list[BusinessModel]],
        parameters: PortfolioOptimisationParameters,
    ):
        self.input_data = input_data
        self.parameters = parameters

        loads: list[LoadPO] = [LoadPO.model_validate(load.model_dump()) for load in input_data.get("load", [])]

        self.equipments: dict[str, list[EquipmentPO]] = {
            "wind": [WindPO.model_validate(wind.model_dump()) for wind in input_data.get("wind", [])],
            "storage": [StoragePO.model_validate(storage.model_dump()) for storage in input_data.get("storage", [])],
            "hydro": [HydroPO.model_validate(hydro.model_dump()) for hydro in input_data.get("hydro", [])],
            "solar": [SolarPO.model_validate(solar.model_dump()) for solar in input_data.get("solar", [])],
            "thermal": [ThermalPO.model_validate(thermal.model_dump()) for thermal in input_data.get("thermal", [])],
            "other_non_dispatchable": [
                OtherNonDispatchablePO.model_validate(other.model_dump())
                for other in input_data.get("other_non_dispatchable", [])
            ],
            "dispatchable_load": cast(
                list[EquipmentPO], [load for load in loads if load.load_type == LoadType.POWER_TO_GAS]
            ),
            "non_dispatchable_load": cast(
                list[EquipmentPO], [load for load in loads if load.load_type != LoadType.POWER_TO_GAS]
            ),
        }

        self.portfolios: list[PortfolioPO] = []
        self.portfolios_manual_activation: list[PortfolioPO] = []
        self.time_windows: dict[str, list[DateTime]] = {}

        self._create_portfolios()
        self._get_optimisation_time_window()

    def _get_optimisation_time_window(self) -> None:
        """Get the longest optimisation time periods across all portfolios."""
        self.time_windows = {
            p.name: max(
                (
                    e.get_optimisation_time_window(
                        start_date=self.parameters.start_date,
                        end_date=self.parameters.end_date - self.parameters.timestep,
                        timestep=self.parameters.timestep,
                    )
                    for eqs in p.equipments.values()
                    for e in eqs
                ),
                key=lambda tw: tw[-1],
            )
            for p in self.portfolios + self.portfolios_manual_activation
        }

    def _create_portfolios(self):
        """Collect and classify all equipment into PortfolioPO objects with manual activation handling"""

        all_equipments_with_type_and_status = []

        # Collecte de tous les équipements avec leur type et statut
        for equipment_type, equipment_list in self.equipments.items():
            for equipment in equipment_list:
                is_manual = should_manually_activate(
                    equipment, self.parameters.excluded_technologies, self.parameters.excluded_thermal_strategies
                ) or is_excluded_market_area(
                    use_forecast=self.parameters.use_forecast,
                    excluded_market_areas=self.parameters.excluded_market_areas,
                    market_area=equipment.portfolio.market_area.name,
                )
                status = "manual" if is_manual else "included"
                all_equipments_with_type_and_status.append((equipment, equipment_type, status))

        # Tri par nom de portfolio, type d'équipement et statut
        all_equipments_with_type_and_status.sort(key=lambda x: (x[0].portfolio.name, x[1], x[2]))

        for _, portfolio_items in groupby(all_equipments_with_type_and_status, key=lambda x: x[0].portfolio.name):
            portfolio_list = list(portfolio_items)

            original_portfolio: Portfolio = portfolio_list[0][0].portfolio

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

            # Création des objets PortfolioPO
            if equipment_by_type_included:
                portfolio_po = PortfolioPO(**original_portfolio.model_dump(), equipments=equipment_by_type_included)
                # Apply market validation to the MarketAreaPO based on parameters
                portfolio_po.market_area = portfolio_po.market_area.set_market_context(
                    self.parameters.market, self.parameters.use_forecast
                )
                self.portfolios.append(portfolio_po)

            if equipment_by_type_manual:
                portfolio_po_manual = PortfolioPO(
                    **original_portfolio.model_dump(), equipments=equipment_by_type_manual
                )
                # Apply market validation to the MarketAreaPO based on parameters
                portfolio_po_manual.market_area = portfolio_po_manual.market_area.set_market_context(
                    self.parameters.market, self.parameters.use_forecast
                )
                self.portfolios_manual_activation.append(portfolio_po_manual)

    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        """Return list of business model classes used in this dataset."""
        return [Thermal, Load, Hydro, Storage, Wind, Solar, Portfolio, MarketArea, ControlBlock, OtherNonDispatchable]
