"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.common.optimal_dispatch.reserves.hydro import HydroReserveHandler
from atlas.common.optimal_dispatch.reserves.renewable import RenewableReserveHandler
from atlas.common.optimal_dispatch.reserves.storage import StorageReserveHandler
from atlas.common.optimal_dispatch.reserves.thermal import ThermalReserveHandler

if TYPE_CHECKING:
    from atlas.common.optimal_dispatch.dispatch.hydro import HydroDispatch
    from atlas.common.optimal_dispatch.dispatch.thermal import ThermalDispatch
    from atlas.common.optimal_dispatch.input_objects.hydro import HydroDispatchInput
    from atlas.common.optimal_dispatch.input_objects.renewable import RenewableDispatchInput
    from atlas.common.optimal_dispatch.input_objects.storage import StorageDispatchInput
    from atlas.common.optimal_dispatch.input_objects.thermal import ThermalDispatchInput


class ReserveFactory:
    """
    Factory that creates the right :class:`ReserveHandler` for a given equipment type.

    Callers never instantiate handlers directly — they ask the factory::

        reserves = ReserveFactory.for_thermal(equipment, dispatch)
        reserves.setup(model)

    Adding support for a new equipment type means adding a new factory method here
    and a new :class:`ReserveHandler` subclass — existing code is untouched.

    :Example:

        # Thermal
        self._reserves = ReserveFactory.for_thermal(thermal_unit, self._dispatch)

        # Storage
        self._reserves = ReserveFactory.for_storage(storage_unit)
    """

    @staticmethod
    def for_thermal(equipment: ThermalDispatchInput, dispatch: ThermalDispatch) -> ThermalReserveHandler:
        """
        Create a :class:`ThermalReserveHandler` for *equipment*.

        Computes ``maximum_automated`` from the equipment's AFRR and FCR capacities.

        :param equipment: Thermal equipment (DAO or PO input object)
        :type equipment: ThermalDispatchInput
        :param dispatch: The thermal dispatch component for this unit
        :type dispatch: ThermalDispatch
        :return: Configured thermal reserve handler
        :rtype: ThermalReserveHandler
        """
        maximum_automated = (equipment.maximum_afrr or 0.0) + (equipment.maximum_fcr or 0.0)
        return ThermalReserveHandler(equipment.name, dispatch, maximum_automated)

    @staticmethod
    def for_renewable(equipment: RenewableDispatchInput) -> RenewableReserveHandler:
        """
        Create a :class:`RenewableReserveHandler` for a wind or solar *equipment*.

        Computes ``maximum_automated`` from the equipment's AFRR and FCR capacities.

        :param equipment: Renewable equipment (any input object satisfying
            :class:`~atlas.common.optimal_dispatch.input_objects.renewable.RenewableDispatchInput`)
        :return: Configured renewable reserve handler
        """
        maximum_automated = (getattr(equipment, "maximum_afrr", None) or 0.0) + (
            getattr(equipment, "maximum_fcr", None) or 0.0
        )
        return RenewableReserveHandler(equipment.name, maximum_automated)

    @staticmethod
    def for_hydro(equipment: HydroDispatchInput, dispatch: HydroDispatch) -> HydroReserveHandler:
        """
        Create a :class:`HydroReserveHandler` for *equipment*.

        :param equipment: Hydro reservoir equipment. ``maximum_afrr`` and ``maximum_fcr``
            are looked up via ``getattr`` so the dispatch input contract stays purely
            physical — reserve-procurement fields are module-specific extensions.
        :param dispatch: The hydro dispatch component — used to access ``stored_energy_var``
            when adding storage-level reserve coupling constraints.
        """
        maximum_automated = (getattr(equipment, "maximum_afrr", None) or 0.0) + (
            getattr(equipment, "maximum_fcr", None) or 0.0
        )
        return HydroReserveHandler(equipment.name, dispatch, maximum_automated)

    @staticmethod
    def for_storage(equipment: StorageDispatchInput) -> StorageReserveHandler:
        """
        Create a :class:`StorageReserveHandler` for *equipment*.

        Computes ``maximum_automated`` from the equipment's AFRR and FCR capacities.

        :param equipment: Storage equipment (DAO or PO input object)
        :type equipment: StorageDispatchInput
        :return: Configured storage reserve handler
        :rtype: StorageReserveHandler
        """
        maximum_automated = (equipment.maximum_afrr or 0.0) + (equipment.maximum_fcr or 0.0)
        return StorageReserveHandler(equipment.name, maximum_automated)
