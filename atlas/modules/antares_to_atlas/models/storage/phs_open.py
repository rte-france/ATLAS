# coding: utf-8

import API
import functions
import os


# Function creating a PumpedHydraulicStorage Equipment based on an open loop PHS in the Antares input marker
def creation_phs_open(antares_input_marker, atlas_output_marker, hydro_reservoirs, inflows_dictionary, p):
    # Define a list storing all open_phs equipemnts created
    open_phs_list = []

    # if a link (pump or turb, doesnt matter) exists between an open phs and a node w_hydro_open_node, it creates a phs
    for links in antares_input_marker.Link.GetAllInstances():
        # we are searching for links between an open phs and a node (w_hydro_open_node in reality)
        if links.DownhillNode.Name == "x_open_turb":
            hydro_name = links.UphillNode.Name

            # we split and get node, then we ensure that we have the minuscule, just a detail of presentation in atlas output
            node_name = hydro_name.split("_")[-1].lower()

            if (node_name == "fr") or (node_name not in p.market_areas_list):
                continue

            if (
                hydro_reservoirs[node_name]["OpenLoopCapacity"] == 0.0
                or links.IndirectTransferCapacity.GetTimeSeriesByName("1").Abs().Max() == 0.0
            ):
                continue

            # Load useful informations from the input_marker
            w_hydro_open_node = links.UphillNode
            w_hydro_open_link = antares_input_marker.Link.GetInstanceByName(node_name + "_" + hydro_name)
            binding_constraint = functions.find_binding_constraint_phs(antares_input_marker, links)

            # we create the node phs
            msg = "Creating phs equipment in Node {}".format(node_name)
            API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

            instance_name = "{}_phs_open".format(node_name)
            atlas_output_marker.Equipment.Storage.CreateInstance(instance_name)

            open_phs = atlas_output_marker.Equipment.Storage.GetInstanceByName(instance_name)

            if p.consumption_production_separation:
                portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                    "generator_{}".format(node_name)
                )
            else:
                portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                    "portfolio_{}".format(node_name)
                )

            # general properties of a storage equipment
            open_phs.Node = atlas_output_marker.Network.Node.GetInstanceByName(node_name)
            open_phs.Portfolio = portfolio
            open_phs.StorageType = "PumpedHydraulicStorage"
            if binding_constraint:
                open_phs.DischargeEfficiency = abs(binding_constraint.Weights[1])  # turb
                open_phs.ChargeEfficiency = abs(binding_constraint.Weights[0])  # pump
            else:
                open_phs.DischargeEfficiency = 1  # turb
                open_phs.ChargeEfficiency = 1  # pump
            open_phs.TransitionDuration = 0
            open_phs.SetupDelay = 0

            # MinimumPower is directly given by DirectTransferCapacity of w_hydro_open_link
            open_phs.MinimumPower = -1.0 * w_hydro_open_link.DirectTransferCapacity.GetTimeSeriesByName("1")

            # In ATLAS, the open_phs is divided into two compenents:
            # - A closed phs that will later be merged with the other closed phs of the corresponding node
            # - The open part is integrated into the hydro equipment of the node by increasing its MaximumEnergy, MaximumPower and Inflow

            # Calculate the part corresponding to the closed phs within the open phs, both as a difference and as a ratio

            # link power between the phs turb -> the node w_hydro_open_node
            power_link_phs_w = links.IndirectTransferCapacity.GetTimeSeriesByName("1")

            # link power between w_hydro_open_node -> node
            power_link_w_node = w_hydro_open_link.IndirectTransferCapacity.GetTimeSeriesByName("1")

            # difference added to the hydro power of the node
            hydro_equipment = atlas_output_marker.Equipment.Hydraulic.GetInstanceByName("{}_hydro".format(node_name))
            if not hydro_equipment:
                # If the hydro power does not exists, we create one to append to inflows of the open phs
                hydro_equipment = atlas_output_marker.Equipment.Hydraulic.CreateInstance("{}_hydro".format(node_name))

                # Inflows are empty
                available_scenarios = [
                    ts.Name
                    for ts in antares_input_marker.Node.GetInstanceByName(node_name).CalculatedMarginalPrice.TimeSeries
                ]
                if p.water_value_scenarios == "All":
                    scenarios = available_scenarios
                else:
                    scenarios = p.water_value_scenarios.split(sep=";")
                empty_ts = API.TimeSeries.NewTimeSeries("", API.TimeSeries.Constant, "", power_link_phs_w.Index, 0.0)
                inflows_dictionary[node_name] = {scenario: empty_ts for scenario in scenarios}

                if p.consumption_production_separation:
                    hydro_equipment.Portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                        "generator_{}".format(node_name)
                    )
                else:
                    hydro_equipment.Portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                        "portfolio_{}".format(node_name)
                    )
                hydro_equipment.Node = atlas_output_marker.Network.Node.GetInstanceByName(node_name)
                hydro_equipment.EnergyTargetFrequency = "Daily"
                hydro_equipment.InflowFrequency = "Daily"
                hydro_equipment.MaximumPower = API.TimeSeries.NewTimeSeries(
                    "MaxPower", API.TimeSeries.Constant, "", power_link_w_node.Index, 0.0
                )
                hydro_equipment.MinimumPower = API.TimeSeries.NewTimeSeries(
                    "MinPower", API.TimeSeries.Constant, p.start_date.ToString(), "1Y", 2, 0.0, "MW"
                )

                hydro_equipment.MaximumEnergy = API.TimeSeries.NewTimeSeries(
                    "", API.TimeSeries.Constant, "MWh", power_link_w_node.Index, 0.0
                )
                curve_index = API.DatetimeIndex.NewIndex(p.start_date, p.start_date.AddYears(1), p.inflows_time_step)
                hydro_equipment.Inflows = API.TimeSeries.NewTimeSeries("", API.TimeSeries.Constant, "", curve_index, 0)
                hydro_equipment.MinimumEnergy = API.TimeSeries.NewTimeSeries(
                    "MinimumEnergy", API.TimeSeries.Constant, p.start_date.ToString(), "1Y", 2, 0, "MWh"
                )

                one_year_days_index = API.DatetimeIndex.NewIndex(p.start_date, p.start_date.AddYears(1), "1d")

                hydro_equipment.HasDailyEnergyConstraint = True
                hydro_equipment.MinimumDailyEnergy = API.TimeSeries.NewTimeSeries(
                    "MinimumDailyEnergy", API.TimeSeries.Constant, "MWh", one_year_days_index, 0.0
                )
                hydro_equipment.MaximumDailyEnergy = API.TimeSeries.NewTimeSeries(
                    "MaximumDailyEnergy", API.TimeSeries.Constant, "MWh", one_year_days_index, 0.0
                )

            total_closed_delta = API.TimeSeries.NewTimeSeries(
                "Closed Ratio", API.TimeSeries.Constant, "", power_link_w_node.Index, 0
            )
            total_closed_ratio = API.TimeSeries.NewTimeSeries(
                "Closed Ratio", API.TimeSeries.Constant, "", power_link_w_node.Index, 0
            )

            for time in total_closed_ratio.Index:
                total_closed_delta.SetValue(
                    time, max(0, power_link_w_node.GetValue(time) - power_link_phs_w.GetValue(time))
                )

                if power_link_w_node.GetValue(time) == 0:
                    total_closed_ratio.SetValue(time, 0)
                else:
                    total_closed_ratio.SetValue(
                        time, total_closed_delta.GetValue(time) / power_link_w_node.GetValue(time)
                    )

            # Using these informations, update the following properties in both the open_phs and hydro equipments:
            # - MaximumPower
            # - MaximumEnergy

            # MaximumPower of open_phs
            open_phs.MaximumPower = power_link_phs_w

            # MinimumStateOfCharge of open_phs
            open_phs.MinimumStateOfCharge = API.TimeSeries.NewTimeSeries(
                "MinimumStateOfCharge", API.TimeSeries.Constant, p.start_date.ToString(), "1Y", 2, 0, ""
            )

            # Initial level
            open_phs.StorageInitialLevel = p.phs_initial_level

            # Increase the MaximumPower of the corresponding hydro equipment
            hydro_equipment.MaximumPower += total_closed_delta

            # Increase the MaximumEnergy of the corresponding hydro equipment
            open_loop_capacity = API.TimeSeries.NewTimeSeries(
                "OpenLoopCapacity",
                API.TimeSeries.Constant,
                "MWh",
                total_closed_ratio.Index,
                float(hydro_reservoirs[node_name]["OpenLoopCapacity"]),
            )

            hydro_equipment_additional_energy = API.TimeSeries.NewTimeSeries(
                "OpenLoopCapacity",
                API.TimeSeries.Constant,
                "MWh",
                total_closed_ratio.Index,
                float(hydro_reservoirs[node_name]["OpenLoopCapacity"]),
            )

            hydro_equipment_additional_energy.Multiply(total_closed_ratio)
            hydro_equipment.MaximumEnergy += hydro_equipment_additional_energy.Round()

            # Deduce the MaximumEnergy of the PHS component from the previous part
            open_phs.MaximumEnergy = (open_loop_capacity - hydro_equipment_additional_energy).Round()

            # --- Update inflows contained in inflows_dictionary according to those in w_hydro_open_node
            # An accurate PHS inflow profile is used, taken from the inflow csvs
            available_scenarios = [
                ts.Name
                for ts in antares_input_marker.Node.GetInstanceByName(node_name).CalculatedMarginalPrice.TimeSeries
            ]
            if p.water_value_scenarios == "All":
                scenarios = available_scenarios
            else:
                scenarios = p.water_value_scenarios.split(sep=";")

            curve_index = API.DatetimeIndex.NewIndex(p.start_date, p.start_date.AddYears(1), p.inflows_time_step)

            # First, read the inflow csv corresponding to the current node,
            # and store all values in TimeSeries within a dictionary
            path2 = "{}_phs.csv".format(node_name)
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
                                "PHSInflowTimeseries", API.TimeSeries.Constant, "", curve_index, 0
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
                        str(len(scenarios)), str(len(inflows_csv_timeseries.keys())), node_name
                    ),
                    API.IO.LogTypeWarn,
                )

            # Then, for each scenario used in WV calculation, find the inflow profile that has the closest total energy
            for scenario_index, scenario in enumerate(scenarios):
                local_hydro_sc = w_hydro_open_node.HydroReservoir.HydroSelectedScenario[int(scenario) - 1]

                local_modulation_sum = w_hydro_open_node.HydroReservoir.Modulation.GetTimeSeriesByName(
                    str(local_hydro_sc)
                ).Sum()

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
                        "Specific inflow time step, please look at the corresponding part of the code",
                        API.IO.LogTypeWarn,
                    )

                if inflows_csv_timeseries[closest_inflow_scenario].Sum() == 0:
                    inflow_to_add = inflows_csv_timeseries[closest_inflow_scenario]
                else:
                    inflow_to_add = (
                        inflows_csv_timeseries[closest_inflow_scenario]
                        * conversion_coefficient
                        * (local_modulation_sum / inflows_csv_timeseries[closest_inflow_scenario].Sum())
                    ).Round()

                inflows_dictionary[node_name][scenario] += inflow_to_add

                if scenario_index == 0:
                    hydro_equipment.Inflows += inflow_to_add

            # --- Update MaximumDailyEnergy and MinimumDailyEnergy
            total_flow = -1.0 * w_hydro_open_link.CalculatedTransit.GetTimeSeriesByName(str(p.scenario))
            # QB: we should only account for positive flow and scale it down
            power_hourly = (total_flow.Abs() + total_flow) / 2 * total_closed_ratio
            power_hourly = power_hourly.Round()

            one_year_days_index = API.DatetimeIndex.NewIndex(p.start_date, p.start_date.AddYears(1), "1d")
            power_hourly.ChangeIndex(one_year_days_index)
            one_day_max_energy = API.TimeSeries.NewTimeSeries(
                "OneDayMaxEnergy", API.TimeSeries.Constant, "MWh", one_year_days_index, 0
            )
            one_day_min_energy = API.TimeSeries.NewTimeSeries(
                "OneDayMinEnergy", API.TimeSeries.Constant, "MWh", one_year_days_index, 0
            )

            for time in one_year_days_index:
                one_day_energy = power_hourly.Slice(time, time.AddDays(1).AddHours(-1))
                one_day_max_energy.SetValue(time, one_day_energy.Sum() * p.hydro_max_energy_coeff)
                one_day_min_energy.SetValue(time, one_day_energy.Sum() * p.hydro_min_energy_coeff)

            hydro_equipment.MaximumDailyEnergy += one_day_max_energy
            hydro_equipment.MinimumDailyEnergy += one_day_min_energy

            open_phs_list.append(node_name)

    return open_phs_list, inflows_dictionary


