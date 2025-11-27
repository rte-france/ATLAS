"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import cast

from atlas.modules.portfolio_optimisation.models import EquipmentPO
from atlas.modules.portfolio_optimisation.models.hydro import HydroPO
from atlas.modules.portfolio_optimisation.models.load import LoadPO
from atlas.modules.portfolio_optimisation.models.other_non_dispatchable import OtherNonDispatchablePO
from atlas.modules.portfolio_optimisation.models.solar import SolarPO
from atlas.modules.portfolio_optimisation.models.storage import StoragePO
from atlas.modules.portfolio_optimisation.models.thermal.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.models.wind import WindPO


@dataclass
class PortfolioEquipments:
    """Strongly-typed container for portfolio equipment organized by type.

    This replaces the previous dict[str, list[EquipmentPO]] pattern to eliminate
    the need for cast() operations and provide better type safety.
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
        """Return all equipment as a flat list."""
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
        """Iterate over equipment grouped by type.

        Yields tuples of (equipment_type_name, equipment_list) for each equipment type.
        This method is provided for backward compatibility with code that expects to iterate
        over equipment by type name.
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
        """Iterate over equipment grouped by type. This methods is used to iterate over equipments that are allowed in optimisation problem"""
        yield ("thermal", cast(list[EquipmentPO], self.thermal))
        yield ("storage", cast(list[EquipmentPO], self.storage))
        yield ("hydro", cast(list[EquipmentPO], self.hydro))
        yield ("wind", cast(list[EquipmentPO], self.wind))
        yield ("solar", cast(list[EquipmentPO], self.solar))
        yield ("dispatchable_load", cast(list[EquipmentPO], self.dispatchable_load))

    def has_generation_equipment(self) -> bool:
        """Check if portfolio has any generation equipment."""
        return bool(self.thermal or self.hydro or self.storage or self.wind or self.solar)

    def get_reserve_equipment_types(self) -> list[tuple[str, list[EquipmentPO]]]:
        """Get equipment types that can provide reserves."""
        return [
            ("thermal", cast(list[EquipmentPO], self.thermal)),
            ("storage", cast(list[EquipmentPO], self.storage)),
            ("hydro", cast(list[EquipmentPO], self.hydro)),
            ("wind", cast(list[EquipmentPO], self.wind)),
            ("solar", cast(list[EquipmentPO], self.solar)),
        ]

    def get_dispatchable_equipment_types(self) -> list[tuple[str, list[EquipmentPO]]]:
        """Get all dispatchable equipment types."""
        return [
            ("thermal", cast(list[EquipmentPO], self.thermal)),
            ("storage", cast(list[EquipmentPO], self.storage)),
            ("hydro", cast(list[EquipmentPO], self.hydro)),
            ("wind", cast(list[EquipmentPO], self.wind)),
            ("solar", cast(list[EquipmentPO], self.solar)),
            ("dispatchable_load", cast(list[EquipmentPO], self.dispatchable_load)),
        ]

    def add(self, equipment_type: str, equipment: EquipmentPO) -> None:
        """Add a single piece of equipment to the proper list."""
        try:
            getattr(self, equipment_type).append(equipment)
        except AttributeError:
            raise ValueError(f"Unknown equipment type: {equipment_type}")  # noqa: B904
