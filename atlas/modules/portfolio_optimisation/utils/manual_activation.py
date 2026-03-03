"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from datetime import datetime
from typing import cast

from pendulum import DateTime

from atlas.enums import MarketType, StorageType, ThermalStrategy
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.equipment import Equipment
from atlas.modules.portfolio_optimisation.models import EquipmentPO
from atlas.modules.portfolio_optimisation.models.hydro import HydroPO
from atlas.modules.portfolio_optimisation.models.load import LoadPO
from atlas.modules.portfolio_optimisation.models.other_non_dispatchable import OtherNonDispatchablePO
from atlas.modules.portfolio_optimisation.models.solar import SolarPO
from atlas.modules.portfolio_optimisation.models.storage import StoragePO
from atlas.modules.portfolio_optimisation.models.thermal.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.models.wind import WindPO
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


def set_manual_activation(equipments: list[EquipmentPO], parameters: PortfolioOptimisationParameters):
    """
    Update power matrix and stored energy for equipment portfolio based on market clearing.

    :param equipments: List of equipment objects to process
    :type equipments: list[EquipmentPO]
    :param parameters: Configuration parameters containing market type, dates, etc.
    :type parameters: PortfolioOptimisationParameters
    """
    for equipment in equipments:
        new_power = _calculate_new_power(equipment, parameters)
        activated_power = _calculate_activated_power(equipment, parameters)

        if _should_skip_equipment(equipment, activated_power, parameters):
            continue

        _apply_power_constraints(equipment, new_power, parameters)

        if isinstance(equipment, HydroPO | StoragePO):
            _update_stored_energy(equipment, new_power, parameters)

        _finalize_power_update(equipment, new_power, parameters)


def is_excluded_technology(excluded_technologies: list[str], equipment: EquipmentPO) -> bool:
    """
    Check if equipment technology is excluded.

    Supports both friendly names (e.g., 'thermal', 'storage', 'wind') and technical class names (e.g., 'ThermalPO').

    :param excluded_technologies: List of technologies to exclude
    :type excluded_technologies: list[str]
    :param equipment: Equipment instance
    :type equipment: EquipmentPO
    :return: True if equipment is excluded
    :rtype: bool
    """
    if excluded_technologies == ["all"]:
        return True

    mapping_name = {
        "thermal": "ThermalPO",
        "storage": "StoragePO",
        "wind": "WindPO",
        "solar": "SolarPO",
        "hydro": "HydroPO",
        "load": "LoadPO",
        "other_non_dispatchable": "OtherNonDispatchablePO",
    }

    equipment_class_name = equipment.__class__.__name__

    for excluded in excluded_technologies:
        if excluded.lower() in mapping_name:
            if equipment_class_name == mapping_name[excluded.lower()]:
                return True

    return False


def is_excluded_thermal_strategy(excluded_thermal_strategies: list[ThermalStrategy], equipment: ThermalPO) -> bool:
    """
    Check if thermal equipment strategy is excluded.

    :param excluded_thermal_strategies: List of thermal strategies to exclude
    :type excluded_thermal_strategies: list[ThermalStrategy]
    :param equipment: Thermal equipment instance
    :type equipment: ThermalPO
    :return: True if equipment strategy is excluded
    :rtype: bool
    """
    if isinstance(equipment, ThermalPO):
        if equipment.strategy:
            return equipment.strategy in excluded_thermal_strategies
    return False


def is_excluded_market_area(use_forecast: bool, excluded_market_areas: list[str], market_area: str) -> bool:
    """
    Check if portfolio market area is excluded.

    :param use_forecast: Whether forecast mode is used
    :type use_forecast: bool
    :param excluded_market_areas: List of market areas to exclude
    :type excluded_market_areas: list[str]
    :param market_area: Market area name
    :type market_area: str
    :return: True if market area is excluded
    :rtype: bool
    """
    return not use_forecast and market_area in excluded_market_areas if excluded_market_areas != ["all"] else True


