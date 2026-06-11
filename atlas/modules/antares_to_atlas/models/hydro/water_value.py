"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import numpy as np
from antares.craft import Frequency, MCIndAreasDataType
from antares.craft.model.area import Area
from antares.craft.model.output import Output
from antares.craft.model.study import Study
from loguru import logger
from pendulum import duration

from atlas.core.io_utils.atlas_dataset import AtlasDataset
from atlas.core.math.matrix import ScenarioMatrix
from atlas.core.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.models.hydro.inflows import build_inflows_for_area
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.objects.equipment.hydro import Hydro
from atlas.timing import generate_datetimes


def compute_water_values(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Compute water values for all hydraulic equipment using dynamic programming (Bellman).

    Autonomous: builds its own per-scenario inflows from the study for each area.

    :param study: Antares study
    :param parameters: Conversion parameters
    :param atlas_dataset: Atlas dataset with hydraulic equipment
    :return: Updated atlas_dataset with water values computed
    """
    logger.info("Computing water values for hydraulic equipment")

    areas = study.get_areas()
    study_output = study.get_output(parameters.output_name)

    for hydro in atlas_dataset.hydro:
        area_name = hydro.node.name if hydro.node else None
        if not area_name or area_name not in parameters.market_areas:
            continue
        if area_name not in areas:
            continue

        area = areas[area_name]
        if not (
            (parameters.hydro.use_heuristic or area.hydro.properties.reservoir) and parameters.hydro.use_water_value
        ):
            continue

        mapping_mc_ts = study_output.get_hydro_ts_numbers(area.id)
        inflows_dictionary = build_inflows_for_area(area, parameters, mapping_mc_ts)

        if not inflows_dictionary:
            logger.info(f"No inflows for {area_name}, skipping water value computation")
            continue

        logger.info(f"Computing water values for area: {area_name}")
        _compute_node_water_values(
            area=area,
            hydro=hydro,
            parameters=parameters,
            inflows_dictionary=inflows_dictionary,
            study_output=study_output,
        )

    logger.info("Water value computation done")
    return atlas_dataset


def _compute_node_water_values(
    area: Area,
    hydro: Hydro,
    parameters: AntaresToAtlasParameters,
    inflows_dictionary: dict[str, Timeseries],
    study_output: Output,
) -> None:
    """Compute water values for a single hydraulic reservoir.

    Uses Bellman value iteration (dynamic programming) backwards in time to compute
    the marginal value of stored energy at each level and time step.

        WV[L][T] = (BV[T+1][L] - BV[T+1][L-1]) / CapacityStep
    """
    if parameters.hydro.water_value_scenarios == "all":
        scenarios = list(inflows_dictionary.keys())
    else:
        scenarios = parameters.hydro.water_value_scenarios

    # Keep only scenarios that have inflows data
    scenario_inflows: list[tuple[str, Timeseries]] = [
        (sc, inflows_dictionary[sc] / 24) for sc in scenarios if sc in inflows_dictionary
    ]
    if not scenario_inflows:
        logger.warning(f"No scenarios found for water value computation of {area.id}")
        return

    logger.info(f"Water value scenarios for {area.id}: {[sc for sc, _ in scenario_inflows]}")

    n_time_steps = len(
        generate_datetimes(
            start=parameters.start_date,
            end=parameters.start_date + duration(years=1),
            freq=parameters.hydro.water_value_timestep,
        )
    )
    total_time_steps = n_time_steps * parameters.hydro.water_value_nb_years

    if hydro.maximum_power is None or hydro.maximum_energy is None:
        logger.warning(f"Cannot compute water values for {area.id}: missing power or energy timeseries")
        return

    power_average = np.mean(hydro.maximum_power.values)
    capacity = hydro.maximum_energy.first_value()

    if power_average == 0.0 or capacity == 0.0:
        logger.warning(f"Cannot compute water values for {area.id}: zero power or capacity")
        return

    capacity_step = int(power_average / parameters.hydro.storage_subdivision)
    stock_levels = list(range(0, int(capacity), capacity_step))
    logger.info(f"Capacity: {capacity}, step: {capacity_step}, levels: {len(stock_levels)}")

    water_values = _run_bellman_iteration(
        area=area,
        hydro=hydro,
        parameters=parameters,
        scenario_inflows=scenario_inflows,
        stock_levels=stock_levels,
        capacity_step=capacity_step,
        n_time_steps=n_time_steps,
        total_time_steps=total_time_steps,
        study_output=study_output,
    )

    _store_water_values(hydro, water_values, stock_levels, parameters, n_time_steps, len(scenario_inflows))


def _run_bellman_iteration(
    area: Area,
    hydro: Hydro,
    parameters: AntaresToAtlasParameters,
    scenario_inflows: list[tuple[str, Timeseries]],
    stock_levels: list[int],
    capacity_step: int,
    n_time_steps: int,
    total_time_steps: int,
    study_output: Output,
) -> np.ndarray:
    """Run backward Bellman value iteration over all scenarios and time steps.

    Returns wv of shape (n_time_steps, n_levels): sum of water values across all scenarios
    (to be divided by n_scenarios in _store_water_values).

    Assumes hourly timestep: MaxPower (MW) × 1h = MWh, consistent with stock levels in MWh.
    """
    assert hydro.maximum_power is not None
    n_levels = len(stock_levels)
    stock_arr = np.array(stock_levels, dtype=float)
    level_indices = np.arange(n_levels)
    beta = parameters.hydro.beta
    subdiv = parameters.hydro.storage_subdivision
    use_interp = parameters.hydro.use_bellman_interpolation

    # Pre-compute max power at hourly resolution: daily (365) → hourly (8760 or 8784 for leap year)
    max_power_arr = np.repeat(np.array(hydro.maximum_power.values, dtype=float), 24)
    if len(max_power_arr) < n_time_steps:
        max_power_arr = np.pad(max_power_arr, (0, n_time_steps - len(max_power_arr)), mode="edge")

    # Accumulator: wv[t, level_idx] — sum across all scenarios
    wv = np.zeros((n_time_steps, n_levels), dtype=float)

    for scenario, inflows_ts in scenario_inflows:
        logger.debug(f"Running Bellman for scenario {scenario}")

        # Price forecast: hourly from study output, padded to n_time_steps
        price_arr = np.array(
            study_output.get_mc_ind_area(
                int(scenario),
                frequency=Frequency.HOURLY,
                data_type=MCIndAreasDataType.VALUES,
                area=area.id,
            )[(parameters.output.marginal_price_column, "Euro")],
            dtype=float,
        )
        if len(price_arr) < n_time_steps:
            price_arr = np.pad(price_arr, (0, n_time_steps - len(price_arr)), mode="edge")

        # Inflows: daily /24 → expand to hourly, padded to n_time_steps
        inflows_arr = np.repeat(np.array(inflows_ts.values, dtype=float), 24)
        if len(inflows_arr) < n_time_steps:
            inflows_arr = np.pad(inflows_arr, (0, n_time_steps - len(inflows_arr)), mode="edge")

        wv_sc = np.zeros((n_time_steps, n_levels), dtype=float)
        # Rolling buffer: bellman_next holds bellman[t+1] during backward pass
        bellman_next = np.zeros(n_levels, dtype=float)

        for t in range(total_time_steps - 1, -1, -1):
            t_yr = t % n_time_steps
            max_power_t = float(max_power_arr[t_yr])
            price_t = float(price_arr[t_yr])
            inflows_t = float(inflows_arr[t_yr])

            if t == total_time_steps - 1:
                bellman_curr = np.zeros(n_levels, dtype=float)
            else:
                bellman_curr = bellman_next * beta  # discounted future value as baseline

                stock_i = stock_arr + inflows_t  # (n_levels,)

                # j = 0: no discharge — evaluate carrying inflows forward
                g1 = bellman_next * beta + inflows_t * price_t
                n_idx = (stock_i // capacity_step + 1).astype(int)
                n_idx_clipped = np.clip(n_idx, 0, n_levels - 1)
                n_idx_prev = np.maximum(n_idx_clipped - 1, 0)
                denom_j0 = stock_arr[n_idx_clipped] - stock_arr[n_idx_prev]
                safe_denom_j0 = np.where(denom_j0 != 0.0, denom_j0, 1.0)
                interp_g2 = bellman_next[n_idx_clipped] + (
                    (stock_i - stock_arr[n_idx_clipped])
                    / safe_denom_j0
                    * (bellman_next[n_idx_clipped] - bellman_next[n_idx_prev])
                )
                g2 = np.where(
                    (n_idx != level_indices) & (n_idx < n_levels) & (denom_j0 != 0.0),
                    interp_g2,
                    0.0,
                )
                g_j0 = np.maximum(g1, g2)
                bellman_curr = np.where((g_j0 > bellman_curr) & (level_indices > 0), g_j0, bellman_curr)

                # j > 0: partial to full discharge at each subdivision step
                for j in range(1, subdiv + 1):
                    stock_j = stock_arr - j * max_power_t / subdiv + inflows_t
                    # np.searchsorted replaces the per-level while-loop bracket search
                    m = np.searchsorted(stock_arr, stock_j, side="right") - 1
                    m = np.clip(m, 0, n_levels - 2)
                    m1 = m + 1
                    valid = stock_j > 0.0

                    if use_interp:
                        denom_j = stock_arr[m1] - stock_arr[m]
                        safe_denom_j = np.where(denom_j != 0.0, denom_j, 1.0)
                        sv = beta * (
                            (bellman_next[m] - bellman_next[m1]) * (stock_arr[m1] - stock_j) / safe_denom_j
                            + bellman_next[m1]
                        )
                        gain_lv1 = (stock_i - stock_j) * (-5000.0)
                        gain_other = (stock_i - stock_j) * price_t
                    else:
                        sv = beta * bellman_next[m]
                        gain_lv1 = (stock_i - stock_arr[m]) * (-5000.0)
                        gain_other = (stock_i - stock_arr[m]) * price_t

                    g_lv1 = np.where(valid & (level_indices == 1), gain_lv1 + sv, -np.inf)
                    g_other = np.where(valid & (level_indices > 1), gain_other + sv, -np.inf)
                    g_j = np.maximum(g_lv1, g_other)
                    bellman_curr = np.where((g_j > bellman_curr) & (level_indices > 0), g_j, bellman_curr)

            # Water value for t uses bellman_next (= bellman[t+1]) before rolling forward
            if t < n_time_steps and capacity_step > 0:
                wv_sc[t, 1:] = (bellman_next[1:] - bellman_next[:-1]) / capacity_step

            bellman_next = bellman_curr

        wv += wv_sc

    return wv


def _store_water_values(
    hydro: Hydro,
    water_values: np.ndarray,
    stock_levels: list[int],
    parameters: AntaresToAtlasParameters,
    n_time_steps: int,
    n_scenarios: int,
) -> None:
    """Store computed water values as hydro.storage_marginal_value (ScenarioMatrix).

    Each column of the matrix corresponds to a stock level (in MWh).
    Water values are averaged across scenarios and capped at max_water_value.
    """
    if water_values.size == 0:
        return

    levels_to_store = _select_storage_levels(stock_levels, parameters)
    scenario_matrix = ScenarioMatrix()
    n_sc = max(n_scenarios, 1)

    for level_idx in levels_to_store:
        avg_wv = np.clip(water_values[:, level_idx] / n_sc, None, parameters.hydro.max_water_value)
        stock_level_value = stock_levels[level_idx] if level_idx < len(stock_levels) else 0
        ts = Timeseries.from_values(
            start_date=parameters.start_date,
            frequency="1h",
            values=avg_wv.tolist(),
        )
        scenario_matrix.add(ts, index=str(int(round(stock_level_value, 0))))

    hydro.storage_marginal_value = scenario_matrix
    logger.debug(f"Stored water values for {len(levels_to_store)} stock levels on {hydro.name}")


def _select_storage_levels(stock_levels: list[int], parameters: AntaresToAtlasParameters) -> list[int]:
    """Select which stock level indices to keep based on nb_storage_levels parameter.

    If nb_storage_levels == 0: keep all levels.
    Otherwise: subsample evenly and trim symmetrically to reach the target count.
    """
    if parameters.hydro.nb_storage_levels == 0:
        return list(range(1, len(stock_levels)))

    step = int(len(stock_levels) / parameters.hydro.nb_storage_levels)
    if step == 0:
        return list(range(1, len(stock_levels)))

    candidate_levels = [level for level in range(1, len(stock_levels)) if (level - 1) % step == 0]
    delta = len(candidate_levels) - parameters.hydro.nb_storage_levels

    if delta <= 0:
        return candidate_levels

    trim_start = delta - delta // 2
    trim_end = delta // 2
    return candidate_levels[trim_start : len(candidate_levels) - trim_end if trim_end > 0 else None]
