"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.area import Area
from loguru import logger
from pendulum import duration

from atlas.math.timeseries import Timeseries
from atlas.models.equipment.hydro import Hydro
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def add_inflows_from_csv(
    area: Area,
    hydro: Hydro,
    modulation_ts: Timeseries,
    parameters: AntaresToAtlasParameters,
) -> dict:
    """Compute inflows from CSV profiles when ReservoirManagement is False.

    When an Antares node has ReservoirManagement=False, the Modulation time series
    doesn't represent actual inflows but rather energy production. This function
    reads generic inflow profiles from CSV files and matches them with modulation
    scenarios based on total energy.

    The CSV file should contain multiple inflow scenarios (columns) with values
    that will be scaled to match the total energy in the modulation time series.

    :param area: Antares area
    :param hydro: Atlas Hydraulic equipment instance
    :param modulation_ts: Modulation time series from Antares
    :param parameters: Conversion parameters
    :return: Dictionary with scenario names as keys and inflow timeseries as values
    """
    logger.info(f"Adding inflows from CSV for area {area.id}")

    inflows_dictionary = {}

    # Determine which scenarios to process for water values
    # TODO: Verify how to get available scenarios from area
    # In old code: [ts.Name for ts in node.CalculatedMarginalPrice.TimeSeries]
    if parameters.water_value_scenarios == "All":
        # TODO: Get all available scenarios
        scenarios = []  # TODO: Get from area.get_marginal_prices() or similar
        logger.debug("TODO: Get all available scenarios for water values")
    else:
        scenarios = parameters.water_value_scenarios.split(sep=";")

    number_of_scenarios = len(scenarios)

    if number_of_scenarios == 0:
        logger.warning("Water values are requested but no scenarios are indicated")
        return inflows_dictionary

    # Load inflow profiles from CSV
    csv_path = parameters.path_inflows / f"{area.id}.csv"

    if not csv_path.is_file():
        logger.warning(f"Inflow CSV file not found: {csv_path}")
        return inflows_dictionary

    logger.debug(f"Loading inflows from: {csv_path}")

    # TODO: Create curve index for inflows
    # In old code: API.DatetimeIndex.NewIndex(p.start_date, p.start_date.AddYears(1), p.inflows_time_step)
    # This determines the frequency of inflow data (daily, weekly, etc.)

    try:
        inflows_csv_timeseries = _load_inflows_from_csv(csv_path, parameters)

        if len(inflows_csv_timeseries) < len(scenarios):
            logger.warning(
                f"There are {len(scenarios)} water value scenarios, but only "
                f"{len(inflows_csv_timeseries)} inflow scenarios for node {area.id}. "
                "Results may be invalid."
            )

        # Match each water value scenario with the closest inflow profile
        inflows_dictionary = _match_inflows_to_scenarios(
            area=area,
            scenarios=scenarios,
            inflows_csv_timeseries=inflows_csv_timeseries,
            modulation_ts=modulation_ts,
            parameters=parameters,
        )

        # Set the first scenario's inflows on the hydro equipment
        if scenarios and scenarios[0] in inflows_dictionary:
            # TODO: Verify how to set inflows on Hydro model
            # hydro.inflows = inflows_dictionary[scenarios[0]]
            logger.debug(f"Set inflows for first scenario on {hydro.name}")

    except Exception as e:
        logger.error(f"Error processing inflows for area {area.id}: {e}")

    return inflows_dictionary


