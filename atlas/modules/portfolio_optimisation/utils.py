from collections.abc import Mapping

from pendulum import DateTime

import atlas.config as cfg
from atlas.enum import StorageType
from atlas.math.timeseries import Timeseries
from atlas.models.control_block import ControlBlock
from atlas.models.equipment.equipment import Equipment
from atlas.models.equipment.hydro import Hydro
from atlas.models.equipment.load import Load
from atlas.models.equipment.other_non_dispatchable import OtherNonDispatchable
from atlas.models.equipment.solar import Solar
from atlas.models.equipment.storage import Storage
from atlas.models.equipment.thermal import Thermal
from atlas.models.equipment.wind import Wind
from atlas.models.market.market_area import MarketArea
from atlas.models.portfolio import Portfolio
from atlas.modules.portfolio_optimisation.parameters import (
    MarketEnum,
    PortfolioOptimisationParameters,
)


def estimate_imbalance_prices(
    time: DateTime,
    portfolio: Portfolio,
    market_area: MarketArea,
    control_block: ControlBlock,
    imbalance_price_up: Mapping[DateTime, float],
    large_imbalance_price_up: Mapping[DateTime, float],
    imbalance_price_down: Mapping[DateTime, float],
    large_imbalance_price_down: Mapping[DateTime, float],
    parameters: PortfolioOptimisationParameters,
) -> None:
    """
    Estimate imbalance settlement prices (ISP) at a given time and store them in the provided dictionaries.

    There are four outputs:
      - imbalance_price_up: small upward imbalance
      - large_imbalance_price_up: large upward imbalance
      - imbalance_price_down: small downward imbalance
      - large_imbalance_price_down: large downward imbalance

    Uses either forecast or actual reference price depending on `parameters.use_forecast`,
    and applies either provided imbalance price markers or calculates them using
    French regulation method with penalties and lower bounds.
    """
    # 1. Get reference price
    if parameters.use_forecast:
        if parameters.market == MarketEnum.dayahead:
            ts = market_area.price_forecast_medium.get_forecast(parameters.execution_date, time, time)
            price = ts.get_value(time)
        elif parameters.market == MarketEnum.intraday:
            ts = market_area.id_price_forecast.get_forecast(parameters.execution_date, time, time)
            price = ts.get_value(time)
        else:
            price = 0.0  # safe default; original logic covers only DA/ID in forecast mode
    else:
        if parameters.market == MarketEnum.dayahead:
            price = market_area.da_price.get_value(time)
        elif parameters.market == MarketEnum.intraday:
            price = market_area.id_price.get_forecast(parameters.execution_date, time, time).get_value(time)
        elif parameters.market == MarketEnum.rr_activation:
            price = market_area.rr_activation_price.get_value(time)
        elif parameters.market == MarketEnum.mfrr_activation:
            price = market_area.mfrr_activation_price.get_value(time)
        else:
            price = 0.0  # fallback

    # 2. Upward imbalance prices
    if len(control_block.negative_imbalance_price) > 0:
        base = control_block.negative_imbalance_price.get_value(time)
        imbalance_price_up[time] = base * (1 + parameters.small_imbalance_penalty)
        large_imbalance_price_up[time] = base * (1 + parameters.large_imbalance_penalty)
    else:
        # French rule estimation
        ref = parameters.isp_forecast_lower_bound
        abs_price = abs(price)
        if abs_price < ref:
            if price >= 0:
                imbalance_price_up[time] = (1 + parameters.small_imbalance_penalty) * ref
                large_imbalance_price_up[time] = (1 + parameters.large_imbalance_penalty) * ref
            else:
                imbalance_price_up[time] = (1 - parameters.small_imbalance_penalty) * -ref
                large_imbalance_price_up[time] = (1 - parameters.large_imbalance_penalty) * -ref
        else:
            if price >= 0:
                imbalance_price_up[time] = (1 + parameters.small_imbalance_penalty) * price
                large_imbalance_price_up[time] = (1 + parameters.large_imbalance_penalty) * price
            else:
                imbalance_price_up[time] = (1 - parameters.small_imbalance_penalty) * price
                large_imbalance_price_up[time] = (1 - parameters.large_imbalance_penalty) * price

    # 3. Downward imbalance prices
    if len(control_block.positive_imbalance_price) > 0:
        base = control_block.positive_imbalance_price.get_value(time)
        imbalance_price_down[time] = base * (1 - parameters.small_imbalance_penalty)
        large_imbalance_price_down[time] = base * (1 - parameters.large_imbalance_penalty)
    else:
        ref = parameters.isp_forecast_lower_bound
        abs_price = abs(price)
        if abs_price < ref:
            if price >= 0:
                imbalance_price_down[time] = (1 - parameters.small_imbalance_penalty) * ref
                large_imbalance_price_down[time] = (1 - parameters.large_imbalance_penalty) * ref
            else:
                imbalance_price_down[time] = (1 + parameters.small_imbalance_penalty) * -ref
                large_imbalance_price_down[time] = (1 + parameters.large_imbalance_penalty) * -ref
        else:
            if price >= 0:
                imbalance_price_down[time] = (1 - parameters.small_imbalance_penalty) * price
                large_imbalance_price_down[time] = (1 - parameters.large_imbalance_penalty) * price
            else:
                imbalance_price_down[time] = (1 + parameters.small_imbalance_penalty) * price
                large_imbalance_price_down[time] = (1 + parameters.large_imbalance_penalty) * price


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

        if isinstance(equipment, Hydro | Storage):
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
    if isinstance(equipment, Wind | Solar | Thermal):
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
    if isinstance(equipment, Load | Wind | Solar | OtherNonDispatchable):
        max_power_forecast = equipment.maximum_power_forecast.get_forecast(
            parameters.execution_date, parameters.start_date, parameters.end_date
        )

    for time in new_power.Index:
        power_value = new_power.get_value(time)

        max_power = _get_max_power(equipment, time, max_power_forecast)
        if power_value > max_power:
            new_power.set_value(time, max_power)
            power_value = max_power

        if isinstance(equipment, Thermal | Hydro | Wind | Solar):
            if power_value < 0:
                new_power.set_value(time, 0)
                power_value = 0

        if not isinstance(equipment, Thermal):
            min_power = _get_min_power(equipment, time, max_power_forecast, max_power)
            if power_value < min_power:
                new_power.set_value(time, min_power)


