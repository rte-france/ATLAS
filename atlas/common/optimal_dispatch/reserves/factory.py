"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.common.optimal_dispatch.reserves.thermal import ThermalReserveHandler

if TYPE_CHECKING:
    from atlas.common.optimal_dispatch.dispatch.thermal import ThermalDispatch
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

        # Thermal (DAO or PO)
        self._reserves = ReserveFactory.for_thermal(thermal_unit, self._dispatch)

        # Storage (future)
        # self._reserves = ReserveFactory.for_storage(storage_unit, self._dispatch)
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
