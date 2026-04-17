"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import numpy as np
from antares.craft.model.area import Area
from antares.craft.model.study import Study
from loguru import logger
from pendulum import duration

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.objects.equipment.hydro import Hydro
from atlas.timing import generate_datetimes

# Maximum water value (€/MWh) - water values are capped at this value
_MAX_WATER_VALUE = 26000.0


def compute_water_values(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    inflows_dictionary: dict,
) -> AtlasDataset:
    """Compute water values for all hydraulic equipment using dynamic programming (Bellman).

    Water values represent the marginal value of stored water at each reservoir level
    and time step. They are computed using backward induction over multiple price
    and inflow scenarios.

    The algorithm:
    1. For each area with a hydro unit and inflows, determine water value scenarios
    2. Run Bellman value iteration backwards in time over multiple years
    3. Average water values across scenarios
    4. Store as StorageMarginalValue on the Hydro equipment

    :param study: Antares study
    :param parameters: Conversion parameters
    :param atlas_dataset: Atlas dataset with hydraulic equipment
    :param inflows_dictionary: Dict of {area_name: {scenario: inflow_timeseries}}
    :return: Updated atlas_dataset with water values computed
    """
    logger.info("Computing water values for hydraulic equipment")

    areas = study.get_areas()

    for hydro in atlas_dataset.hydro:
        area_name = hydro.node.name if hydro.node else None
        if not area_name or area_name not in parameters.market_areas:
            continue

        if area_name not in areas:
            continue

        if area_name not in inflows_dictionary:
            logger.info(f"No inflows for {area_name}, skipping water value computation")
            continue

        area = areas[area_name]
        logger.info(f"Computing water values for area: {area_name}")

        _compute_node_water_values(
            area=area,
            hydro=hydro,
            parameters=parameters,
            inflows_dictionary=inflows_dictionary[area_name],
        )

    logger.info("Water value computation done")
    return atlas_dataset


def _compute_node_water_values(
    area: Area,
    hydro: Hydro,
    parameters: AntaresToAtlasParameters,
    inflows_dictionary: dict,
) -> None:
    """Compute water values for a single hydraulic reservoir.

    Uses Bellman value iteration (dynamic programming) backwards in time to compute
    the marginal value of stored energy at each level and time step.

    The water value at level L and time T is approximated as:
        WV[L][T] = (BV[T+1][L] - BV[T+1][L-1]) / CapacityStep

    where BV is the Bellman value function.
    """
    # Determine scenarios for water value computation
    # TODO: Verify how to get available scenarios from area
    # In old code: [int(ts.Name) for ts in antares_node.CalculatedMarginalPrice.TimeSeries]
    available_scenarios: list[str] = []

    if parameters.water_value_scenarios == "all":
        scenarios = available_scenarios
    else:
        scenarios = parameters.water_value_scenarios

    logger.info(f"Water value scenarios for {area.id}: {scenarios}")

    if not scenarios:
        logger.warning(f"No scenarios found for water value computation of {area.id}")
        return

    n_time_steps = generate_datetimes(
        start_date=parameters.start_date,
        end_date=parameters.start_date + duration(years=1),
        frequency=f"{parameters.water_value_timestep}m",
    )
    total_time_steps = n_time_steps * parameters.water_value_nb_years

    # Prepare hourly inflows for each scenario (daily inflows / 24)
    inflows_per_scenario: list[Timeseries] = []
    for scenario in scenarios:
        if scenario not in inflows_dictionary:
            logger.warning(f"No inflows for scenario {scenario} in area {area.id}")
            continue

        inflows_per_scenario.append(inflows_dictionary[scenario] / 24)

    power_average = np.mean(hydro.maximum_power.values)
    capacity = hydro.maximum_energy.first_value()

    if power_average == 0.0 or capacity == 0.0:
        logger.warning(f"Cannot compute water values for {area.id}: zero power or capacity")
        return

    capacity_step = int(power_average / parameters.hydro_storage_subdivision)

    stock_levels = list(range(0, int(capacity), capacity_step))
    logger.info(f"Capacity: {capacity}, step: {capacity_step}, levels: {len(stock_levels)}")

    water_values = _run_bellman_iteration(
        area=area,
        hydro=hydro,
        parameters=parameters,
        scenarios=scenarios,
        inflows_per_scenario=inflows_per_scenario,
        stock_levels=stock_levels,
        capacity_step=capacity_step,
        n_time_steps=n_time_steps,
        total_time_steps=total_time_steps,
    )

    _store_water_values(hydro, water_values, stock_levels, parameters, n_time_steps)


