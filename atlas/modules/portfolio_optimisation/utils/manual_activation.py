"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import cast

from pendulum import DateTime

from atlas.enums import MarketType, StorageType, ThermalStrategy
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.modules.portfolio_optimisation.input_objects import EquipmentPO
from atlas.modules.portfolio_optimisation.input_objects.hydro import HydroPO
from atlas.modules.portfolio_optimisation.input_objects.load import LoadPO
from atlas.modules.portfolio_optimisation.input_objects.other_non_dispatchable import OtherNonDispatchablePO
from atlas.modules.portfolio_optimisation.input_objects.solar import SolarPO
from atlas.modules.portfolio_optimisation.input_objects.storage import StoragePO
from atlas.modules.portfolio_optimisation.input_objects.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.input_objects.wind import WindPO
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.objects.equipment.equipment import Equipment


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

    Supported values: 'thermal', 'storage', 'wind', 'solar', 'hydro', 'load', 'other_non_dispatchable', 'all'.

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
    if equipment.da_cleared_quantity is not None:
        da_power = equipment.da_cleared_quantity.filter(parameters.target_times, inplace=False)
        if isinstance(da_power, LazyTimeseries):
            da_power = da_power.collect()
    else:
        da_power = Timeseries.from_index(
            parameters.temporal.start_date,
            parameters.temporal.timestep,
            parameters.temporal.end_date - parameters.temporal.timestep,
            default_value=0,
        )

    if parameters.market == MarketType.dayahead:
        return cast(Timeseries, da_power)

    elif parameters.market == MarketType.intraday:
        if equipment.total_id_cleared_quantity is not None:
            id_power = equipment.total_id_cleared_quantity.filter(parameters.target_times, inplace=False)
            if isinstance(id_power, LazyTimeseries):
                id_power = id_power.collect()
        else:
            id_power = Timeseries.from_index(
                parameters.temporal.start_date,
                parameters.temporal.timestep,
                parameters.temporal.end_date - parameters.temporal.timestep,
                default_value=0,
            )
        result = cast(Timeseries, da_power) + cast(Timeseries, id_power)
        return result

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
        if equipment.da_cleared_quantity is not None:
            da_power = equipment.da_cleared_quantity.filter(parameters.target_times, inplace=False)
        else:
            da_power = Timeseries.from_index(
                parameters.temporal.start_date,
                parameters.temporal.timestep,
                parameters.temporal.end_date,
                default_value=0,
            )
        return da_power

    elif parameters.market == MarketType.intraday:
        if equipment.id_cleared_quantity is not None:
            id_power = equipment.id_cleared_quantity.get_forecast(
                parameters.temporal.execution_date, parameters.temporal.start_date, parameters.temporal.end_date
            ).filter(parameters.target_times, inplace=False)
            return id_power
        else:
            return Timeseries.from_index(
                parameters.temporal.start_date,
                parameters.temporal.timestep,
                parameters.temporal.end_date,
                default_value=0,
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
    :param new_power: New power timeseries (modified in place)
    :type new_power: Timeseries
    :param parameters: Optimization parameters
    :type parameters: PortfolioOptimisationParameters
    """
    max_power_forecast: Timeseries | None = None
    if isinstance(equipment, LoadPO | WindPO | SolarPO | OtherNonDispatchablePO):
        max_power_forecast = equipment.maximum_power_forecast.get_forecast(
            parameters.temporal.execution_date, parameters.temporal.start_date, parameters.temporal.end_date
        )

    max_power = _build_max_power_bound(equipment, new_power, max_power_forecast)
    new_power.clip(upper_bound=max_power)

    if isinstance(equipment, ThermalPO | HydroPO | WindPO | SolarPO):
        new_power.clip(lower_bound=0.0)

    if isinstance(equipment, OtherNonDispatchablePO):
        new_power.clip(lower_bound=max_power)
    elif not isinstance(equipment, ThermalPO):
        min_power = _build_min_power_bound(equipment, new_power, max_power_forecast)
        new_power.clip(lower_bound=min_power)


def _build_max_power_bound(
    equipment: EquipmentPO, new_power: Timeseries, max_power_forecast: AbstractTimeseries | None
) -> Timeseries:
    """Per-row maximum-power bound aligned on `new_power`'s time index."""
    if isinstance(equipment, LoadPO):
        return _zero_bound(new_power)
    if isinstance(equipment, WindPO | SolarPO | OtherNonDispatchablePO):
        if max_power_forecast is None:
            return _zero_bound(new_power)
        return cast(Timeseries, max_power_forecast.reindex(new_power, default=0.0, inplace=False))
    if equipment.maximum_power:
        return cast(Timeseries, equipment.maximum_power.reindex(new_power, default=0.0, inplace=False))
    return _zero_bound(new_power)


def _build_min_power_bound(
    equipment: EquipmentPO, new_power: Timeseries, max_power_forecast: AbstractTimeseries | None
) -> Timeseries:
    """Per-row minimum-power bound aligned on `new_power`'s time index.

    Note: the OtherNonDispatchablePO branch (min equals the per-row max) is handled
    directly in :func:`_apply_power_constraints` and not produced here.
    """
    if isinstance(equipment, LoadPO):
        if max_power_forecast is None:
            return _zero_bound(new_power)
        return cast(Timeseries, max_power_forecast.reindex(new_power, default=0.0, inplace=False))
    if isinstance(equipment, WindPO | SolarPO):
        if max_power_forecast is None:
            return _zero_bound(new_power)
        forecast = max_power_forecast.reindex(new_power, default=0.0, inplace=False)
        curtailment = equipment.maximum_curtailment_ratio.reindex(new_power, default=0.0, inplace=False)
        return cast(Timeseries, forecast - forecast * curtailment)
    if isinstance(equipment, StoragePO | HydroPO):
        return cast(Timeseries, equipment.minimum_power.reindex(new_power, default=0.0, inplace=False))
    return _zero_bound(new_power)


def _zero_bound(reference: Timeseries) -> Timeseries:
    """Build a zero-valued Timeseries aligned on `reference`'s time index."""
    return Timeseries.from_timeseries(reference, default_value=0.0)


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
        parameters.temporal.start_date,
        parameters.temporal.timestep,
        parameters.temporal.end_date + parameters.temporal.timestep,
        default_value=0,
    )

    initial_stored_energy = _get_initial_stored_energy(equipment, parameters)
    out_of_bounds_corrections = {}

    for index, time in enumerate(parameters.target_times):
        previous_energy = (
            initial_stored_energy if index == 0 else new_stored_energy.get_value(time - parameters.temporal.timestep)
        )

        new_energy_value = _calculate_new_energy_value(equipment, time, previous_energy, new_power, parameters)

        energy_bounds = _get_energy_bounds(equipment, time)
        corrected_energy, correction = _apply_energy_bounds(new_energy_value, energy_bounds, parameters)

        new_stored_energy.set_value(time, corrected_energy)

        if correction != 0:
            out_of_bounds_corrections[time] = correction

    # Apply power corrections based on energy bound violations
    _apply_power_corrections(equipment, new_power, out_of_bounds_corrections)

    # Add extra timestep for interpolation
    new_stored_energy.set_value(
        parameters.temporal.end_date + parameters.temporal.timestep,
        new_stored_energy.get_value(parameters.temporal.end_date),
    )

    if not parameters.use_forecast and equipment.stored_energy:
        stored_energy_matrix = equipment.stored_energy
        if parameters.temporal.execution_date in stored_energy_matrix:
            stored_energy_matrix.delete(parameters.temporal.execution_date)
        stored_energy_matrix.add(new_stored_energy, parameters.temporal.execution_date)


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
            parameters.temporal.execution_date,
            parameters.temporal.start_date - parameters.temporal.timestep,
            parameters.temporal.start_date,
        )

        target_time = parameters.temporal.start_date - parameters.temporal.timestep
        if local_stored_energy.first_date() <= target_time:
            return local_stored_energy.get_value(target_time)

    # Fallback to initial level calculations
    if isinstance(equipment, HydroPO):
        return equipment.initial_level.get_value(parameters.temporal.start_date - parameters.temporal.timestep)
    else:
        max_energy = equipment.maximum_energy.get_value(parameters.temporal.start_date - parameters.temporal.timestep)
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
    time_factor_hours = parameters.temporal.timestep.total_hours()

    if isinstance(equipment, StoragePO):
        if equipment.storage_type == StorageType.ELECTRIC_VEHICLE:
            # Handle capacity scaling for electric vehicles
            capacity_ratio = equipment.maximum_energy.get_value(time) / equipment.maximum_energy.get_value(
                time - parameters.temporal.timestep
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
    timestep_hours = parameters.temporal.timestep.total_hours()

    if energy_value > max_energy:
        correction = (max_energy - energy_value) / timestep_hours
        return max_energy, correction
    elif energy_value < min_energy:
        correction = (min_energy - energy_value) / timestep_hours
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
    # Extend new_power to end_date for interpolation
    end_date = parameters.temporal.end_date
    if equipment.power:
        next_power_value = equipment.power.get_forecast(
            parameters.temporal.execution_date, end_date, end_date
        ).get_value(end_date)
    else:
        next_power_value = 0.0
    new_power = Timeseries.from_values(
        start_date=parameters.temporal.start_date,
        frequency=parameters.temporal.timestep,
        values=list(new_power.values) + [next_power_value],
    )

    # Update equipment power
    if parameters.use_forecast:
        if not equipment.id_po_for_orders:
            equipment.id_po_for_orders = ForecastingMatrix()
        equipment.id_po_for_orders.add(new_power, parameters.temporal.execution_date)
    else:
        if equipment.power:
            if parameters.temporal.execution_date in equipment.power:
                equipment.power.replace(parameters.temporal.execution_date, new_power)
            else:
                equipment.power.add(new_power, parameters.temporal.execution_date)
        else:
            equipment.power = ForecastingMatrix().add(new_power, parameters.temporal.execution_date)
