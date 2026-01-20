# coding: utf-8

import API
import os

# Script


def AddInflows(node, hydro, modulation, sc_hydro, p):
    """
    Recompute Inflows if ReservoirManagement of the considered Antares node is False,
    based on a csv input file giving a generic profile for this node and on the total energy
    in a TimeSeries of Modulation.
    This function takes the following inputs:
    - node: Antares node, whose name should match the name of an inflow csv
    - hydro: ATLAS Hydraulic Equipment instance for which Inflow will be filled
    - modulation: Modulation Matrix of the Antares node.
    - sc_hydro: Hydro scenario selected in the Antares study, computed in main.py

    It returns the following output:
    - inflows_dictionary: Dictionary containing inflow timeseries corresponding to each scenario
      used for water values computation
    """

    curve_index = API.DatetimeIndex.NewIndex(p.start_date, p.start_date.AddYears(1), p.inflows_time_step)

    # Initialize the output of the function
    inflows_dictionary = {}

    # If Water Values are generated over multiple scenarios, the same number of inflow timeseries also need to be generated
    # In that case, the same number of inflow profiles are needed for each node, ranked by increasing average energy.
    # For each node, the modulation timeseries available are also ranked by average energy and linked with profiles of similar average energy.
    if p.water_value_scenarios == "All":
        scenarios = [ts.Name for ts in node.CalculatedMarginalPrice.TimeSeries]
    else:
        scenarios = p.water_value_scenarios.split(sep=";")

    number_of_ts_desired = len(scenarios)

    # Case of no valid wv scenario, a warning is returned
    if number_of_ts_desired == 0:
        API.IO.Trace.Log(
            "WARNING: WaterValues are calculated, but there is no watervalues scenario indicated", API.IO.LogTypeWarn
        )

    else:
        # First, read the inflow csv corresponding to the current node,
        # and store all values in TimeSeries within a dictionary
        path2 = "{}.csv".format(node.Name)
        csv_path = os.path.join(p.path_inflows, path2)

        if os.path.isfile(csv_path):
            f = open(csv_path, "r")
            lines_list = f.readlines()
            f.close()

            for line_index, line in enumerate(lines_list):
                splitted_line = line.split(";")

                # For the first line, initialize a dictionary storing all inflow TimeSeries
                if line_index == 0:
                    inflows_csv_timeseries = {}

                    for inflow_index, inflow in enumerate(splitted_line):
                        new_inflow_ts = API.TimeSeries.NewTimeSeries(
                            "InflowTimeseries", API.TimeSeries.Constant, "", curve_index, 0
                        )

                        inflows_csv_timeseries[inflow_index] = new_inflow_ts

                local_date = curve_index[line_index]

                for inflow_index, inflow in enumerate(splitted_line):
                    inflows_csv_timeseries[inflow_index].SetValue(local_date, float(inflow) * 1000)

        # Raise a warning if there are more wv scenarios than inflow scenarios
        if len(inflows_csv_timeseries.keys()) < len(scenarios):
            API.IO.Trace.Log(
                "WARNING: There are {} water values scenarios, and "
                " only {} inflow scenarios for node {}. "
                "Results may be invalid. ".format(
                    str(len(scenarios)), str(len(inflows_csv_timeseries.keys())), node.Name
                ),
                API.IO.LogTypeWarn,
            )

        # Then, for each scenario used in WV calculation, find the inflow profile that has the closest total energy
        for scenario_index, scenario in enumerate(scenarios):
            local_hydro_sc = node.HydroReservoir.HydroSelectedScenario[int(scenario) - 1]

            local_modulation_sum = modulation.GetTimeSeriesByName(str(local_hydro_sc)).Sum()

            closest_inflow_scenario = 0
            smallest_energy_gap = local_modulation_sum
            used_inflow_scenarios = []

            for inflow_scenario in inflows_csv_timeseries.keys():
                if inflow_scenario in used_inflow_scenarios:
                    continue

                if abs(inflows_csv_timeseries[inflow_scenario].Sum() - local_modulation_sum) < smallest_energy_gap:
                    closest_inflow_scenario = inflow_scenario
                    smallest_energy_gap = abs(inflows_csv_timeseries[inflow_scenario].Sum() - local_modulation_sum)

            used_inflow_scenarios.append(closest_inflow_scenario)

            # Inflow values are multiplied by a coefficient to convert them from weekly to daily values
            if p.inflows_time_step == "7d":
                conversion_coefficient = 1.0 / 7.0
            else:
                conversion_coefficient = 1
                API.IO.Trace.Log(
                    "Specific inflow time step, please look at the corresponding part of the code", API.IO.LogTypeWarn
                )

            if inflows_csv_timeseries[closest_inflow_scenario].Sum() == 0:
                inflow_to_add = inflows_csv_timeseries[closest_inflow_scenario]
            else:
                inflow_to_add = (
                    inflows_csv_timeseries[closest_inflow_scenario]
                    * conversion_coefficient
                    * (local_modulation_sum / inflows_csv_timeseries[closest_inflow_scenario].Sum())
                ).Round()

            inflows_dictionary[scenario] = inflow_to_add

            if scenario_index == 0:
                hydro.Inflows = inflow_to_add

    return inflows_dictionary