def should_manually_activate(
    equipment: EquipmentPO,
    excluded_technologies: list[str],
    excluded_thermal_strategies: list[ThermalStrategy],
) -> bool:
    """
    Determine if equipment should be manually activated.

    :param equipment: Equipment instance
    :type equipment: EquipmentPO
    :param excluded_technologies: List of technologies to exclude
    :type excluded_technologies: list[str]
    :param excluded_thermal_strategies: List of thermal strategies to exclude
    :type excluded_thermal_strategies: list[ThermalStrategy]
    :return: True if equipment should be manually activated
    :rtype: bool
    """
    if not isinstance(equipment, ThermalPO):
        return is_excluded_technology(excluded_technologies, equipment)
    return is_excluded_technology(excluded_technologies, equipment) or is_excluded_thermal_strategy(
        excluded_thermal_strategies, equipment
    )


def _calculate_new_power(equipment: EquipmentPO, parameters: PortfolioOptimisationParameters) -> Timeseries:
    """
    Calculate new power based on market type.

    :param equipment: Equipment instance
    :type equipment: EquipmentPO
    :param parameters: Optimization parameters
    :type parameters: PortfolioOptimisationParameters
    :return: New power timeseries
    :rtype: Timeseries
    """
    if parameters.market == MarketType.dayahead:
        filtered = cast(AbstractTimeseries, equipment.da_cleared_quantity).filter(
            parameters.target_times, inplace=False
        )
        return cast(Timeseries, filtered)

    elif parameters.market == MarketType.intraday:
        da_power = cast(AbstractTimeseries, equipment.da_cleared_quantity).filter(
            parameters.target_times, inplace=False
        )
        id_power = cast(AbstractTimeseries, equipment.total_id_cleared_quantity).filter(
            parameters.target_times, inplace=False
        )
        result = da_power + id_power
        return cast(Timeseries, result)

    raise ValueError(f"Unsupported market type: {parameters.market}")


def _calculate_activated_power(equipment: Equipment, parameters: PortfolioOptimisationParameters):
    """
    Calculate activated power for validation.

    :param equipment: Equipment instance
    :type equipment: Equipment
    :param parameters: Optimization parameters
    :type parameters: PortfolioOptimisationParameters
    :return: Activated power timeseries
    :rtype: Timeseries
    """
    if parameters.market == MarketType.dayahead:
        return cast(AbstractTimeseries, equipment.da_cleared_quantity).filter(parameters.target_times, inplace=False)

    elif parameters.market == MarketType.intraday:
        return (
            cast(ForecastingMatrix | LazyForecastingMatrix, equipment.id_cleared_quantity)
            .get_forecast(parameters.execution_date, parameters.start_date, parameters.end_date)
            .filter(parameters.target_times, inplace=False)
        )


def _should_skip_equipment(
    equipment: EquipmentPO,
    activated_power: Timeseries,
    parameters: PortfolioOptimisationParameters,
) -> bool:
    """
    Check if equipment should be skipped due to zero activation.

    :param equipment: Equipment instance
    :type equipment: EquipmentPO
    :param activated_power: Activated power timeseries
    :type activated_power: Timeseries
    :param parameters: Optimization parameters
    :type parameters: PortfolioOptimisationParameters
    :return: True if equipment should be skipped
    :rtype: bool
    """
    if parameters.use_forecast:
        return False

    # Always process these equipment types
    if isinstance(equipment, WindPO | SolarPO | ThermalPO):
        return False

    # Skip if power is effectively zero
    max_power = activated_power.max()
    min_power = activated_power.abs().min()
    return max_power <= parameters.allowed_round_off_error and min_power <= parameters.allowed_round_off_error


