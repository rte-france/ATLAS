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

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.matrix import ScenarioMatrix
from atlas.math.timeseries import Timeseries
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

        mapping_mc_ts = study_output.get_hydro_ts_numbers(area.name)
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

    _store_water_values(hydro, water_values, stock_levels, parameters, n_time_steps)


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
) -> dict[int, dict[int, float]]:
    """Run backward Bellman value iteration over all scenarios and time steps.

    Returns WV[level_idx][t] as the sum of water values across all scenarios
    (to be divided by n_scenarios in _store_water_values).

    Assumes hourly timestep: MaxPower (MW) × 1h = MWh, consistent with stock levels in MWh.
    """
    # Pre-compute max power at hourly resolution: daily (365) → hourly (8760)
    assert hydro.maximum_power is not None
    max_power_arr = np.repeat(np.array(hydro.maximum_power.values, dtype=float), 24)

    # Initialize WV accumulator
    wv: dict[int, dict[int, float]] = {
        level_idx: dict.fromkeys(range(n_time_steps), 0.0) for level_idx in range(1, len(stock_levels))
    }

    for scenario, inflows_ts in scenario_inflows:
        logger.debug(f"Running Bellman for scenario {scenario}")

        # Price forecast: hourly (8760 values) from study output
        price_arr = np.array(
            study_output.get_mc_ind_area(
                int(scenario),
                frequency=Frequency.HOURLY,
                data_type=MCIndAreasDataType.VALUES,
                area=area.name,
            )[(parameters.output.marginal_price_column, "Euro")],
            dtype=float,
        )

        # Inflows: daily /24 → expand to hourly (8760 values)
        inflows_arr = np.repeat(np.array(inflows_ts.values, dtype=float), 24)

        wv_sc: dict[int, dict[int, float]] = {}
        bellman: dict[int, dict[int, float]] = {}

        for t in range(total_time_steps - 1, -1, -1):
            t_yr = t % n_time_steps
            max_power_t = max_power_arr[t_yr]
            price_t = price_arr[t_yr]
            inflows_t = inflows_arr[t_yr]

            bellman[t] = {}
            if t < n_time_steps:
                wv_sc[t] = {}

            for level_idx in range(len(stock_levels)):
                if t == total_time_steps - 1:
                    bellman[t][level_idx] = 0.0
                else:
                    bellman[t][level_idx] = bellman[t + 1][level_idx] * parameters.hydro.beta
                    m = level_idx

                    if level_idx:
                        g: float | None = None

                        for j in range(parameters.hydro.storage_subdivision + 1):
                            stock_i = stock_levels[level_idx] + inflows_t
                            stock_j = (
                                stock_levels[level_idx]
                                - j * max_power_t / parameters.hydro.storage_subdivision
                                + inflows_t
                            )

                            if j == 0:
                                g1 = bellman[t + 1][level_idx] * parameters.hydro.beta + inflows_t * price_t
                                n_idx = int((stock_levels[level_idx] + inflows_t) // capacity_step + 1)
                                g2 = 0.0
                                if n_idx != level_idx and n_idx < len(stock_levels):
                                    g2 = bellman[t + 1][n_idx] + (
                                        (stock_levels[level_idx] + inflows_t - stock_levels[n_idx])
                                        / (stock_levels[n_idx] - stock_levels[n_idx - 1])
                                        * (bellman[t + 1][n_idx] - bellman[t + 1][n_idx - 1])
                                    )
                                g = max(g1, g2)

                            elif stock_j > 0:
                                while m > 0 and stock_levels[m] > stock_j:
                                    m -= 1

                                if level_idx == 1:
                                    if parameters.hydro.use_bellman_interpolation:
                                        gain = (stock_i - stock_j) * (-5000)
                                        stock_value = parameters.hydro.beta * (
                                            (bellman[t + 1][m] - bellman[t + 1][m + 1])
                                            * (stock_levels[m + 1] - stock_j)
                                            / (stock_levels[m + 1] - stock_levels[m])
                                            + bellman[t + 1][m + 1]
                                        )
                                    else:
                                        gain = (stock_i - stock_levels[m]) * (-5000)
                                        stock_value = parameters.hydro.beta * bellman[t + 1][m]
                                    g = gain + stock_value

                                elif m + 1 <= len(stock_levels) - 1:
                                    if parameters.hydro.use_bellman_interpolation:
                                        gain = (stock_i - stock_j) * price_t
                                        stock_value = parameters.hydro.beta * (
                                            (bellman[t + 1][m] - bellman[t + 1][m + 1])
                                            * (stock_levels[m + 1] - stock_j)
                                            / (stock_levels[m + 1] - stock_levels[m])
                                            + bellman[t + 1][m + 1]
                                        )
                                    else:
                                        gain = (stock_i - stock_levels[m]) * price_t
                                        stock_value = parameters.hydro.beta * bellman[t + 1][m]
                                    g = gain + stock_value

                            if g is not None and g > bellman[t][level_idx]:
                                bellman[t][level_idx] = g

                if level_idx > 0 and t < n_time_steps:
                    wv_sc[t][level_idx] = (
                        (bellman[t + 1][level_idx] - bellman[t + 1][level_idx - 1]) / capacity_step
                        if capacity_step > 0
                        else 0.0
                    )

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
    water_values: dict[int, dict[int, float]],
    stock_levels: list[int],
    parameters: AntaresToAtlasParameters,
    n_time_steps: int,
) -> None:
    """Store computed water values as hydro.storage_marginal_value (ScenarioMatrix).

    Each column of the matrix corresponds to a stock level (in MWh).
    Water values are averaged across scenarios and capped at max_water_value.
    """
    if not water_values:
        return

    n_scenarios = len(parameters.hydro.water_value_scenarios) if parameters.hydro.water_value_scenarios != "all" else 1
    levels_to_store = _select_storage_levels(stock_levels, parameters)
    scenario_matrix = ScenarioMatrix()

    for level_idx in levels_to_store:
        avg_wv = [
            min(water_values.get(level_idx, {}).get(t, 0.0) / max(n_scenarios, 1), parameters.hydro.max_water_value)
            for t in range(n_time_steps)
        ]
        stock_level_value = stock_levels[level_idx] if level_idx < len(stock_levels) else 0
        ts = Timeseries.from_values(
            start_date=parameters.start_date,
            frequency="1h",
            values=avg_wv,
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
