"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Reading of solved optimisation variables back into schedules.

This module owns the knowledge of how temporal variables are named — it is the mirror image of
the dispatch components used by ``steps/``, which declare those variables. Keeping it separate from
the output dataset lets the latter deal only with writing results onto business objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import reduce
from typing import TYPE_CHECKING

from atlas.enums import ThermalDispatchState
from atlas.modules.portfolio_optimisation.input_objects.hydro import HydroPO
from atlas.modules.portfolio_optimisation.input_objects.storage import StoragePO
from atlas.modules.portfolio_optimisation.input_objects.thermal import ThermalPO

if TYPE_CHECKING:
    from atlas.math.timeseries import Timeseries
    from atlas.modules.portfolio_optimisation.input_objects import EquipmentPO
    from atlas.modules.portfolio_optimisation.utils.orchestration import SinglePortfolioResult

#: Temporal variable prefix carrying the indicator of each thermal state.
THERMAL_STATE_VARIABLES: dict[ThermalDispatchState, str] = {
    ThermalDispatchState.ON_UP: "on_up",
    ThermalDispatchState.ON_DOWN: "on_down",
    ThermalDispatchState.OFF: "off",
    ThermalDispatchState.START: "on_start",
    ThermalDispatchState.STOP: "stop",
    ThermalDispatchState.ON_FLAT: "on_flat",
}


@dataclass
class EquipmentSchedule:
    """
    Optimised schedule of a single equipment over the portfolio time window.

    :param power: Power level over the window, in MW.
    :type power: Timeseries
    :param stored_energy: Stored energy over the window, in MWh. None for equipments that carry
        no stock (everything but hydro and storage).
    :type stored_energy: Timeseries | None
    :param state_sequence: Operating state (:class:`ThermalDispatchState` value) over the window.
        None for non-thermal equipments.
    :type state_sequence: Timeseries | None
    """

    power: Timeseries
    stored_energy: Timeseries | None = None
    state_sequence: Timeseries | None = None


def extract_equipment_schedule(equipment: EquipmentPO, optimisation_result: SinglePortfolioResult) -> EquipmentSchedule:
    """
    Read the optimised schedule of an equipment from the solved variables.

    Dispatches on the equipment type: thermal units also yield a state sequence, hydro and
    storage also yield a stored energy trajectory, and every other equipment yields a plain
    power schedule.

    :param equipment: Equipment whose schedule must be read.
    :type equipment: EquipmentPO
    :param optimisation_result: Solved optimisation holding the variable values.
    :type optimisation_result: SinglePortfolioResult
    :return: The optimised schedule.
    :rtype: EquipmentSchedule

    :Example:

    >>> schedule = extract_equipment_schedule(thermal, result)  # doctest: +SKIP
    >>> schedule.state_sequence.first_value()  # doctest: +SKIP
    6.0
    """
    extractor = _EXTRACTORS.get(type(equipment), _extract_power_only)
    return extractor(equipment, optimisation_result.solution)


def _extract_thermal(equipment: ThermalPO, solution: dict[str, Timeseries]) -> EquipmentSchedule:
    """
    Read the power schedule and the operating state sequence of a thermal unit.

    The state indicators are binary and mutually exclusive, so the state is the sum of each
    indicator times its :class:`ThermalDispatchState` value; a unit with no indicator set is
    reported as :attr:`ThermalDispatchState.UNKNOWN` (0). Indicators the unit's combination
    does not use are absent from the solution.
    """
    power = solution[f"{equipment.name}_power_level"]
    state_sequence = sum(
        (
            solution[f"{prefix}_{equipment.name}"] * float(state)
            for state, prefix in THERMAL_STATE_VARIABLES.items()
            if f"{prefix}_{equipment.name}" in solution
        ),
        start=power * float(ThermalDispatchState.UNKNOWN),
    )
    return EquipmentSchedule(power=power, state_sequence=state_sequence)


def _extract_hydro(equipment: HydroPO, solution: dict[str, Timeseries]) -> EquipmentSchedule:
    """
    Read the power schedule, summed over fragments, and the stock trajectory of a hydro unit.

    A fragment too small to bid carries no variable at some timesteps, or none at all, so the
    fragments are summed on the union of their timesteps.
    """
    fragments = [
        solution[name]
        for category in equipment.fragment_data
        if (name := f"{equipment.name}_power_level_frag_{category}") in solution
    ]
    return EquipmentSchedule(
        power=reduce(lambda total, fragment: total.add_on_union(fragment, inplace=False), fragments),
        stored_energy=solution[f"{equipment.name}_stored_energy"],
    )


def _extract_storage(equipment: StoragePO, solution: dict[str, Timeseries]) -> EquipmentSchedule:
    """Read the net power schedule (sell plus negative buy) and the stock trajectory of a storage unit."""
    return EquipmentSchedule(
        power=solution[f"{equipment.name}_power_level_sell"] + solution[f"{equipment.name}_power_level_buy"],
        stored_energy=solution[f"{equipment.name}_stored_energy"],
    )


def _extract_power_only(equipment: EquipmentPO, solution: dict[str, Timeseries]) -> EquipmentSchedule:
    """Read the power schedule of an equipment carrying no stock and no operating state."""
    return EquipmentSchedule(power=solution[f"{equipment.name}_power_level"])


#: Equipment types with a dedicated extractor; anything else falls back to :func:`_extract_power_only`.
_EXTRACTORS = {
    ThermalPO: _extract_thermal,
    HydroPO: _extract_hydro,
    StoragePO: _extract_storage,
}