def _apply_power_constraints(
    equipment: EquipmentPO, new_power: Timeseries, parameters: PortfolioOptimisationParameters
) -> None:
    """
    Apply power constraints based on equipment type.

    :param equipment: Equipment instance
    :type equipment: EquipmentPO
    :param new_power: New power timeseries
    :type new_power: Timeseries
    :param parameters: Optimization parameters
    :type parameters: PortfolioOptimisationParameters
    :return: None
    :rtype: None
    """
    # Preload maximum power forecast for certain equipment types
    max_power_forecast: AbstractTimeseries | None = None
    if isinstance(equipment, LoadPO | WindPO | SolarPO | OtherNonDispatchablePO):
        max_power_forecast = equipment.maximum_power_forecast.get_forecast(
            parameters.execution_date, parameters.start_date, parameters.end_date
        )

    for time, power_value in new_power.iter_rows():
        max_power = _get_max_power(equipment, time, max_power_forecast)
        if power_value > max_power:
            new_power.set_value(time, max_power)
            power_value = max_power

        if isinstance(equipment, ThermalPO | HydroPO | WindPO | SolarPO):
            if power_value < 0:
                new_power.set_value(time, 0)
                power_value = 0

        if not isinstance(equipment, ThermalPO):
            min_power = _get_min_power(equipment, time, max_power_forecast, max_power)
            if power_value < min_power:
                new_power.set_value(time, min_power)


def _get_max_power(
    equipment: EquipmentPO, time: DateTime | datetime, max_power_forecast: AbstractTimeseries | None
) -> float:
    """
    Get maximum power limit for equipment at given time.

    :param equipment: Equipment instance
    :type equipment: EquipmentPO
    :param time: Current time
    :type time: DateTime
    :param max_power_forecast: Maximum power forecast timeseries
    :type max_power_forecast: AbstractTimeseries | None
    :return: Maximum power limit
    :rtype: float
    """
    if isinstance(equipment, LoadPO):
        return 0
    elif isinstance(equipment, WindPO | SolarPO | OtherNonDispatchablePO):
        if max_power_forecast is None:
            return 0
        return max_power_forecast.get_value(time)
    else:
        if hasattr(equipment, "maximum_power") and equipment.maximum_power and time in equipment.maximum_power:
            return equipment.maximum_power.get_value(time)
        return 0


def _get_min_power(
    equipment: EquipmentPO,
    time: DateTime | datetime,
    max_power_forecast: AbstractTimeseries | None,
    max_power: float,
) -> float:
    """
    Get minimum power limit for equipment at given time.

    :param equipment: Equipment instance
    :type equipment: EquipmentPO
    :param time: Current time
    :type time: DateTime
    :param max_power_forecast: Maximum power forecast timeseries
    :type max_power_forecast: AbstractTimeseries | None
    :param max_power: Maximum power value
    :type max_power: float
    :return: Minimum power limit
    :rtype: float
    """
    if isinstance(equipment, LoadPO):
        if max_power_forecast is None:
            return 0
        return max_power_forecast.get_value(time)
    elif isinstance(equipment, WindPO | SolarPO):
        if max_power_forecast is None:
            return 0
        curtailment_ratio = equipment.maximum_curtailment_ratio.get_value(time)
        return max_power_forecast.get_value(time) * (1 - curtailment_ratio)
    elif isinstance(equipment, StoragePO | HydroPO):
        return equipment.minimum_power.get_value(time)
    elif isinstance(equipment, OtherNonDispatchablePO):
        return max_power
    else:
        return 0


def _get_energy_bounds(obj: HydroPO | StoragePO, time: DateTime):
    """
    Get energy bounds for equipment at given time.

    :param obj: Hydro or storage equipment instance
    :type obj: HydroPO | StoragePO
    :param time: Current time
    :type time: DateTime
    :return: Tuple of (min_energy, max_energy)
    :rtype: tuple[float, float]
    """
    max_energy = obj.maximum_energy.get_value(time)

    if isinstance(obj, StoragePO):
        min_energy = max_energy * obj.minimum_state_of_charge.get_value(time)
    else:  # Hydraulic
        min_energy = obj.minimum_energy.get_value(time)

    return min_energy, max_energy


