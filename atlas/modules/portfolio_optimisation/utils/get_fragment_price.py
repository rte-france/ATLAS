from pendulum import DateTime
from pydantic import BaseModel

from atlas.models.equipment.hydro import Hydro
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.solver.solver_interface import OptimisationModel


def get_fragment_price_and_size(
    obj: Hydro, time: DateTime, parameters: PortfolioOptimisationParameters, model: OptimisationModel
) -> tuple[dict, dict]:
    """
    Formulates hydraulic reservoir offers by calculating fragment prices and volumes.

    Returns:
        tuple: (power_level_fragment, power_level_fragment_sum)
    """
    # Create fragment data structure combining volumes and prices
    fragment_data = {
        category: FragmentData(volume=obj.fragment_volumes[category], price=obj.fragment_prices[category])
        for category in range(len(obj.fragment_volumes))
    }

    # Get current energy level
    energy_level = _get_current_energy_level(obj, parameters)

    # Calculate marginal value weights based on energy level
    marginal_weights = _calculate_marginal_weights(obj, energy_level)

    # Skip processing if time is not in hydraulic operation times
    if time not in parameters.hydraulic_op_times:
        return {}, {}

    # Calculate fragment offers
    power_level_fragment = {}
    power_level_fragment_sum = {}

    capacity = obj.maximum_power[time]

    for category, fragment in fragment_data.items():
        # Calculate volume based on capacity and fragment ratio
        volume = capacity * fragment.volume

        # Calculate price using marginal values and fragment price
        price = _calculate_fragment_price(fragment.price, marginal_weights, time)

        # Create optimization variable
        power_level_fragment[category] = {
            time: model.add_continuous_variable(
                name=f"{obj.name}_power_level_frag_{category}_at_{time}",
                lower_bound=0,
                upper_bound=volume,
            )
        }

        # Store the calculated price
        if not hasattr(obj, "price_fragment"):
            obj.price_fragment = {}
        if category not in obj.price_fragment:
            obj.price_fragment[category] = {}
        obj.price_fragment[category][time] = price

        # Sum all fragment variables for this time
        if category == 0:
            power_level_fragment_sum[time] = power_level_fragment[category][time]
        else:
            power_level_fragment_sum[time] += power_level_fragment[category][time]

    return power_level_fragment, power_level_fragment_sum


def _get_current_energy_level(obj: Hydro, parameters: PortfolioOptimisationParameters) -> float:
    """Get the current energy level from forecast or initial level."""
    energy_forecast = obj.stored_energy.get_forecast(
        parameters.execution_date,
        parameters.start_date - parameters.timestep,
        parameters.start_date - parameters.timestep,
    )

    if len(energy_forecast) > 0:
        return energy_forecast.get_value(parameters.start_date - parameters.timestep)
    else:
        return obj.initial_level.get_value(parameters.start_date - parameters.timestep)


def _calculate_marginal_weights(obj: Hydro, energy_level: float) -> dict:
    """Calculate marginal value weights based on current energy level."""
    storage_indices = obj.storage_marginal_value.index

    # Find bounds around current energy level
    x_min_candidates = [x for x in storage_indices if int(x) <= energy_level]
    x_max_candidates = [x for x in storage_indices if int(x) > energy_level]

    weights = {
        "has_min": bool(x_min_candidates),
        "has_max": bool(x_max_candidates),
        "weight_inf": 0.0,
        "weight_sup": 0.0,
        "level_inf": None,
        "level_sup": None,
    }

    if x_min_candidates:
        xp_min = max(x_min_candidates, key=lambda x: int(x))
        weights["level_inf"] = obj.storage_marginal_value.select(xp_min)

    if x_max_candidates:
        xp_max = min(x_max_candidates, key=lambda x: int(x))
        weights["level_sup"] = obj.storage_marginal_value.select(xp_max)

    # Calculate interpolation weights if we have both bounds
    if weights["has_min"] and weights["has_max"]:
        range_diff = int(xp_max) - int(xp_min)
        weights["weight_inf"] = (int(xp_max) - energy_level) / range_diff
        weights["weight_sup"] = (energy_level - int(xp_min)) / range_diff

    return weights


def _calculate_fragment_price(fragment_price: float, marginal_weights: dict, time: DateTime) -> float:
    """Calculate the final fragment price including marginal values."""
    base_price = fragment_price

    # Apply marginal value adjustments based on available bounds
    if not marginal_weights["has_min"] and marginal_weights["has_max"]:
        # Only upper bound available
        marginal_adjustment = marginal_weights["level_sup"].get_value(time)
    elif marginal_weights["has_min"] and not marginal_weights["has_max"]:
        # Only lower bound available
        marginal_adjustment = marginal_weights["level_inf"].get_value(time)
    elif marginal_weights["has_min"] and marginal_weights["has_max"]:
        # Both bounds available - interpolate
        p_min = marginal_weights["level_inf"].get_value(time)
        p_max = marginal_weights["level_sup"].get_value(time)
        marginal_adjustment = marginal_weights["weight_inf"] * p_min + marginal_weights["weight_sup"] * p_max
    else:
        # No bounds available
        marginal_adjustment = 0.0

    return base_price + marginal_adjustment


class FragmentData(BaseModel):
    """Data structure to hold fragment volume and price information."""

    volume: float
    price: float
