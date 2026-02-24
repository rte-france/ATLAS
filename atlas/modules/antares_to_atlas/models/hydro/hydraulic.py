"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import os

from antares.craft.model.area import Area
from antares.craft.model.study import Study
from loguru import logger
from pendulum import duration

from atlas.enums import InflowFrequency
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.hydro import Hydro
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def convert_hydro_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> tuple[AtlasDataset, dict, dict]:
    """Convert Hydraulic reservoir units from Antares to Atlas.

    Hydraulic units are complex equipment with:
    - Reservoir capacity management
    - Inflow profiles
    - Daily energy constraints
    - Water value calculation
    - Fragment prices and volumes

    :return: Tuple of (atlas_dataset, inflows_dictionary, hydro_reservoirs)
    """
    logger.info("Converting Hydraulic units")

    # Load hydraulic reservoirs data from CSV
    hydro_reservoirs = _load_hydro_reservoirs(parameters)
    inflows_dictionary = {}

    areas = study.get_areas()
    hydro_units: list[Hydro] = []

    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]
        logger.debug(f"Processing hydraulic unit for area {area.id}")

        scenario = area.hydro.HydroSelectedScenario[parameters.scenario - 1]  # TODO
        # if sc_hydro in antares_node.HydroReservoir.CalculatedStorageProduction.Index:
        if area.hydro.get_maxpower().abs().max() == 0:
            logger.debug(f"Skipping hydraulic unit for area {area.id} (max power is 0)")
            continue
        if area_name in hydro_reservoirs and hydro_reservoirs[area_name].get("ReservoirCapacity", 0) == 0:
            logger.debug(f"Skipping hydraulic unit for area {area.id} (reservoir capacity is 0)")
            continue

        hydro = _create_hydraulic_equipment(
            area=area,
            parameters=parameters,
            atlas_dataset=atlas_dataset,
            inflows_dictionary=inflows_dictionary,
            scenario=scenario,
        )

        if hydro:
            hydro_units.append(hydro)

    atlas_dataset.hydro = hydro_units

    return atlas_dataset, inflows_dictionary, hydro_reservoirs


def _load_hydro_reservoirs(parameters: AntaresToAtlasParameters) -> dict:
    """Load hydraulic reservoirs data from CSV file.

    Returns dict with node names as keys and reservoir properties as values:
    - ReservoirCapacity
    - OpenLoopCapacity
    - ClosedLoopCapacity
    """
    hydro_reservoirs = {}

    if not os.path.isfile(parameters.hydro_reservoirs_file):
        logger.warning(f"Hydro reservoirs file not found: {parameters.hydro_reservoirs_file}")
        return hydro_reservoirs

    logger.debug(f"Loading hydro reservoirs from: {parameters.hydro_reservoirs_file}")

    try:
        with open(parameters.hydro_reservoirs_file) as f:
            lines_list = f.readlines()

        hydro_index = {}
        headers = []

        for row_index, line in enumerate(lines_list):
            if row_index == 0:
                # Parse headers
                headers = line.split(";")
                for i in range(1, len(headers)):
                    node_name = headers[i].strip()
                    hydro_reservoirs[node_name] = {}
                    hydro_index[node_name] = i
            else:
                # Parse data rows
                splitted_line = line.split(";")
                if len(splitted_line) != len(headers):
                    msg = (
                        f"Invalid number of columns on line {row_index + 1}. "
                        "Please modify the HydraulicReservoirs file."
                    )
                    raise ValueError(msg)

                property_name = splitted_line[0]
                for node_name, column_index in hydro_index.items():
                    hydro_reservoirs[node_name][property_name] = float(splitted_line[column_index])

        logger.debug(f"Loaded hydro reservoirs for {len(hydro_reservoirs)} nodes")

    except Exception as e:
        logger.error(f"Error loading hydro reservoirs file: {e}")
        return {}

    return hydro_reservoirs