def _update_stored_energy(
    equipment: HydroPO | StoragePO, new_power: Timeseries, parameters: PortfolioOptimisationParameters
) -> None:
    """
    Update stored energy for storage and hydraulic equipment.

    :param equipment: Hydro or storage equipment instance
    :type equipment: HydroPO | StoragePO
    :param new_power: New power timeseries
    :type new_power: AbstractTimeseries
    :param parameters: Optimization parameters
    :type parameters: PortfolioOptimisationParameters
    :return: None
    :rtype: None
    """

    new_stored_energy = Timeseries.from_index(
        parameters.start_date, parameters.timestep, parameters.end_date, default_value=0
    )

    initial_stored_energy = _get_initial_stored_energy(equipment, parameters)
    out_of_bounds_corrections = {}

    for index, time in enumerate(parameters.target_times):
        previous_energy = (
            initial_stored_energy if index == 0 else new_stored_energy.get_value(time - parameters.timestep)
        )

        new_energy_value = _calculate_new_energy_value(equipment, time, previous_energy, new_power, parameters)

        energy_bounds = _get_energy_bounds(equipment, time)
        corrected_energy, correction = _apply_energy_bounds(new_energy_value, energy_bounds, time, parameters)

        new_stored_energy.set_value(time, corrected_energy)

        if correction != 0:
            out_of_bounds_corrections[time] = correction

    # Apply power corrections based on energy bound violations
    _apply_power_corrections(equipment, new_power, out_of_bounds_corrections)

    # Add extra timestep for interpolation
    new_stored_energy.set_value(
        parameters.end_date + parameters.timestep,
        new_stored_energy.get_value(parameters.end_date),
    )

    # Update equipment stored energy
    if not parameters.use_forecast and equipment.stored_energy:
        stored_energy_matrix = equipment.stored_energy
        if parameters.execution_date in stored_energy_matrix:
            stored_energy_matrix.delete(parameters.execution_date)
        stored_energy_matrix.add(new_stored_energy, parameters.execution_date)


def _get_initial_stored_energy(equipment: HydroPO | StoragePO, parameters: PortfolioOptimisationParameters) -> float:
    """
    Get initial stored energy level for equipment.

    :param equipment: Hydro or storage equipment instance
    :type equipment: HydroPO | StoragePO
    :param parameters: Optimization parameters
    :type parameters: PortfolioOptimisationParameters
    :return: Initial stored energy level
    :rtype: float
    """
    stored_energy_matrix = equipment.stored_energy

    if stored_energy_matrix:
        local_stored_energy = stored_energy_matrix.get_forecast(
            parameters.execution_date,
            parameters.start_date - parameters.timestep,
            parameters.start_date,
        )

        target_time = parameters.start_date - parameters.timestep
        if local_stored_energy.first_date() <= target_time:
            return local_stored_energy.get_value(target_time)

    # Fallback to initial level calculations
    if isinstance(equipment, HydroPO):
        return equipment.initial_level.get_value(parameters.start_date - parameters.timestep)
    else:
        max_energy = equipment.maximum_energy.get_value(parameters.start_date - parameters.timestep)
        return equipment.storage_initial_level * max_energy