def _load_inflows_from_csv(csv_path: str, parameters: AntaresToAtlasParameters) -> dict:
    """Load all inflow profiles from CSV file.

    Returns dict with column index as keys and Timeseries as values.
    """
    inflows_csv_timeseries = {}

    # TODO: Create proper datetime index for inflows
    # This should match parameters.inflows_time_step
    # For now, using a placeholder
    start_date = parameters.start_date
    end_date = start_date + duration(years=1)

    try:
        with open(csv_path) as f:
            lines_list = f.readlines()

        # Parse CSV
        for line_index, line in enumerate(lines_list):
            splitted_line = line.split(";")

            if line_index == 0:
                # Initialize timeseries for each column
                for inflow_index in range(len(splitted_line)):
                    # TODO: Create timeseries with proper index
                    # For now, creating placeholder
                    inflows_csv_timeseries[inflow_index] = Timeseries.from_index(
                        start_date=start_date,
                        frequency=parameters.inflows_time_step if hasattr(parameters, "inflows_time_step") else "7d",
                        end_date=end_date,
                        default_value=0.0,
                    )
            else:
                # TODO: Set values at correct timestamps
                # In old code: uses curve_index[line_index] as timestamp
                # and multiplies by 1000 to convert from GWh to MWh
                for inflow_index, inflow_value in enumerate(splitted_line):
                    try:
                        value = float(inflow_value) * 1000  # GWh to MWh
                        # TODO: Set value at correct timestamp
                        # inflows_csv_timeseries[inflow_index][timestamp] = value
                    except ValueError:
                        pass

    except Exception as e:
        logger.error(f"Error loading CSV file {csv_path}: {e}")

    return inflows_csv_timeseries


def _match_inflows_to_scenarios(
    area: Area,
    scenarios: list[str],
    inflows_csv_timeseries: dict,
    modulation_ts: Timeseries,
    parameters: AntaresToAtlasParameters,
) -> dict:
    """Match inflow profiles with water value scenarios based on total energy.

    For each scenario, finds the inflow profile with the closest total energy
    to the modulation time series for that scenario.
    """
    inflows_dictionary = {}
    used_inflow_scenarios = []

    for scenario_index, scenario in enumerate(scenarios):
        # TODO: Get the hydro scenario for this water value scenario
        # In old code: local_hydro_sc = node.HydroReservoir.HydroSelectedScenario[int(scenario) - 1]
        # local_modulation_sum = modulation.GetTimeSeriesByName(str(local_hydro_sc)).Sum()
        local_modulation_sum = 0.0  # TODO: Get from modulation time series

        # Find the inflow scenario with closest total energy
        closest_inflow_scenario = 0
        smallest_energy_gap = abs(local_modulation_sum) if local_modulation_sum > 0 else float("inf")

        for inflow_scenario in inflows_csv_timeseries.keys():
            if inflow_scenario in used_inflow_scenarios:
                continue

            # TODO: Calculate sum of inflow timeseries
            inflow_sum = 0.0  # TODO: inflows_csv_timeseries[inflow_scenario].sum()
            energy_gap = abs(inflow_sum - local_modulation_sum)

            if energy_gap < smallest_energy_gap:
                closest_inflow_scenario = inflow_scenario
                smallest_energy_gap = energy_gap

        used_inflow_scenarios.append(closest_inflow_scenario)

        # Scale the inflow profile to match the modulation energy
        # TODO: Apply time step conversion (weekly to daily if needed)
        conversion_coefficient = 1.0
        if hasattr(parameters, "inflows_time_step") and parameters.inflows_time_step == "7d":
            conversion_coefficient = 1.0 / 7.0
        elif hasattr(parameters, "inflows_time_step") and parameters.inflows_time_step != "1d":
            logger.warning(f"Specific inflow time step: {parameters.inflows_time_step}")

        # TODO: Scale and add inflow to dictionary
        # if inflows_csv_timeseries[closest_inflow_scenario].sum() == 0:
        #     inflow_to_add = inflows_csv_timeseries[closest_inflow_scenario]
        # else:
        #     scale_factor = local_modulation_sum / inflows_csv_timeseries[closest_inflow_scenario].sum()
        #     inflow_to_add = inflows_csv_timeseries[closest_inflow_scenario] * conversion_coefficient * scale_factor
        #     inflow_to_add = inflow_to_add.round()

        # inflows_dictionary[scenario] = inflow_to_add

        logger.debug(f"Matched scenario {scenario} with inflow profile {closest_inflow_scenario}")

    return inflows_dictionary
