"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pathlib import Path

import pandas as pd
import polars as pl
from antares.craft.model.area import Area
from loguru import logger

from atlas.core.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.objects.equipment.hydro import Hydro


def build_reservoir_inflows(
    area: Area,
    parameters: AntaresToAtlasParameters,
    mapping_mc_ts: dict[int, int],
) -> dict[str, Timeseries]:
    """Build per-scenario inflow timeseries for a reservoir-managed area.

    Used both during hydro unit creation (to set hydro.inflows) and during
    water value computation (to get all scenario inflows for Bellman iteration).

    :return: Dict mapping scenario name to daily inflow Timeseries.
    """
    scenarios: list[str]
    if parameters.hydro.water_value_scenarios == "all":
        scenarios = [str(k) for k in mapping_mc_ts.keys()]
    else:
        scenarios = parameters.hydro.water_value_scenarios

    mod_series = area.hydro.get_mod_series()
    return {
        scenario: Timeseries.from_values(
            parameters.start_date, frequency="1d", values=mod_series[mapping_mc_ts[int(scenario)] - 1].to_list()
        )
        for scenario in scenarios
        if int(scenario) in mapping_mc_ts
    }


def build_inflows_for_area(
    area: Area,
    parameters: AntaresToAtlasParameters,
    mapping_mc_ts: dict[int, int],
) -> dict[str, Timeseries]:
    """Build per-scenario inflow timeseries for an area, handling both reservoir and CSV cases.

    Used by the water value converter to be self-contained (no external inflows_dictionary needed).

    :return: Dict mapping scenario name to daily inflow Timeseries. Empty if inflows cannot be built.
    """
    if area.hydro.properties.reservoir:
        return build_reservoir_inflows(area, parameters, mapping_mc_ts)

    if parameters.hydro.water_value_scenarios == "all":
        scenarios = [str(k) for k in mapping_mc_ts.keys()]
    else:
        scenarios = parameters.hydro.water_value_scenarios

    if not scenarios:
        logger.warning("Water values are requested but no scenarios are indicated")
        return {}

    if parameters.hydro.path_inflows is None:
        logger.warning(f"path_inflows not configured, cannot load inflows from CSV for area {area.id}")
        return {}

    csv_path = parameters.hydro.path_inflows / f"{area.id}.csv"
    inflows_csv = _load_inflows_from_csv(csv_path, parameters)

    if len(inflows_csv) < len(scenarios):
        logger.warning(
            f"There are {len(scenarios)} water value scenarios but only "
            f"{len(inflows_csv)} inflow profiles for node {area.id}. "
            "Results may be invalid."
        )

    return _match_inflows_to_scenarios(
        scenarios=scenarios,
        inflows_csv_timeseries=inflows_csv,
        modulation_df=area.hydro.get_mod_series(),
        mapping_mc_ts=mapping_mc_ts,
        parameters=parameters,
    )


def add_inflows_from_csv(
    area: Area,
    hydro: Hydro,
    modulation_df: pd.DataFrame,
    parameters: AntaresToAtlasParameters,
    mapping_mc_ts: dict[int, int],
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
        scenarios = [str(k) for k in mapping_mc_ts.keys()]
    else:
        scenarios = parameters.hydro.water_value_scenarios

    if not scenarios:
        logger.warning("Water values are requested but no scenarios are indicated")
        return {}

    if parameters.hydro.path_inflows is None:
        logger.warning(f"path_inflows not configured, cannot load inflows from CSV for area {area.id}")
        return {}
    csv_path = parameters.hydro.path_inflows / f"{area.id}.csv"
    logger.debug(f"Loading inflows from: {csv_path}")

    inflows_csv_timeseries = _load_inflows_from_csv(csv_path, parameters)

    if len(inflows_csv_timeseries) < len(scenarios):
        logger.warning(
            f"There are {len(scenarios)} water value scenarios but only "
            f"{len(inflows_csv_timeseries)} inflow profiles for node {area.id}. "
            "Results may be invalid."
        )

    inflows_dictionary = _match_inflows_to_scenarios(
        scenarios=scenarios,
        inflows_csv_timeseries=inflows_csv_timeseries,
        modulation_df=modulation_df,
        mapping_mc_ts=mapping_mc_ts,
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
    return {
        i: Timeseries.from_values(
            start_date=parameters.start_date,
            frequency=parameters.hydro.inflows_timestep,
            values=(df[:, i] * 1000).to_list(),  # GWh → MWh
        )
        for i in range(df.width)
    }


def _match_inflows_to_scenarios(
    scenarios: list[str],
    inflows_csv_timeseries: dict[int, Timeseries],
    modulation_df: pd.DataFrame,
    mapping_mc_ts: dict[int, int],
    parameters: AntaresToAtlasParameters,
) -> dict[str, Timeseries]:
    """Match inflow profiles to water value scenarios by closest total energy.

    For each scenario, picks the unused inflow profile whose total energy is closest
    to the modulation sum, then scales it to match exactly.
    """
    inflows_dictionary: dict[str, Timeseries] = {}
    used_indices: set[int] = set()
    # Weekly → daily conversion: divide by number of days covered by each inflow timestep
    inflows_hours = parameters.hydro.inflows_timestep.in_hours()
    conversion = 24.0 / inflows_hours if inflows_hours > 24 else 1.0

    for scenario in scenarios:
        local_hydro_sc = mapping_mc_ts.get(int(scenario))
        if local_hydro_sc is None:
            logger.warning(f"Scenario {scenario} not found in hydro TS mapping, using 0 as modulation sum")
            local_modulation_sum = 0.0
        else:
            local_modulation_sum = float(modulation_df[local_hydro_sc - 1].sum())

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