def _create_hydraulic_equipment(
    area: Area,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    inflows_dictionary: dict,
    scenario: str,
) -> Hydro | None:
    """Create a Hydraulic equipment for an area."""

    maximum_power_ts = Timeseries(area.hydro.get_maxpower())

    # Create Hydro equipment
    hydro = Hydro(
        name=f"{area.id}_hydro",
        node=atlas_dataset.get("node", area.id),
        portfolio=atlas_dataset.get(
            "portfolio",
            f"generator_{area.id}" if parameters.consumption_production_separation else f"portfolio_{area.id}",
        ),
        maximum_power=maximum_power_ts,
        minimum_power=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=0.0,
        ),
        maximum_energy=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=area.hydro.properties.reservoir_capacity,
        ),
        minimum_energy=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=0.0,
        ),
        energy_target_frequency=InflowFrequency.Daily,
        inflow_frequency=InflowFrequency.Daily,
    )

    if (parameters.use_hydro_heuristic or area.hydro.properties.reservoir) and parameters.use_water_value:
        if area.hydro.properties.reservoir:
            hydro.inflows = area.hydro.get_mod_series()[scenario]
            node_inflows_dictionary = _prepare_inflows_for_water_values(area, parameters)
        else:
            node_inflows_dictionary = _add_inflows_from_csv(area, hydro, area.hydro.get_mod_series(), parameters)
        inflows_dictionary[area.id] = node_inflows_dictionary
    else:
        # Use energy target
        hydro.energy_target = modulation_ts

    # TODO: Set daily energy constraints
    # In old code: uses CalculatedStorageProduction to calculate daily min/max energy
    hydro.has_daily_energy_constraint = True
    minimum_daily_energy = Timeseries.from_index(
        start_date=parameters.start_date,
        frequency="1d",
        end_date=parameters.start_date + duration(years=1),
        default_value=0.0,
    )
    maximum_daily_energy = Timeseries.from_index(
        start_date=parameters.start_date,
        frequency="1d",
        end_date=parameters.start_date + duration(years=1),
        default_value=0.0,
    )

    power_hourly = area.hydro.CalculatedStorageProduction[parameters.scenario]  # TODO
    # power_hourly.ChangeIndex(one_year_hours_index)
    # for time_step in range(len(one_year_days_index) - 1):
    #     one_day_energy = power_hourly.slice(
    #         one_year_days_index[time_step], one_year_days_index[time_step].AddDays(1).AddHours(-1)
    #     )
    #     hydro.MinimumDailyEnergy[one_year_days_index[time_step]] = (
    #         one_day_energy.Sum() * parameters.hydro_min_energy_coeff
    #     )
    #     hydro.MaximumDailyEnergy[one_year_days_index[time_step]] = (
    #         one_day_energy.Sum() * parameters.hydro_max_energy_coeff
    #     )

    hydro.minimum_daily_energy = minimum_daily_energy
    hydro.maximum_daily_energy = maximum_daily_energy

    local_prices = []
    local_volumes = []
    if area.id in parameters.fragment_prices:
        local_prices.append(parameters.fragment_prices[area.id])
    else:
        local_prices.append(parameters.fragment_prices["Generic"])
    hydro.fragment_prices = local_prices

    if area.id in parameters.fragment_volumes:
        local_volumes = parameters.fragment_volumes[area.id]
    else:
        local_volumes = parameters.fragment_volumes["Generic"]
    hydro.fragment_volumes = local_volumes

    logger.debug(f"Created hydraulic equipment for area: {area.id}")
    return hydro


def _prepare_inflows_for_water_values(area: Area, parameters: AntaresToAtlasParameters) -> dict:
    node_inflows_dictionary = {}

    if parameters.water_value_scenarios == "all":
        scenarios = area.CalculatedMarginalPrice.columns  # TODO
    else:
        scenarios = parameters.water_value_scenarios

    for scenario in scenarios:
        local_hydro_sc = area.hydro.HydroSelectedScenario[int(scenario) - 1]  # TODO

        node_inflows_dictionary[scenario] = area.hydro.get_mod_series()[local_hydro_sc]
    return node_inflows_dictionary


