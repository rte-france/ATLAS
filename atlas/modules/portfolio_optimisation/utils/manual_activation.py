from pendulum import DateTime

from atlas.enum import StorageType
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.equipment import Equipment
from atlas.modules.portfolio_optimisation.models.hydro import HydroPO
from atlas.modules.portfolio_optimisation.models.load import LoadPO
from atlas.modules.portfolio_optimisation.models.other_non_dispatchable import OtherNonDispatchablePO
from atlas.modules.portfolio_optimisation.models.solar import SolarPO
from atlas.modules.portfolio_optimisation.models.storage import StoragePO
from atlas.modules.portfolio_optimisation.models.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.models.wind import WindPO
from atlas.modules.portfolio_optimisation.parameters import MarketEnum, PortfolioOptimisationParameters


def is_excluded_technology(parameters: PortfolioOptimisationParameters, equipment: type[Equipment]) -> bool:
    """Check if equipment technology is excluded."""
    return equipment.__class__.__name__ in parameters.excluded_technologies


def is_excluded_thermal_strategy(parameters: PortfolioOptimisationParameters, equipment: ThermalPO) -> bool:
    """Check if thermal equipment strategy is excluded."""
    if isinstance(equipment, ThermalPO):
        return equipment.strategy in parameters.excluded_thermal_strategies
    return False


def is_excluded_market_area(use_forecast: bool, excluded_market_areas: list[str], market_area: str) -> bool:
    """Check if portfolio market area is excluded."""
    return not use_forecast and market_area in excluded_market_areas


def should_manually_activate(equipment: type[Equipment]) -> bool:
    """Determine if equipment should be manually activated."""
    return is_excluded_technology(equipment) or is_excluded_thermal_strategy(equipment)