def _run_bellman_iteration(
    area: Area,
    hydro: Hydro,
    parameters: AntaresToAtlasParameters,
    scenarios: list[int],
    inflows_per_scenario: list[Timeseries],
    stock_levels: list[int],
    capacity_step: int,
    n_time_steps: int | None,
    total_time_steps: int | None,
) -> dict:
    """Run backward Bellman value iteration over all scenarios and time steps.

    Returns WV[level][t] as the sum of water values across all scenarios
    (to be divided by n_scenarios afterwards).

    TODO: Full implementation requires:
    - A time index for one year with water_value_time_step resolution
    - Access to CalculatedMarginalPrice time series per scenario
    - Timeseries indexing and value access at specific timestamps
    See old code lines 79-172 for the complete algorithm.
    """
    if n_time_steps is None or total_time_steps is None:
        logger.debug(f"TODO: Implement Bellman iteration for {area.id}")
        return {}

    # Initialize WV accumulator: WV[level][t] = 0
    wv: dict[int, dict[int, float]] = {
        level: dict.fromkeys(range(n_time_steps), 0.0) for level in range(1, len(stock_levels))
    }

    for scenario in scenarios:
        logger.debug(f"Running Bellman for scenario {scenario}")

        # TODO: Get price forecast time series for this scenario
        # In old code: antares_node.CalculatedMarginalPrice.GetTimeSeriesByName(str(scenario))
        # price_forecast_ts = area.get_calculated_marginal_price(str(scenario))

        wv_sc: dict[int, dict[int, float]] = {}
        bellman: dict[int, dict[int, float]] = {}

        # Loop backwards over time
        for t in range(total_time_steps - 1, -1, -1):
            # TODO: Get MaxPower, Price, Inflows at time index t % n_time_steps
            # In old code:
            #   MaxPower_t = hydro.MaximumPower.GetValue(one_year_hours_index[t % n_time_steps])
            #   Price_t = PriceForecast_sc.GetValue(one_year_hours_index[t % n_time_steps])
            #   Inflows_t = inflows[sc].GetValue(one_year_hours_index[t % n_time_steps])

            bellman[t] = {}

            if t < n_time_steps:
                wv_sc[t] = {}

            for level_idx in range(len(stock_levels)):
                # Boundary condition: BV at final time = 0
                if t == total_time_steps - 1:
                    bellman[t][level_idx] = 0.0
                else:
                    # TODO: Implement Bellman recurrence
                    # See old code lines 103-163 for detailed logic
                    # Including:
                    # - Case j=0: compare turbining inflows vs storing them
                    # - Cases j>0: turbine at fractions of max power
                    # - Interpolation between stock levels
                    # - Penalty for going below minimum stock (price = -5000)
                    # - Optional Bellman interpolation (parameters.use_bellman_interpolation)
                    bellman[t][level_idx] = parameters.beta * bellman[t + 1][level_idx]

                # Store water value for first year
                if level_idx > 0 and t < n_time_steps:
                    wv_sc[t][level_idx] = (
                        (bellman[t + 1][level_idx] - bellman[t + 1][level_idx - 1]) / capacity_step
                        if capacity_step > 0
                        else 0.0
                    )

        # Accumulate water values across scenarios
        for level_idx in range(1, len(stock_levels)):
            for t in range(n_time_steps):
                try:
                    wv[level_idx][t] += wv_sc.get(t, {}).get(level_idx, 0.0)
                except Exception as e:
                    logger.error(f"Error accumulating water values at level={level_idx}, t={t}: {e}")
                    raise

    return wv


def _store_water_values(
    hydro: Hydro,
    water_values: dict,
    stock_levels: list[int],
    parameters: AntaresToAtlasParameters,
    n_time_steps: int | None,
) -> None:
    """Store computed water values on the Hydro equipment as fragment data.

    Optionally subsamples levels using nb_storage_levels parameter.
    Water values are capped at _MAX_WATER_VALUE and averaged across scenarios.
    """
    # TODO: In the new Atlas model, water values are stored as fragment_prices/fragment_volumes
    # rather than as a StorageMarginalValue matrix. Verify the correct mapping.
    # In old code: hydro.StorageMarginalValue.AddTimeSeries(str(stock_level), timeseries)

    if not water_values or n_time_steps is None:
        logger.debug(f"TODO: Store water values on {hydro.name}")
        return

    n_scenarios = len(parameters.water_value_scenarios) if parameters.water_value_scenarios != "all" else 1

    # Determine which levels to store (subsample if nb_storage_levels is set)
    levels_to_store = _select_storage_levels(stock_levels, parameters)

    for level_idx in levels_to_store:
        avg_water_values = []
        for t in range(n_time_steps):
            raw_wv = water_values.get(level_idx, {}).get(t, 0.0) / max(n_scenarios, 1)
            avg_water_values.append(min(raw_wv, _MAX_WATER_VALUE))

        # TODO: Create a Timeseries and store on the hydro equipment
        # In old code: hydro.StorageMarginalValue.AddTimeSeries(str(stock_level_value), ts)
        # In new model: may map to fragment_prices or a dedicated field
        stock_level_value = stock_levels[level_idx] if level_idx < len(stock_levels) else 0
        logger.debug(f"TODO: Store water value timeseries for level {stock_level_value} MWh on {hydro.name}")


def _select_storage_levels(stock_levels: list[int], parameters: AntaresToAtlasParameters) -> list[int]:
    """Select which stock levels to keep based on nb_storage_levels parameter.

    If nb_storage_levels == 0: keep all levels.
    Otherwise: subsample evenly and trim symmetrically to reach the target count.
    """

    if parameters.nb_storage_levels == 0:
        return list(range(1, len(stock_levels)))

    step = int(len(stock_levels) / parameters.nb_storage_levels)
    if step == 0:
        return list(range(1, len(stock_levels)))

    candidate_levels = [level for level in range(1, len(stock_levels)) if (level - 1) % step == 0]
    delta = len(candidate_levels) - parameters.nb_storage_levels

    if delta <= 0:
        return candidate_levels

    trim_start = delta - delta // 2
    trim_end = delta // 2
    return candidate_levels[trim_start : len(candidate_levels) - trim_end if trim_end > 0 else None]