# Function creating a PumpedHydraulicStorage Equipment based on an open loop PHS in the Antares input marker, specific to the FR node
def creation_phs_open_fr(antares_input_marker, atlas_output_marker, hydro_reservoirs, open_phs_list, p):
    link = antares_input_marker.Link.GetInstanceByName("fr_x_open_turb")

    # looking for the node name
    node_name = "fr"

    # we create the node phs
    msg = "Creating phs equipment in Node {}".format(node_name)
    API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

    instance_name = "{}_phs_open".format(node_name)
    atlas_output_marker.Equipment.Storage.CreateInstance(instance_name)

    open_phs = atlas_output_marker.Equipment.Storage.GetInstanceByName(instance_name)

    binding_constraint = functions.find_binding_constraint_phs(antares_input_marker, link)

    if p.consumption_production_separation:
        portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName("generator_{}".format(node_name))
    else:
        portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName("portfolio_{}".format(node_name))

    # general properties of a storage equipment
    open_phs.Node = atlas_output_marker.Network.Node.GetInstanceByName(node_name)
    open_phs.Portfolio = portfolio
    open_phs.StorageType = "PumpedHydraulicStorage"
    open_phs.isV2G = False
    if binding_constraint:
        open_phs.DischargeEfficiency = abs(binding_constraint.Weights[1])
        open_phs.ChargeEfficiency = abs(binding_constraint.Weights[0])
    else:
        open_phs.DischargeEfficiency = 1
        open_phs.ChargeEfficiency = 1
    open_phs.TransitionDuration = 0
    open_phs.SetupDelay = 0

    # specific properties for phs : Power, Pmax and Pmin
    # power
    power_timeseries = -1 * link.CalculatedTransit.GetTimeSeriesByName(str(p.scenario))
    open_phs.Power.AddTimeSeries(p.execution_date, power_timeseries)

    # Pmax
    open_phs.MaximumPower = link.IndirectTransferCapacity.GetTimeSeriesByName("1")

    # Pmin
    open_phs.MinimumPower = -1.0 * link.IndirectTransferCapacity.GetTimeSeriesByName("1")

    # MaximumEnergy and MinimumStateOfCharge
    open_phs.MaximumEnergy = API.TimeSeries.NewTimeSeries(
        "OpenLoopCapacity",
        API.TimeSeries.Constant,
        p.start_date.ToString(),
        "1Y",
        2,
        float(hydro_reservoirs[node_name]["OpenLoopCapacity"]),
        "MWh",
    )

    open_phs.MinimumStateOfCharge = API.TimeSeries.NewTimeSeries(
        "MinimumStateOfCharge", API.TimeSeries.Constant, p.start_date.ToString(), "1Y", 2, 0, ""
    )

    # Initial level
    open_phs.StorageInitialLevel = p.phs_initial_level

    open_phs_list.append(node_name)

    return open_phs_list