def set_manual_activation(equipments: list[Equipment], parameters: PortfolioOptimisationParameters):
    """
    Update power matrix and stored energy for equipment portfolio based on market clearing.

    Args:
        equipments: List of equipment objects to process
        parameters: Configuration parameters containing market type, dates, etc.
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


def _calculate_new_power(equipment: type[Equipment], parameters: PortfolioOptimisationParameters) -> Timeseries:
    """Calculate new power based on market type."""
    if parameters.market == MarketEnum.dayahead:
        return equipment.da_cleared_quantity.filter(parameters.target_times)

    elif parameters.market == MarketEnum.intraday:
        da_power = equipment.da_cleared_quantity.filter(parameters.target_times)
        id_power = equipment.total_id_cleared_quantity.filter(parameters.target_times)
        return da_power + id_power


def _calculate_activated_power(equipment: Equipment, parameters: PortfolioOptimisationParameters):
    """Calculate activated power for validation."""
    if parameters.market == MarketEnum.dayahead:
        return equipment.da_cleared_quantity.filter(parameters.target_times)

    elif parameters.market == MarketEnum.intraday:
        return equipment.id_cleared_quantity.get_forecast(
            parameters.execution_date, parameters.start_date, parameters.end_date
        ).filter(parameters.target_times)


def _should_skip_equipment(
    equipment: type[Equipment],
    activated_power: Timeseries,
    parameters: PortfolioOptimisationParameters,
):
    """Check if equipment should be skipped due to zero activation."""
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
    equipment: type[Equipment], new_power: Timeseries, parameters: PortfolioOptimisationParameters
):
    """Apply power constraints based on equipment type."""
    # Preload maximum power forecast for certain equipment types
    max_power_forecast = None
    if isinstance(equipment, LoadPO | WindPO | SolarPO | OtherNonDispatchablePO):
        max_power_forecast = equipment.maximum_power_forecast.get_forecast(
            parameters.execution_date, parameters.start_date, parameters.end_date
        )

    for time in new_power.index:
        power_value = new_power.get_value(time)

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


def _get_max_power(equipment: type[Equipment], time: DateTime, max_power_forecast: Timeseries | LazyTimeseries):
    """Get maximum power limit for equipment at given time."""
    if isinstance(equipment, LoadPO):
        return 0
    elif isinstance(equipment, WindPO | SolarPO | OtherNonDispatchablePO):
        return max_power_forecast.get_value(time)
    else:
        return equipment.maximum_power.get_value(time)


def _get_min_power(equipment, time, max_power_forecast: Timeseries | LazyTimeseries, max_power) -> float:
    """Get minimum power limit for equipment at given time."""
    if isinstance(equipment, LoadPO):
        return max_power_forecast.get_value(time)
    elif isinstance(equipment, WindPO | SolarPO):
        curtailment_ratio = equipment.maximum_curtailment_ratio.get_value(time)
        return max_power_forecast.get_value(time) * (1 - curtailment_ratio)
    elif isinstance(equipment, StoragePO | HydroPO):
        return equipment.minimum_power.get_value(time)
    elif isinstance(equipment, OtherNonDispatchablePO):
        return max_power
    else:
        return 0


def _get_energy_bounds(obj: HydroPO | StoragePO, time: DateTime):
    """Get energy bounds for equipment at given time."""
    max_energy = obj.maximum_energy.get_value(time)

    if isinstance(obj, StoragePO):
        min_energy = max_energy * obj.minimum_state_of_charge.get_value(time)
    else:  # Hydraulic
        min_energy = obj.minimum_energy.get_value(time)

    return min_energy, max_energy


def _update_stored_energy(
    equipment: HydroPO | StoragePO, new_power: Timeseries | LazyTimeseries, parameters: PortfolioOptimisationParameters
):
    """Update stored energy for storage and hydraulic equipment."""

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
    if not parameters.use_forecast:
        stored_energy_matrix = equipment.stored_energy
        if parameters.execution_date in stored_energy_matrix.index:
            equipment.stored_energy.delete(parameters.execution_date)
        equipment.stored_energy.add(parameters.execution_date, new_stored_energy)


def _get_initial_stored_energy(equipment: HydroPO | StoragePO, parameters: PortfolioOptimisationParameters):
    """Get initial stored energy level for equipment."""
    stored_energy_matrix = equipment.stored_energy

    if stored_energy_matrix.index:
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
    previous_energy,
    new_power: Timeseries | LazyTimeseries,
    parameters: PortfolioOptimisationParameters,
):
    """Calculate new energy value based on power and efficiency."""
    power_value = new_power.get_value(time)
    time_factor = parameters.timestep

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

        return previous_energy - power_value * time_factor * efficiency

    else:
        return previous_energy - power_value * time_factor


def _apply_energy_bounds(energy_value, bounds, time, parameters):
    """Apply energy bounds and return corrected value and correction amount."""
    min_energy, max_energy = bounds

    if energy_value > max_energy:
        correction = (max_energy - energy_value) * parameters.timestep
        return max_energy, correction
    elif energy_value < min_energy:
        correction = (min_energy - energy_value) * parameters.timestep
        return min_energy, correction
    else:
        return energy_value, 0


def _apply_power_corrections(equipment: type[Equipment], new_power: Timeseries, corrections):
    """Apply power corrections based on energy bound violations."""
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
    equipment: type[Equipment], new_power: Timeseries, parameters: PortfolioOptimisationParameters
):
    """Finalize power update by adding extra timestep and updating equipment."""
    # Add extra timestep for interpolation
    next_time = parameters.end_date + parameters.timestep
    next_power_value = equipment.power.get_forecast(parameters.execution_date, next_time, next_time).get_value(
        next_time
    )
    new_power.set_value(next_time, next_power_value)

    # Update equipment power
    if parameters.use_forecast:
        equipment.id_po_for_orders.add(new_power, parameters.execution_date)
    else:
        if parameters.execution_date in equipment.power.index:
            equipment.power.delete(parameters.execution_date)
        equipment.power.add(parameters.execution_date, new_power)
