"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements BSPBalancingOrdersInputDataset.
"""

from typing import Any

from pendulum import DateTime
from pydantic import BaseModel

from atlas.abstract_class.dataset import AbstractDataset
from atlas.config import logger
from atlas.enums import LoadType
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.io_utils.container import Container
from atlas.modules.balancing_market_bsp_orders.input_objects.hydro import BalancingHydro
from atlas.modules.balancing_market_bsp_orders.input_objects.load import BalancingLoad
from atlas.modules.balancing_market_bsp_orders.input_objects.solar import BalancingSolar
from atlas.modules.balancing_market_bsp_orders.input_objects.storage import BalancingStorage
from atlas.modules.balancing_market_bsp_orders.input_objects.thermal import BalancingThermal
from atlas.modules.balancing_market_bsp_orders.input_objects.wind import BalancingWind
from atlas.modules.balancing_market_bsp_orders.parameters import BSPBalancingOrdersParameters
from atlas.objects.equipment.hydro import Hydro
from atlas.objects.equipment.load import Load
from atlas.objects.equipment.solar import Solar
from atlas.objects.equipment.storage import Storage
from atlas.objects.equipment.thermal import Thermal
from atlas.objects.equipment.wind import Wind
from atlas.objects.market.market_area import MarketArea
from atlas.timing import generate_datetimes

# Type alias for all balancing-eligible equipment types
BalancingEquipment = (
    BalancingHydro | BalancingStorage | BalancingLoad | BalancingWind | BalancingSolar | BalancingThermal
)

# Load types that cannot provide balancing reserves
# TODO : No power to gas ?
_NON_DISPATCHABLE_LOAD_TYPES = {LoadType.BASE_LOAD, LoadType.OTHER_NON_DISPATCHABLE_LOAD}


class BSPBalancingOrdersInputDataset(AbstractDataset[BSPBalancingOrdersParameters]):
    """Input dataset for the Balancing Orders Formulation module.

    Holds the time index, all eligible equipment instances grouped by technology,
    and the market areas resolved from the 'included_market_areas' parameter.

    Equipment instances are typed as local subclasses that enforce the presence
    of all attributes required by their respective order formulators.

    :param time_index: Ordered list of DateTime steps covering the balancing time frame,
        from start_date (inclusive) to end_date - time_step (inclusive)
    :type time_index: list[DateTime]
    :param hydro_equipments: Hydro equipment instances eligible for order formulation,
        keyed by equipment name
    :type hydro_equipments: dict[str, BalancingHydro]
    :param storage_equipments: Storage equipment instances eligible for order formulation,
        keyed by equipment name
    :type storage_equipments: dict[str, BalancingStorage]
    :param load_equipments: Load equipment instances eligible for order formulation,
        keyed by equipment name
    :type load_equipments: dict[str, BalancingLoad]
    :param wind_equipments: Wind equipment instances eligible for order formulation,
        keyed by equipment name
    :type wind_equipments: dict[str, BalancingWind]
    :param solar_equipments: Solar equipment instances eligible for order formulation,
        keyed by equipment name
    :type solar_equipments: dict[str, BalancingSolar]
    :param thermal_equipments: Thermal equipment instances eligible for order formulation,
        keyed by equipment name
    :type thermal_equipments: dict[str, BalancingThermal]
    :param market_areas: Market area instances resolved from the 'included_market_areas'
        parameter, keyed by market area name
    :type market_areas: dict[str, MarketArea]
    """

    def __init__(self, input_data: AtlasDataset, parameters: BSPBalancingOrdersParameters):
        self.input_data = input_data
        self.parameters = parameters
        self.time_index: list[DateTime] = generate_datetimes(
            parameters.temporal.start_date,
            parameters.temporal.end_date - parameters.temporal.timestep,
            parameters.temporal.timestep,
        )

        self.market_areas: dict[str, MarketArea] = self.get_market_areas(input_data.market_area)

        self.hydro_equipments: dict[str, BalancingHydro] = self.get_hydro_equipments(input_data.hydro)
        self.storage_equipments: dict[str, BalancingStorage] = self.get_storage_equipments(input_data.storage)
        self.load_equipments: dict[str, BalancingLoad] = self.get_load_equipments(input_data.load)
        self.wind_equipments: dict[str, BalancingWind] = self.get_wind_equipments(input_data.wind)
        self.solar_equipments: dict[str, BalancingSolar] = self.get_solar_equipments(input_data.solar)
        self.thermal_equipments: dict[str, BalancingThermal] = self.get_thermal_equipments(input_data.thermal)

    def get_market_areas(self, market_areas: Container[MarketArea]) -> dict[str, MarketArea]:
        """Filter and return market areas according to the 'market_area_names' parameter."""
        if self.parameters.market_area_names == "all":
            return {ma.name: ma for ma in market_areas}

        return {ma.name: ma for ma in market_areas if ma.name in self.parameters.market_area_names}

    def _is_in_included_market_area(self, equipment: Any) -> bool:
        """Check whether the equipment belongs to one of the included market areas."""
        return equipment.node.market_area.name in self.market_areas

    def _is_excluded_by_parameters(self, equipment: Any) -> bool:
        """Check whether the equipment is explicitly excluded by name or technology."""
        if equipment.name in self.parameters.excluded_equipments:
            logger.debug(f"Equipment {equipment.name} excluded by name parameter.")
            return True
        if type(equipment).__name__ in self.parameters.excluded_technologies:
            logger.debug(f"Equipment {equipment.name} excluded by technology parameter.")
            return True
        return False

    def _is_eligible(self, equipment: Any) -> bool:
        """Return True if the equipment passes all common eligibility filters."""
        return self._is_in_included_market_area(equipment) and not self._is_excluded_by_parameters(equipment)

    def get_hydro_equipments(self, equipments: Container[Hydro]) -> dict[str, BalancingHydro]:
        """Filter hydro equipments and cast them to BalancingHydro."""
        result = {}
        for equipment in equipments:
            if not isinstance(equipment, Hydro):
                continue
            if not self._is_eligible(equipment):
                continue
            equipment_dump = BSPBalancingOrdersInputDataset.shallow_dump(equipment)
            result[equipment.name] = BalancingHydro.model_validate(equipment_dump)
        return result

    def get_storage_equipments(self, equipments: Container[Storage]) -> dict[str, BalancingStorage]:
        """Filter storage equipments and cast them to BalancingStorage."""
        result = {}
        for equipment in equipments:
            if not isinstance(equipment, Storage):
                continue
            if not self._is_eligible(equipment):
                continue
            equipment_dump = BSPBalancingOrdersInputDataset.shallow_dump(equipment)
            result[equipment.name] = BalancingStorage.model_validate(equipment_dump)
        return result

    def get_load_equipments(self, equipments: Container[Load]) -> dict[str, BalancingLoad]:
        """Filter load equipments, excluding non-dispatchable types, and cast to BalancingLoad."""
        result = {}
        for equipment in equipments:
            if not isinstance(equipment, Load):
                continue
            if equipment.load_type in _NON_DISPATCHABLE_LOAD_TYPES:
                logger.debug(f"Load {equipment.name} excluded: non-dispatchable load type {equipment.load_type}.")
                continue
            if not self._is_eligible(equipment):
                continue
            equipment_dump = BSPBalancingOrdersInputDataset.shallow_dump(equipment)
            result[equipment.name] = BalancingLoad.model_validate(equipment_dump)
        return result

    def get_wind_equipments(self, equipments: Container[Wind]) -> dict[str, BalancingWind]:
        """Filter wind equipments and cast them to BalancingWind."""
        result = {}
        for equipment in equipments:
            if not isinstance(equipment, Wind):
                continue
            if not self._is_eligible(equipment):
                continue
            equipment_dump = BSPBalancingOrdersInputDataset.shallow_dump(equipment)
            result[equipment.name] = BalancingWind.model_validate(equipment_dump)
        return result

    def get_solar_equipments(self, equipments: Container[Solar]) -> dict[str, BalancingSolar]:
        """Filter solar equipments and cast them to BalancingSolar."""
        result = {}
        for equipment in equipments:
            if not isinstance(equipment, Solar):
                continue
            if not self._is_eligible(equipment):
                continue
            equipment_dump = BSPBalancingOrdersInputDataset.shallow_dump(equipment)
            result[equipment.name] = BalancingSolar.model_validate(equipment_dump)
        return result

    def get_thermal_equipments(self, equipments: Container[Thermal]) -> dict[str, BalancingThermal]:
        """Filter thermal equipments, excluding those in maintenance, and cast to BalancingThermal."""
        result = {}
        for equipment in equipments:
            if not isinstance(equipment, Thermal):
                continue
            if not self._is_eligible(equipment):
                continue
            if self._is_thermal_in_maintenance(equipment):
                logger.debug(
                    f"Thermal equipment {equipment.name} excluded: in maintenance during balancing time frame."
                )
                continue
            equipment_dump = BSPBalancingOrdersInputDataset.shallow_dump(equipment)
            result[equipment.name] = BalancingThermal.model_validate(equipment_dump)
        return result

    def _is_thermal_in_maintenance(self, equipment: Thermal) -> bool:
        """Return True if the thermal equipment is in maintenance at any point in the time index.

        A thermal unit is considered in maintenance when its maximum power is below 0.01 MW,
        or when its maximum power falls below its minimum power.
        """
        if equipment.maximum_power is None or equipment.minimum_power is None:
            return False
        for time in self.time_index:
            max_power = equipment.maximum_power.get_value(time)
            min_power = equipment.minimum_power.get_value(time)
            if max_power < 0.01 or max_power < min_power:
                return True
        return False

    @staticmethod
    def shallow_dump(model: BaseModel) -> dict[str, Any]:
        result = {}
        for name, value in model.__dict__.items():
            result[name] = value
        return result
