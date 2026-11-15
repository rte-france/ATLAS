"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import cast

from atlas.modules.portfolio_optimisation.input_objects import EquipmentPO
from atlas.modules.portfolio_optimisation.input_objects.hydro import HydroPO
from atlas.modules.portfolio_optimisation.input_objects.load import LoadPO
from atlas.modules.portfolio_optimisation.input_objects.other_non_dispatchable import OtherNonDispatchablePO
from atlas.modules.portfolio_optimisation.input_objects.solar import SolarPO
from atlas.modules.portfolio_optimisation.input_objects.storage import StoragePO
from atlas.modules.portfolio_optimisation.input_objects.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.input_objects.wind import WindPO


@dataclass
class PortfolioEquipments:
    """
    Strongly-typed container for portfolio equipment organized by type.

    This replaces the previous dict[str, list[EquipmentPO]] pattern to eliminate
    the need for cast() operations and provide better type safety.

    :param thermal: List of thermal equipment
    :type thermal: list[ThermalPO]
    :param storage: List of storage equipment
    :type storage: list[StoragePO]
    :param hydro: List of hydro equipment
    :type hydro: list[HydroPO]
    :param wind: List of wind equipment
    :type wind: list[WindPO]
    :param solar: List of solar equipment
    :type solar: list[SolarPO]
    :param other_non_dispatchable: List of other non-dispatchable equipment
    :type other_non_dispatchable: list[OtherNonDispatchablePO]
    :param dispatchable_load: List of dispatchable load equipment
    :type dispatchable_load: list[LoadPO]
    :param non_dispatchable_load: List of non-dispatchable load equipment
    :type non_dispatchable_load: list[LoadPO]
    """

    thermal: list[ThermalPO] = field(default_factory=list)
    storage: list[StoragePO] = field(default_factory=list)
    hydro: list[HydroPO] = field(default_factory=list)
    wind: list[WindPO] = field(default_factory=list)
    solar: list[SolarPO] = field(default_factory=list)
    other_non_dispatchable: list[OtherNonDispatchablePO] = field(default_factory=list)
    dispatchable_load: list[LoadPO] = field(default_factory=list)
    non_dispatchable_load: list[LoadPO] = field(default_factory=list)

    def get_all_equipment(self) -> list[EquipmentPO]:
        """
        Return all equipment as a flat list.

        :return: List of all equipment across all types
        :rtype: list[EquipmentPO]
        """
        return (
            self.thermal
            + self.storage
            + self.hydro
            + self.wind
            + self.solar
            + self.other_non_dispatchable
            + self.dispatchable_load
            + self.non_dispatchable_load
        )

    def iter_by_type(self) -> Iterator[tuple[str, list[EquipmentPO]]]:
        """
        Iterate over equipment grouped by type.

        Yields tuples of (equipment_type_name, equipment_list) for each equipment type.
        This method is provided for backward compatibility with code that expects to iterate
        over equipment by type name.

        :return: Iterator of (equipment_type_name, equipment_list) tuples
        :rtype: Iterator[tuple[str, list[EquipmentPO]]]
        """
        yield ("thermal", cast(list[EquipmentPO], self.thermal))
        yield ("storage", cast(list[EquipmentPO], self.storage))
        yield ("hydro", cast(list[EquipmentPO], self.hydro))
        yield ("wind", cast(list[EquipmentPO], self.wind))
        yield ("solar", cast(list[EquipmentPO], self.solar))
        yield ("other_non_dispatchable", cast(list[EquipmentPO], self.other_non_dispatchable))
        yield ("dispatchable_load", cast(list[EquipmentPO], self.dispatchable_load))
        yield ("non_dispatchable_load", cast(list[EquipmentPO], self.non_dispatchable_load))

    def iter_by_type_for_optimisation(self) -> Iterator[tuple[str, list[EquipmentPO]]]:
        """
        Iterate over equipment grouped by type. This methods is used to iterate over equipments that are allowed in optimisation problem.

        :return: Iterator of (equipment_type_name, equipment_list) tuples for optimisation
        :rtype: Iterator[tuple[str, list[EquipmentPO]]]
        """
        yield ("thermal", cast(list[EquipmentPO], self.thermal))
        yield ("storage", cast(list[EquipmentPO], self.storage))
        yield ("hydro", cast(list[EquipmentPO], self.hydro))
        yield ("wind", cast(list[EquipmentPO], self.wind))
        yield ("solar", cast(list[EquipmentPO], self.solar))
        yield ("dispatchable_load", cast(list[EquipmentPO], self.dispatchable_load))

    def has_generation_equipment(self) -> bool:
        """
        Check if portfolio has any generation equipment.

        :return: True if portfolio has thermal, hydro, storage, wind, or solar equipment
        :rtype: bool
        """
        return bool(self.thermal or self.hydro or self.storage or self.wind or self.solar)

    def get_reserve_equipment_types(self) -> list[tuple[str, list[EquipmentPO]]]:
        """
        Get equipment types that can provide reserves.

        :return: List of (equipment_type_name, equipment_list) tuples for reserve-capable equipment
        :rtype: list[tuple[str, list[EquipmentPO]]]
        """
        return [
            ("thermal", cast(list[EquipmentPO], self.thermal)),
            ("storage", cast(list[EquipmentPO], self.storage)),
            ("hydro", cast(list[EquipmentPO], self.hydro)),
            ("wind", cast(list[EquipmentPO], self.wind)),
            ("solar", cast(list[EquipmentPO], self.solar)),
        ]

    def get_dispatchable_equipment_types(self) -> list[tuple[str, list[EquipmentPO]]]:
        """
        Get all dispatchable equipment types.

        :return: List of (equipment_type_name, equipment_list) tuples for dispatchable equipment
        :rtype: list[tuple[str, list[EquipmentPO]]]
        """
        return [
            ("thermal", cast(list[EquipmentPO], self.thermal)),
            ("storage", cast(list[EquipmentPO], self.storage)),
            ("hydro", cast(list[EquipmentPO], self.hydro)),
            ("wind", cast(list[EquipmentPO], self.wind)),
            ("solar", cast(list[EquipmentPO], self.solar)),
            ("dispatchable_load", cast(list[EquipmentPO], self.dispatchable_load)),
        ]

    def add(self, equipment_type: str, equipment: EquipmentPO) -> None:
        """
        Add a single piece of equipment to the proper list.

        :param equipment_type: Type of equipment (e.g., 'thermal', 'storage')
        :type equipment_type: str
        :param equipment: Equipment object to add
        :type equipment: EquipmentPO
        :raises ValueError: If equipment_type is unknown
        """
        try:
            getattr(self, equipment_type).append(equipment)
        except AttributeError:
            raise ValueError(f"Unknown equipment type: {equipment_type}")  # noqa: B904