def _add_inflows_from_csv(
    area: Area, hydro: Hydro, modulation_ts: Timeseries, parameters: AntaresToAtlasParameters
) -> dict:
    pass

    # curve_index = API.DatetimeIndex.NewIndex(p.start_date, p.start_date.AddYears(1), p.inflows_time_step)

    # # Initialize the output of the function
    # inflows_dictionary = {}

    # # If Water Values are generated over multiple scenarios, the same number of inflow timeseries also need to be generated
    # # In that case, the same number of inflow profiles are needed for each node, ranked by increasing average energy.
    # # For each node, the modulation timeseries available are also ranked by average energy and linked with profiles of similar average energy.
    # if p.water_value_scenarios == "All":
    #     scenarios = [ts.Name for ts in node.CalculatedMarginalPrice.TimeSeries]
    # else:
    #     scenarios = p.water_value_scenarios.split(sep = ";")

    # number_of_ts_desired = len(scenarios)

    # # Case of no valid wv scenario, a warning is returned
    # if number_of_ts_desired == 0:
    #     API.IO.Trace.Log("WARNING: WaterValues are calculated, but there is no watervalues scenario indicated", API.IO.LogTypeWarn)

    # else:
    #     # First, read the inflow csv corresponding to the current node,
    #     # and store all values in TimeSeries within a dictionary
    #     path2 = "{}.csv".format(node.Name)
    #     csv_path = os.path.join(p.path_inflows, path2)

    #     if os.path.isfile(csv_path):

    #         f = open(csv_path,"r")
    #         lines_list = f.readlines()
    #         f.close()

    #         for line_index, line in enumerate(lines_list):

    #             splitted_line = line.split(";")

    #             # For the first line, initialize a dictionary storing all inflow TimeSeries
    #             if line_index == 0:
    #                 inflows_csv_timeseries = {}

    #                 for inflow_index, inflow in enumerate(splitted_line):
    #                     new_inflow_ts = API.TimeSeries.NewTimeSeries('InflowTimeseries', API.TimeSeries.Constant,
    #                                                                  '', curve_index, 0)

    #                     inflows_csv_timeseries[inflow_index] = new_inflow_ts

    #             local_date = curve_index[line_index]

    #             for inflow_index, inflow in enumerate(splitted_line):
    #                 inflows_csv_timeseries[inflow_index].SetValue(local_date, float(inflow) * 1000)

    #     # Raise a warning if there are more wv scenarios than inflow scenarios
    #     if len(inflows_csv_timeseries.keys()) < len(scenarios):
    #         API.IO.Trace.Log("WARNING: There are {} water values scenarios, and "
    #                          " only {} inflow scenarios for node {}. "
    #                          "Results may be invalid. ".format(str(len(scenarios)),
    #                                                            str(len(inflows_csv_timeseries.keys())),
    #                                                            node.Name), API.IO.LogTypeWarn)

    #     # Then, for each scenario used in WV calculation, find the inflow profile that has the closest total energy
    #     for scenario_index, scenario in enumerate(scenarios):

    #         local_hydro_sc = node.HydroReservoir.HydroSelectedScenario[int(scenario) -1]

    #         local_modulation_sum = modulation.GetTimeSeriesByName(str(local_hydro_sc)).Sum()

    #         closest_inflow_scenario = 0
    #         smallest_energy_gap = local_modulation_sum
    #         used_inflow_scenarios = []

    #         for inflow_scenario in inflows_csv_timeseries.keys():
    #             if inflow_scenario in used_inflow_scenarios:
    #                 continue

    #             if abs(inflows_csv_timeseries[inflow_scenario].Sum() - local_modulation_sum) < smallest_energy_gap:
    #                 closest_inflow_scenario = inflow_scenario
    #                 smallest_energy_gap = abs(inflows_csv_timeseries[inflow_scenario].Sum() - local_modulation_sum)

    #         used_inflow_scenarios.append(closest_inflow_scenario)

    #         # Inflow values are multiplied by a coefficient to convert them from weekly to daily values
    #         if p.inflows_time_step == "7d":
    #             conversion_coefficient = 1.0/7.0
    #         else:
    #             conversion_coefficient = 1
    #             API.IO.Trace.Log("Specific inflow time step, please look at the corresponding part of the code", API.IO.LogTypeWarn)

    #         if inflows_csv_timeseries[closest_inflow_scenario].Sum() == 0:
    #             inflow_to_add = inflows_csv_timeseries[closest_inflow_scenario]
    #         else:
    #             inflow_to_add = (inflows_csv_timeseries[closest_inflow_scenario] * conversion_coefficient *
    #                              (local_modulation_sum/inflows_csv_timeseries[closest_inflow_scenario].Sum())).Round()

    #         inflows_dictionary[scenario] = inflow_to_add

    #         if scenario_index == 0:
    #             hydro.Inflows = inflow_to_add

    # return inflows_dictionary
