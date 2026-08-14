"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Reading of solved optimisation variables back into plain Python schedules.

This module owns the knowledge of how solver variables are named — it is the mirror image of
the constraint builders in ``steps/``, which create those variables. Keeping it separate from
the output dataset lets the latter deal only with writing results onto business objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from atlas.enums import ThermalDispatchState
from atlas.modules.portfolio_optimisation.input_objects.hydro import HydroPO
from atlas.modules.portfolio_optimisation.input_objects.storage import StoragePO
from atlas.modules.portfolio_optimisation.input_objects.thermal import ThermalPO

if TYPE_CHECKING:
    from pendulum import DateTime

    from atlas.modules.portfolio_optimisation.input_objects import EquipmentPO
    from atlas.modules.portfolio_optimisation.utils.orchestration import PortfolioOptimisationResult

#: Solver variable prefix carrying the indicator of each thermal state.
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
    Optimised schedule of a single equipment over the target times.

    :param power: Power level for each target time, in MW.
    :type power: list[float]
    :param stored_energy: Stored energy for each target time, in MWh. Empty for equipments
        that carry no stock (everything but hydro and storage).
    :type stored_energy: list[float]
    :param state_sequence: Operating state for each target time. Empty for non-thermal equipments.
    :type state_sequence: list[ThermalDispatchState]
    """

    power: list[float] = field(default_factory=list)
    stored_energy: list[float] = field(default_factory=list)
    state_sequence: list[ThermalDispatchState] = field(default_factory=list)


def extract_equipment_schedule(
    equipment: EquipmentPO,
    optimisation_result: PortfolioOptimisationResult,
    target_times: list[DateTime],
    allowed_round_off_error: float,
) -> EquipmentSchedule:
    """
    Read the optimised schedule of an equipment from the solved variables.

    Dispatches on the equipment type: thermal units also yield a state sequence, hydro and
    storage also yield a stored energy trajectory, and every other equipment yields a plain
    power schedule.

    :param equipment: Equipment whose schedule must be read.
    :type equipment: EquipmentPO
    :param optimisation_result: Solved optimisation holding the variable values.
    :type optimisation_result: PortfolioOptimisationResult
    :param target_times: Times over which the schedule is read.
    :type target_times: list[DateTime]
    :param allowed_round_off_error: Power below which the schedule is snapped to zero, in MW.
    :type allowed_round_off_error: float
    :return: The optimised schedule.
    :rtype: EquipmentSchedule

    :Example:

    >>> schedule = extract_equipment_schedule(thermal, result, times, 0.01)  # doctest: +SKIP
    >>> schedule.state_sequence[0]  # doctest: +SKIP
    <ThermalDispatchState.ON_FLAT: 6>
    """
    if isinstance(equipment, ThermalPO):
        return _extract_thermal(equipment, optimisation_result, target_times, allowed_round_off_error)
    if isinstance(equipment, HydroPO):
        return _extract_hydro(equipment, optimisation_result, target_times, allowed_round_off_error)
    if isinstance(equipment, StoragePO):
        return _extract_storage(equipment, optimisation_result, target_times, allowed_round_off_error)
    return _extract_power_only(equipment, optimisation_result, target_times, allowed_round_off_error)


def _snap_to_zero(power: float, allowed_round_off_error: float) -> float:
    """
    Snap a residual solver value to zero.

    :param power: Power read from the solver, in MW.
    :type power: float
    :param allowed_round_off_error: Threshold below which the power is considered null, in MW.
    :type allowed_round_off_error: float
    :return: The power, or 0.0 if within the round-off error.
    :rtype: float
    """
    return 0.0 if abs(power) <= allowed_round_off_error else power


def _extract_thermal(
    equipment: ThermalPO,
    optimisation_result: PortfolioOptimisationResult,
    target_times: list[DateTime],
    allowed_round_off_error: float,
) -> EquipmentSchedule:
    """Read the power schedule and the operating state sequence of a thermal unit."""
    schedule = EquipmentSchedule()

    for time in target_times:
        power = optimisation_result.get_variable_value(f"{equipment.name}_power_level_{time}")
        schedule.power.append(_snap_to_zero(power, allowed_round_off_error))
        schedule.state_sequence.append(_read_thermal_state(equipment, optimisation_result, time))

    return schedule


def _read_thermal_state(
    equipment: ThermalPO, optimisation_result: PortfolioOptimisationResult, time: DateTime
) -> ThermalDispatchState:
    """
    Read the operating state of a thermal unit at a given time.

    The state indicators are mutually exclusive; the first one set wins, and a unit with no
    indicator set is reported as :attr:`ThermalDispatchState.UNKNOWN`.

    :param equipment: Thermal unit to read.
    :type equipment: ThermalPO
    :param optimisation_result: Solved optimisation holding the variable values.
    :type optimisation_result: PortfolioOptimisationResult
    :param time: Target time to read.
    :type time: DateTime
    :return: The operating state at that time.
    :rtype: ThermalDispatchState
    """
    for state, variable_prefix in THERMAL_STATE_VARIABLES.items():
        if optimisation_result.get_variable_value(f"{variable_prefix}_{equipment.name}_{time}") == 1:
            return state
    return ThermalDispatchState.UNKNOWN


def _extract_hydro(
    equipment: HydroPO,
    optimisation_result: PortfolioOptimisationResult,
    target_times: list[DateTime],
    allowed_round_off_error: float,
) -> EquipmentSchedule:
    """Read the power schedule, summed over fragments, and the stock trajectory of a hydro unit."""
    schedule = EquipmentSchedule()

    for time in target_times:
        activated_power = sum(
            optimisation_result.get_variable_value(f"{equipment.name}_power_level_frag_{category}_{time}")
            for category in equipment.fragment_data
        )
        # Hydro fragments are generation-only, so a negative sum is round-off noise, not pumping.
        schedule.power.append(0.0 if activated_power <= allowed_round_off_error else activated_power)
        schedule.stored_energy.append(optimisation_result.get_variable_value(f"{equipment.name}_stored_energy_{time}"))

    return schedule


def _extract_storage(
    equipment: StoragePO,
    optimisation_result: PortfolioOptimisationResult,
    target_times: list[DateTime],
    allowed_round_off_error: float,
) -> EquipmentSchedule:
    """Read the net power schedule (sell minus buy) and the stock trajectory of a storage unit."""
    schedule = EquipmentSchedule()

    for time in target_times:
        power = optimisation_result.get_variable_value(
            f"{equipment.name}_power_level_sell_{time}"
        ) + optimisation_result.get_variable_value(f"{equipment.name}_power_level_buy_{time}")
        schedule.power.append(_snap_to_zero(power, allowed_round_off_error))
        schedule.stored_energy.append(optimisation_result.get_variable_value(f"{equipment.name}_stored_energy_{time}"))

    return schedule


def _extract_power_only(
    equipment: EquipmentPO,
    optimisation_result: PortfolioOptimisationResult,
    target_times: list[DateTime],
    allowed_round_off_error: float,
) -> EquipmentSchedule:
    """Read the power schedule of an equipment carrying no stock and no operating state."""
    schedule = EquipmentSchedule()

    for time in target_times:
        power = optimisation_result.get_variable_value(f"{equipment.name}_power_level_{time}")
        schedule.power.append(_snap_to_zero(power, allowed_round_off_error))

    return schedule