def _get_max_power(equipment: type[Equipment], time: DateTime, max_power_forecast: Timeseries):
    """Get maximum power limit for equipment at given time."""
    if isinstance(equipment, Load):
        return 0
    elif isinstance(equipment, Wind | Solar | OtherNonDispatchable):
        return max_power_forecast.get_value(time)
    else:
        return equipment.maximum_power.get_value(time)


def _get_min_power(equipment, time, max_power_forecast: Timeseries, max_power) -> float:
    """Get minimum power limit for equipment at given time."""
    if isinstance(equipment, Load):
        return max_power_forecast.get_value(time)
    elif isinstance(equipment, Wind | Solar):
        curtailment_ratio = equipment.maximum_curtailment_ratio.get_value(time)
        return max_power_forecast.get_value(time) * (1 - curtailment_ratio)
    elif isinstance(equipment, Storage | Hydro):
        return equipment.MinimumPower.get_value(time)
    elif isinstance(equipment, OtherNonDispatchable):
        return max_power
    else:
        return 0


def _update_stored_energy(
    equipment: Hydro | Storage, new_power: Timeseries, parameters: PortfolioOptimisationParameters
):
    """Update stored energy for storage and hydraulic equipment."""

    new_stored_energy = Timeseries.from_index(
        parameters.start_date, parameters.time_step, parameters.end_date, default_value=0
    )

    initial_stored_energy = _get_initial_stored_energy(equipment, parameters)
    out_of_bounds_corrections = {}

    for index, time in enumerate(parameters.target_times):
        previous_energy = (
            initial_stored_energy if index == 0 else new_stored_energy.get_value(time - parameters.time_step)
        )

        new_energy_value = _calculate_new_energy_value(equipment, time, previous_energy, new_power, parameters)

        energy_bounds = _get_energy_bounds(equipment, time)
        corrected_energy, correction = _apply_energy_bounds(new_energy_value, energy_bounds, time, parameters)

        new_stored_energy.set_value(time, corrected_energy)

        if correction != 0:
            out_of_bounds_corrections[time] = correction
            if parameters.debug:
                bound_type = "high" if correction < 0 else "low"
                cfg.logger.debug(f"Stored energy {bound_type} bound corrected for {equipment.Name} at {time}")

    # Apply power corrections based on energy bound violations
    _apply_power_corrections(equipment, new_power, out_of_bounds_corrections)

    # Add extra timestep for interpolation
    new_stored_energy.set_value(
        parameters.end_date + parameters.time_step,
        new_stored_energy.get_value(parameters.end_date),
    )

    # Update equipment stored energy
    if not parameters.use_forecast:
        stored_energy_matrix = equipment.StoredEnergy
        if parameters.execution_date in stored_energy_matrix.Index:
            equipment.StoredEnergy.DeleteTimeSeries(parameters.execution_date)
        equipment.StoredEnergy.AddTimeSeries(parameters.execution_date, new_stored_energy)


