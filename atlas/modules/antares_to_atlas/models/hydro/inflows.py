"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pathlib import Path

import polars as pl
from antares.craft.model.area import Area
from loguru import logger

from atlas.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.objects.equipment.hydro import Hydro


def add_inflows_from_csv(
    area: Area,
    hydro: Hydro,
    modulation_ts: Timeseries,
    parameters: AntaresToAtlasParameters,
) -> dict:
    """Compute inflows from CSV profiles when ReservoirManagement is False.

    When an Antares node has ReservoirManagement=False, the modulation time series
    represents energy production rather than actual inflows. This function reads
    generic inflow profiles from CSV and matches them with modulation scenarios
    based on total energy.

    :return: Dictionary mapping scenario names to scaled inflow Timeseries.
    """
    logger.info(f"Adding inflows from CSV for area {area.id}")

    if parameters.hydro.water_value_scenarios == "all":
        # TODO: retrieve all available scenarios from area (e.g. area.get_marginal_prices())
        logger.warning(f"'all' water value scenarios not yet supported for area {area.id}")
        return {}

    scenarios: list[str] = parameters.hydro.water_value_scenarios

    if not scenarios:
        logger.warning("Water values are requested but no scenarios are indicated")
        return {}

    csv_path = Path(parameters.hydro.path_inflows) / f"{area.id}.csv"
    logger.debug(f"Loading inflows from: {csv_path}")

    inflows_csv_timeseries = _load_inflows_from_csv(csv_path, parameters)

    if len(inflows_csv_timeseries) < len(scenarios):
        logger.warning(
            f"There are {len(scenarios)} water value scenarios but only "
            f"{len(inflows_csv_timeseries)} inflow profiles for node {area.id}. "
            "Results may be invalid."
        )

    inflows_dictionary = _match_inflows_to_scenarios(
        area=area,
        scenarios=scenarios,
        inflows_csv_timeseries=inflows_csv_timeseries,
        modulation_ts=modulation_ts,
        parameters=parameters,
    )

    if scenarios and scenarios[0] in inflows_dictionary:
        hydro.inflows = inflows_dictionary[scenarios[0]]

    return inflows_dictionary


def _load_inflows_from_csv(csv_path: Path, parameters: AntaresToAtlasParameters) -> dict[int, Timeseries]:
    """Load inflow profiles from CSV (no header, `;`-separated, rows=timesteps, columns=scenarios, values in GWh).

    :return: Dict mapping column index to Timeseries (values converted to MWh).
    """
    df = pl.read_csv(csv_path, separator=";", has_header=False)
    frequency = f"{parameters.hydro.inflows_timestep}h"
    return {
        i: Timeseries.from_values(
            start_date=parameters.start_date,
            frequency=frequency,
            values=(df[:, i] * 1000).to_list(),  # GWh → MWh
        )
        for i in range(df.width)
    }


def _match_inflows_to_scenarios(
    area: Area,
    scenarios: list[str],
    inflows_csv_timeseries: dict[int, Timeseries],
    modulation_ts: Timeseries,
    parameters: AntaresToAtlasParameters,
) -> dict[str, Timeseries]:
    """Match inflow profiles to water value scenarios by closest total energy.

    For each scenario, picks the unused inflow profile whose total energy is closest
    to the modulation sum, then scales it to match exactly.
    """
    inflows_dictionary: dict[str, Timeseries] = {}
    used_indices: set[int] = set()
    # Weekly → daily conversion when inflows are aggregated per week
    conversion = 1.0 / 7.0 if parameters.hydro.inflows_timestep == 168 else 1.0

    for scenario in scenarios:
        # TODO: local_hydro_sc = area.hydro.HydroSelectedScenario[int(scenario) - 1]
        # local_modulation_sum = modulation_ts.get_by_name(str(local_hydro_sc)).sum()
        local_modulation_sum = 0.0  # TODO: replace once HydroSelectedScenario is available

        available = {i: ts for i, ts in inflows_csv_timeseries.items() if i not in used_indices}
        closest = min(available, key=lambda i: abs(available[i].sum() - local_modulation_sum))
        used_indices.add(closest)

        inflow_ts = inflows_csv_timeseries[closest]
        inflow_sum = inflow_ts.sum()
        if inflow_sum != 0:
            scale = local_modulation_sum / inflow_sum
            inflow_ts = (inflow_ts * (conversion * scale)).round()

        inflows_dictionary[scenario] = inflow_ts
        logger.debug(f"Matched scenario {scenario} with inflow profile {closest}")

    return inflows_dictionary