def _calculate_new_energy_value(
    equipment: StoragePO | HydroPO,
    time: DateTime,
    previous_energy: float,
    new_power: AbstractTimeseries,
    parameters: PortfolioOptimisationParameters,
) -> float:
    """
    Calculate new energy value based on power and efficiency.

    :param equipment: Storage or hydro equipment instance
    :type equipment: StoragePO | HydroPO
    :param time: Current time
    :type time: DateTime
    :param previous_energy: Previous energy level
    :param new_power: New power timeseries
    :type new_power: AbstractTimeseries
    :param parameters: Optimization parameters
    :type parameters: PortfolioOptimisationParameters
    :return: New energy value
    :rtype: float
    """
    power_value = new_power.get_value(time)
    time_factor_hours = parameters.timestep.in_hours()

    if isinstance(equipment, StoragePO):
        if equipment.storage_type == StorageType.ELECTRIC_VEHICLE:
            # Handle capacity scaling for electric vehicles
            capacity_ratio = equipment.maximum_energy.get_value(time) / equipment.maximum_energy.get_value(
                time - parameters.timestep
            )
            previous_energy *= capacity_ratio

        if power_value > 0:  # Discharging
            efficiency = 1 / equipment.discharge_efficiency
        else:  # Charging
            efficiency = equipment.charge_efficiency

        return previous_energy - power_value * time_factor_hours * efficiency

    else:
        return previous_energy - power_value * time_factor_hours


def _apply_energy_bounds(
    energy_value: float,
    bounds: tuple[float, float],
    time: DateTime,
    parameters: PortfolioOptimisationParameters,
) -> tuple[float, float]:
    """
    Apply energy bounds and return corrected value and correction amount.

    :param energy_value: Energy value to check
    :param bounds: Tuple of (min_energy, max_energy)
    :param time: Current time
    :param parameters: Optimization parameters
    :return: Tuple of (corrected_energy, correction)
    :rtype: tuple[float, float]
    """
    min_energy, max_energy = bounds
    timestep_hours = parameters.timestep.total_hours()

    if energy_value > max_energy:
        correction = (max_energy - energy_value) * timestep_hours
        return max_energy, correction
    elif energy_value < min_energy:
        correction = (min_energy - energy_value) * timestep_hours
        return min_energy, correction
    else:
        return energy_value, 0.0


def _apply_power_corrections(
    equipment: HydroPO | StoragePO, new_power: Timeseries, corrections: dict[DateTime, float]
) -> None:
    """
    Apply power corrections based on energy bound violations.

    :param equipment: Equipment instance
    :type equipment: HydroPO | StoragePO
    :param new_power: New power timeseries
    :type new_power: Timeseries
    :param corrections: Dictionary of time -> correction pairs
    :type corrections: dict[DateTime, float]
    :return: None
    :rtype: None
    """
    for time, correction in corrections.items():
        current_power = new_power.get_value(time)

        if isinstance(equipment, StoragePO):
            if current_power > 0:  # Discharging
                corrected_power = current_power - correction * equipment.discharge_efficiency
            else:  # Charging
                corrected_power = current_power - correction / equipment.charge_efficiency
        else:  # Hydraulic
            corrected_power = current_power - correction

        new_power.set_value(time, corrected_power)


def _finalize_power_update(
    equipment: EquipmentPO, new_power: Timeseries, parameters: PortfolioOptimisationParameters
) -> None:
    """
    Finalize power update by adding extra timestep and updating equipment.

    :param equipment: Equipment instance
    :type equipment: EquipmentPO
    :param new_power: New power timeseries
    :type new_power: Timeseries
    :param parameters: Optimization parameters
    :type parameters: PortfolioOptimisationParameters
    :return: None
    :rtype: None
    """
    # Add extra timestep for interpolation
    next_time = parameters.end_date + parameters.timestep
    if equipment.power:
        next_power_value = equipment.power.get_forecast(parameters.execution_date, next_time, next_time).get_value(
            next_time
        )
        new_power.set_value(next_time, next_power_value)

    # Update equipment power
    if parameters.use_forecast:
        if equipment.id_po_for_orders:
            cast(ForecastingMatrix | LazyForecastingMatrix, equipment.id_po_for_orders).add(
                new_power, parameters.execution_date
            )
    else:
        if equipment.power:
            equipment.power.replace(
                parameters.execution_date,
                new_power,
            )