def _get_initial_stored_energy(equipment: Hydro | Storage, parameters: PortfolioOptimisationParameters):
    """Get initial stored energy level for equipment."""
    stored_energy_matrix = equipment.stored_energy

    if stored_energy_matrix.Index:
        local_stored_energy = stored_energy_matrix.get_forecast(
            parameters.execution_date,
            parameters.start_date - parameters.time_step,
            parameters.start_date,
        )

        target_time = parameters.start_date - parameters.time_step
        if local_stored_energy.FirstDate <= target_time:
            return local_stored_energy.get_value(target_time)

    # Fallback to initial level calculations
    if isinstance(equipment, Hydro):
        return equipment.initial_level.get_value(parameters.start_date - parameters.time_step)
    else:
        max_energy = equipment.maximum_energy.get_value(parameters.start_date - parameters.time_step)
        return equipment.storage_initial_level * max_energy


def _calculate_new_energy_value(
    equipment: Storage | Hydro,
    time: DateTime,
    previous_energy,
    new_power: Timeseries,
    parameters: PortfolioOptimisationParameters,
):
    """Calculate new energy value based on power and efficiency."""
    power_value = new_power.get_value(time)
    time_factor = parameters.time_step / 60.0

    if isinstance(equipment, Storage):
        if equipment.storage_type == StorageType.ELECTRIC_VEHICLE:
            # Handle capacity scaling for electric vehicles
            capacity_ratio = equipment.maximum_energy.get_value(time) / equipment.maximum_energy.get_value(
                time - parameters.time_step
            )
            previous_energy *= capacity_ratio

        if power_value > 0:  # Discharging
            efficiency = 1 / equipment.discharge_efficiency
        else:  # Charging
            efficiency = equipment.charge_efficiency

        return previous_energy - power_value * time_factor * efficiency

    else:
        return previous_energy - power_value * time_factor


def _get_energy_bounds(equipment: Hydro | Storage, time: DateTime):
    """Get energy bounds for equipment at given time."""
    max_energy = equipment.maximum_energy.get_value(time)

    if isinstance(equipment, Storage):
        min_energy = max_energy * equipment.minimum_state_of_charge.get_value(time)
    else:  # Hydraulic
        min_energy = equipment.minimum_energy.get_value(time)

    return min_energy, max_energy


def _apply_energy_bounds(energy_value, bounds, time, parameters):
    """Apply energy bounds and return corrected value and correction amount."""
    min_energy, max_energy = bounds

    if energy_value > max_energy:
        correction = (max_energy - energy_value) * parameters.time_step / 60.0
        return max_energy, correction
    elif energy_value < min_energy:
        correction = (min_energy - energy_value) * parameters.time_step / 60.0
        return min_energy, correction
    else:
        return energy_value, 0


def _apply_power_corrections(equipment: type[Equipment], new_power: Timeseries, corrections):
    """Apply power corrections based on energy bound violations."""
    for time, correction in corrections.items():
        current_power = new_power.get_value(time)

        if isinstance(equipment, Storage):
            if current_power > 0:  # Discharging
                corrected_power = current_power - correction * equipment.DischargeEfficiency
            else:  # Charging
                corrected_power = current_power - correction / equipment.ChargeEfficiency
        else:  # Hydraulic
            corrected_power = current_power - correction

        new_power.set_value(time, corrected_power)


def _finalize_power_update(
    equipment: type[Equipment], new_power: Timeseries, parameters: PortfolioOptimisationParameters
):
    """Finalize power update by adding extra timestep and updating equipment."""
    # Add extra timestep for interpolation
    next_time = parameters.end_date + parameters.time_step
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
