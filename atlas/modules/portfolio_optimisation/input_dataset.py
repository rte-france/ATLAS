"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from itertools import groupby

from atlas.core.abstract_class.dataset import AbstractDataset
from atlas.core.io_utils.atlas_dataset import AtlasDataset
from atlas.enums import LoadType
from atlas.modules.portfolio_optimisation.input_objects.hydro import HydroPO
from atlas.modules.portfolio_optimisation.input_objects.load import LoadPO
from atlas.modules.portfolio_optimisation.input_objects.market_area import MarketAreaPO
from atlas.modules.portfolio_optimisation.input_objects.other_non_dispatchable import OtherNonDispatchablePO
from atlas.modules.portfolio_optimisation.input_objects.portfolio import PortfolioPO
from atlas.modules.portfolio_optimisation.input_objects.portfolio_equipments import PortfolioEquipments
from atlas.modules.portfolio_optimisation.input_objects.solar import SolarPO
from atlas.modules.portfolio_optimisation.input_objects.storage import StoragePO
from atlas.modules.portfolio_optimisation.input_objects.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.input_objects.wind import WindPO
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.manual_activation import (
    is_excluded_market_area,
    should_manually_activate,
)
from atlas.objects.market_operator.portfolio import Portfolio
from atlas.timing import generate_datetimes


class PortfolioOptimisationInputDataset(AbstractDataset[PortfolioOptimisationParameters]):
    def __init__(
        self,
        input_data: AtlasDataset,
        parameters: PortfolioOptimisationParameters,
    ):
        self.input_data = input_data
        self.parameters = parameters

        loads: list[LoadPO] = [LoadPO(**(dict(load))) for load in self.input_data.load]

        self.equipments = PortfolioEquipments(
            wind=[WindPO(**dict(wind)) for wind in self.input_data.wind],
            storage=[StoragePO(**dict(storage)) for storage in self.input_data.storage],
            hydro=[HydroPO(**dict(hydro)) for hydro in self.input_data.hydro],
            solar=[SolarPO(**dict(solar)) for solar in self.input_data.solar],
            thermal=[ThermalPO(**dict(thermal)) for thermal in self.input_data.thermal],
            other_non_dispatchable=[
                OtherNonDispatchablePO(**dict(other)) for other in self.input_data.other_non_dispatchable
            ],
            dispatchable_load=[load for load in loads if load.load_type == LoadType.POWER_TO_GAS],
            non_dispatchable_load=[load for load in loads if load.load_type != LoadType.POWER_TO_GAS],
        )

        self.portfolios: list[PortfolioPO] = []
        self.portfolios_manual_activation: list[PortfolioPO] = []

        self._create_portfolios()
        self._set_equipments_time_window()

    def _set_equipments_time_window(self) -> None:
        """Set the optimisation time window on each equipment individually."""
        start = self.parameters.temporal.start_date
        end = self.parameters.temporal.end_date - self.parameters.temporal.timestep
        timestep = self.parameters.temporal.timestep
        for p in self.portfolios + self.portfolios_manual_activation:
            for e in p.equipments.get_all_equipment():
                e.optimisation_time_window = generate_datetimes(
                    start=start,
                    end=end + e.additional_hours,
                    freq=timestep,
                )

    def _create_portfolios(self):
        """Collect and classify all equipment into PortfolioPO objects with manual activation handling"""

        all_equipments_with_type_and_status = []

        for equipment_type, equipment_list in self.equipments.iter_by_type():
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

        all_equipments_with_type_and_status.sort(key=lambda x: (x[0].portfolio.name, x[1], x[2]))

        for _, portfolio_items in groupby(all_equipments_with_type_and_status, key=lambda x: x[0].portfolio.name):
            portfolio_list = list(portfolio_items)

            original_portfolio: Portfolio = portfolio_list[0][0].portfolio

            equipment_included = PortfolioEquipments()
            equipment_manual = PortfolioEquipments()

            for equipment_type, type_items in groupby(portfolio_list, key=lambda x: x[1]):
                type_list = list(type_items)

                for status, status_items in groupby(type_list, key=lambda x: x[2]):
                    equipments = [equipment for equipment, _, _ in status_items]

                    if status == "included":
                        setattr(equipment_included, equipment_type, equipments)
                    elif status == "manual":
                        setattr(equipment_manual, equipment_type, equipments)

            portfolio_dict = dict(original_portfolio)
            portfolio_dict["market_area"] = MarketAreaPO(**dict(original_portfolio.market_area))

            if equipment_included.get_all_equipment():
                portfolio_dict["equipments"] = equipment_included
                portfolio_po = PortfolioPO(**portfolio_dict)
                portfolio_po.market_area = portfolio_po.market_area.set_market_context(
                    self.parameters.market, self.parameters.use_forecast
                )
                self.portfolios.append(portfolio_po)

            if equipment_manual.get_all_equipment():
                portfolio_dict["equipments"] = equipment_manual
                portfolio_po_manual = PortfolioPO(**portfolio_dict)
                portfolio_po_manual.market_area = portfolio_po_manual.market_area.set_market_context(
                    self.parameters.market, self.parameters.use_forecast
                )
                self.portfolios_manual_activation.append(portfolio_po_manual)
