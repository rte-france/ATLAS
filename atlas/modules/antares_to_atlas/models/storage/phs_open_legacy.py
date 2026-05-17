import os

import API
import functions


# Function creating a PumpedHydraulicStorage Equipment based on an open loop PHS in the Antares input marker
def creation_phs_open(antares_input_marker, atlas_output_marker, hydro_reservoirs, inflows_dictionary, p):
    # Define a list storing all open_phs equipemnts created
    open_phs_list = []

    for sts in antares_input_marker.STSTechnology.GetAllInstances():
        # If the group of the STS object is PSP_open
        if sts.Group == "PSP_open":
            instance_name = sts.Name
            node_name = sts.Node.Name

            # Looking for the node name, and filter it according to market_areas_list
            if node_name not in p.market_areas_list:
                continue

            # We create the corresponding object in the ATLAS marker
            msg = f"Creating phs equipment {instance_name} in Node {node_name}"
            API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

            atlas_output_marker.Equipment.Storage.CreateInstance(instance_name)

            open_phs = atlas_output_marker.Equipment.Storage.GetInstanceByName(instance_name)

            if p.consumption_production_separation:
                portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(f"generator_{node_name}")
            else:
                portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(f"portfolio_{node_name}")

            # general properties of a storage equipment
            open_phs.Node = atlas_output_marker.Network.Node.GetInstanceByName(node_name)
            open_phs.Portfolio = portfolio
            open_phs.StorageType = "PumpedHydraulicStorage"
            open_phs.DischargeEfficiency = 1
            open_phs.ChargeEfficiency = (
                sts.Efficiency
            )  # In Antares, the efficiency of a STS applies when the STS stores energy
            open_phs.TransitionDuration = 0
            open_phs.SetupDelay = 0

            # Maximum injection power
            try:
                sc = sts.STSSelectedScenario[p.scenario - 1]
                maximum_injection_power_ts = sts.PMaxInjection[sc - 1] * sts.InjectionNominalCapacity
            except:
                maximum_injection_power_ts = API.TimeSeries.NewTimeSeries(
                    "MaximumInjectionPower",
                    API.TimeSeries.Constant,
                    p.start_date.ToString(),
                    "1Y",
                    2,
                    sts.InjectionNominalCapacity,
                    "MWh",
                )

            open_phs.MinimumPower = (
                -maximum_injection_power_ts
            )  # In Antares, "Injection Power" corresponds to the energy from the power system to the storage

            # Maximum withdrawal power
            try:
                sc = sts.STSSelectedScenario[p.scenario - 1]
                maximum_withdrawal_power_ts = sts.PMaxWithdrawal[sc - 1] * sts.WithdrawalNominalCapacity
            except:
                maximum_withdrawal_power_ts = API.TimeSeries.NewTimeSeries(
                    "MaximumWithdrawalPower",
                    API.TimeSeries.Constant,
                    p.start_date.ToString(),
                    "1Y",
                    2,
                    sts.WithdrawalNominalCapacity,
                    "MWh",
                )

            ts_open_phs_power = sts.WithdrawalPower.GetTimeSeriesByName(
                str(sc)
            ) - sts.InjectionPower.GetTimeSeriesByName(str(sc))
            open_phs.Power.AddTimeSeries(p.start_date.AddMinutes(-10), ts_open_phs_power)

            # In ATLAS, the open_phs is divided into two compenents:
            # - A closed phs that will later be merged with the other closed phs of the corresponding node
            # - The open part is integrated into the hydro equipment of the node by increasing its MaximumEnergy, MaximumPower and Inflow

            # difference added to the hydro power of the node
            hydro_equipment = atlas_output_marker.Equipment.Hydraulic.GetInstanceByName(f"{node_name}_hydro")
            if not hydro_equipment:
                # If the hydro power does not exists, we create one to append to inflows of the open phs
                hydro_equipment = atlas_output_marker.Equipment.Hydraulic.CreateInstance(f"{node_name}_hydro")
                print(f"Creating  hydro equipment {hydro_equipment.Name} to put the open PHS in it")

                # Inflows are empty
                available_scenarios = [
                    ts.Name
                    for ts in antares_input_marker.Node.GetInstanceByName(node_name).CalculatedMarginalPrice.TimeSeries
                ]
                if p.water_value_scenarios == "All":
                    scenarios = available_scenarios
                else:
                    scenarios = p.water_value_scenarios.split(sep=";")
                empty_ts = API.TimeSeries.NewTimeSeries(
                    "",
                    API.TimeSeries.Constant,
                    "",
                    maximum_withdrawal_power_ts.Index,
                    0.0,
                )
                inflows_dictionary[node_name] = dict.fromkeys(scenarios, empty_ts)

                if p.consumption_production_separation:
                    hydro_equipment.Portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                        f"generator_{node_name}"
                    )
                else:
                    hydro_equipment.Portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                        f"portfolio_{node_name}"
                    )

                hydro_equipment.Node = atlas_output_marker.Network.Node.GetInstanceByName(node_name)
                hydro_equipment.EnergyTargetFrequency = "Daily"
                hydro_equipment.InflowFrequency = "Daily"
                hydro_equipment.MaximumPower = API.TimeSeries.NewTimeSeries(
                    "MaxPower",
                    API.TimeSeries.Constant,
                    "",
                    maximum_withdrawal_power_ts.Index,
                    0.0,
                )
                hydro_equipment.MinimumPower = API.TimeSeries.NewTimeSeries(
                    "MinPower",
                    API.TimeSeries.Constant,
                    p.start_date.ToString(),
                    "1Y",
                    2,
                    0.0,
                    "MW",
                )

                empty_ts_hydro = API.TimeSeries.NewTimeSeries(
                    "Power",
                    API.TimeSeries.Constant,
                    p.start_date.ToString(),
                    "1Y",
                    2,
                    0.0,
                    "MW",
                )
                hydro_equipment.Power.AddTimeSeries(p.start_date.AddMinutes(-10), empty_ts_hydro)

                hydro_equipment.MaximumEnergy = API.TimeSeries.NewTimeSeries(
                    "",
                    API.TimeSeries.Constant,
                    "MWh",
                    maximum_withdrawal_power_ts.Index,
                    0.0,
                )
                curve_index = API.DatetimeIndex.NewIndex(p.start_date, p.start_date.AddYears(1), p.inflows_time_step)
                hydro_equipment.Inflows = API.TimeSeries.NewTimeSeries("", API.TimeSeries.Constant, "", curve_index, 0)
                hydro_equipment.MinimumEnergy = API.TimeSeries.NewTimeSeries(
                    "MinimumEnergy",
                    API.TimeSeries.Constant,
                    p.start_date.ToString(),
                    "1Y",
                    2,
                    0,
                    "MWh",
                )

                one_year_days_index = API.DatetimeIndex.NewIndex(p.start_date, p.start_date.AddYears(1), "1d")

                hydro_equipment.HasDailyEnergyConstraint = False
                hydro_equipment.MinimumDailyEnergy = API.TimeSeries.NewTimeSeries(
                    "MinimumDailyEnergy",
                    API.TimeSeries.Constant,
                    "MWh",
                    one_year_days_index,
                    0.0,
                )
                hydro_equipment.MaximumDailyEnergy = API.TimeSeries.NewTimeSeries(
                    "MaximumDailyEnergy",
                    API.TimeSeries.Constant,
                    "MWh",
                    one_year_days_index,
                    0.0,
                )

            # With the modelling of short-term storage equipments, the convention taken is that the withdrawal power is divided in two parts:
            # - A part integrated in the closed PHS, equal to the injection power (or to the withdrawal power if injection power > withdrawal power)
            # - A part integrated in the hydro equipment of the node, equal to the difference between the withdrawal power and the injection power
            #   (or to 0 if injection power > withdrawal power)

            total_closed_delta = API.TimeSeries.NewTimeSeries(
                "Closed Delta",
                API.TimeSeries.Constant,
                "",
                maximum_withdrawal_power_ts.Index,
                0,
            )
            total_closed_ratio = API.TimeSeries.NewTimeSeries(
                "Closed Ratio",
                API.TimeSeries.Constant,
                "",
                maximum_withdrawal_power_ts.Index,
                0,
            )

            for time in total_closed_ratio.Index:
                total_closed_delta.SetValue(
                    time,
                    max(
                        0,
                        maximum_withdrawal_power_ts.GetValue(time) - maximum_injection_power_ts.GetValue(time),
                    ),
                )

                if maximum_withdrawal_power_ts.GetValue(time) == 0:
                    total_closed_ratio.SetValue(time, 0)
                else:
                    total_closed_ratio.SetValue(
                        time,
                        total_closed_delta.GetValue(time) / maximum_withdrawal_power_ts.GetValue(time),
                    )

            # Using these informations, update the following properties in both the open_phs and hydro equipments:
            # - MaximumPower
            # - Power
            # - MaximumEnergy

            # MaximumPower of open_phs
            # FC: correction of the min method (does not work for TS)
            # open_phs.MaximumPower = min(maximum_injection_power_ts, maximum_withdrawal_power_ts)
            open_phs.MaximumPower = API.TimeSeries.NewTimeSeries(maximum_injection_power_ts)
            for time in maximum_withdrawal_power_ts.Index:
                open_phs.MaximumPower.SetValue(
                    time,
                    min(
                        open_phs.MaximumPower.GetValue(time),
                        maximum_withdrawal_power_ts.GetValue(time),
                    ),
                )

            # Power of open_phs : for a given timestamp, if the equipment is pumping, the power is allocated to the open PHS;
            # If the equipment is turbining, the power is allocated both to the open PHS and the hydro reservoir based on the closed ratio
            open_power = open_phs.Power.GetTimeseries(p.start_date.AddMinutes(-10))
            negative_phs_power = API.TimeSeries.NewTimeSeries(open_power)
            for time in negative_phs_power.Index:
                if negative_phs_power.GetValue(time) > 0:
                    negative_phs_power.SetValue(time, 0)
            positive_phs_power = API.TimeSeries.NewTimeSeries(open_power)
            for time in positive_phs_power.Index:
                if positive_phs_power.GetValue(time) < 0:
                    positive_phs_power.SetValue(time, 0)
            ts_open_phs_power = negative_phs_power + positive_phs_power * (1 - total_closed_ratio)

            open_phs.Power.DeleteTimeSeries(p.start_date.AddMinutes(-10))
            open_phs.Power.AddTimeSeries(p.start_date.AddMinutes(-10), ts_open_phs_power)

            # Minimum state of charge
            try:
                sc = sts.STSSelectedScenario[p.scenario - 1]
                minimum_soc_ts = sts.LowerRuleCurve[sc - 1]

            except:
                minimum_soc_ts = API.TimeSeries.NewTimeSeries(
                    "MinimumStateOfCharge",
                    API.TimeSeries.Constant,
                    p.start_date.ToString(),
                    "1Y",
                    2,
                    0,
                    "MWh",
                )

            open_phs.MinimumStateOfCharge = minimum_soc_ts

            # Initial level
            open_phs.StorageInitialLevel = sts.InitialLevel

            # Increase the MaximumPower and Power of the corresponding hydro equipment
            hydro_equipment.MaximumPower += total_closed_delta

            if p.start_date.AddMinutes(-10) in hydro_equipment.Power.Index:
                ts_power_hydro = hydro_equipment.Power.GetTimeseries(p.start_date.AddMinutes(-10))
                ts_power_hydro += positive_phs_power * total_closed_ratio
                hydro_equipment.Power.DeleteTimeSeries(p.start_date.AddMinutes(-10))
                hydro_equipment.Power.AddTimeSeries(p.start_date.AddMinutes(-10), ts_power_hydro)

            else:
                ts_power_hydro = positive_phs_power * total_closed_ratio
                hydro_equipment.Power.AddTimeSeries(p.start_date.AddMinutes(-10), ts_power_hydro)

            # Increase the MaximumEnergy of the corresponding hydro equipment
            open_loop_capacity = API.TimeSeries.NewTimeSeries(
                "OpenLoopCapacity",
                API.TimeSeries.Constant,
                "MWh",
                total_closed_ratio.Index,
                sts.ReservoirCapacity,
            )

            hydro_equipment_additional_energy = API.TimeSeries.NewTimeSeries(
                "OpenLoopCapacity",
                API.TimeSeries.Constant,
                "MWh",
                total_closed_ratio.Index,
                sts.ReservoirCapacity,
            )

            hydro_equipment_additional_energy.Multiply(total_closed_ratio)
            hydro_equipment.MaximumEnergy += hydro_equipment_additional_energy.Round()

            # Deduce the MaximumEnergy of the PHS component from the previous part
            open_phs.MaximumEnergy = (open_loop_capacity - hydro_equipment_additional_energy).Round()

            # --- Update inflows contained in inflows_dictionary according to those in the STS equipment
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
            path2 = f"{node_name}_phs.csv"
            csv_path = os.path.join(p.path_inflows, path2)

            if os.path.isfile(csv_path):
                f = open(csv_path)
                lines_list = f.readlines()
                f.close()

                for line_index, line in enumerate(lines_list):
                    splitted_line = line.split(";")

                    # For the first line, initialize a dictionary storing all inflow TimeSeries
                    if line_index == 0:
                        inflows_csv_timeseries = {}

                        for inflow_index, inflow in enumerate(splitted_line):
                            new_inflow_ts = API.TimeSeries.NewTimeSeries(
                                "PHSInflowTimeseries",
                                API.TimeSeries.Constant,
                                "",
                                curve_index,
                                0,
                            )

                            inflows_csv_timeseries[inflow_index] = new_inflow_ts

                    local_date = curve_index[line_index]

                    for inflow_index, inflow in enumerate(splitted_line):
                        inflows_csv_timeseries[inflow_index].SetValue(local_date, float(inflow) * 1000)

            # Raise a warning if there are more wv scenarios than inflow scenarios
            if len(inflows_csv_timeseries.keys()) < len(scenarios):
                API.IO.Trace.Log(
                    f"WARNING: There are {str(len(scenarios))} water values scenarios, and "
                    f" only {str(len(inflows_csv_timeseries.keys()))} inflow scenarios for node {node_name}. "
                    "Results may be invalid. ",
                    API.IO.LogTypeWarn,
                )

            # Then, for each scenario used in WV calculation, find the inflow profile that has the closest total energy
            for scenario_index, scenario in enumerate(scenarios):
                local_hydro_sc = sts.STSSelectedScenario[int(scenario) - 1]

                local_modulation_sum = sts.Inflows.GetTimeSeriesByName(str(local_hydro_sc)).Sum()

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

            # Output power of the whole STS equipment
            power_timeseries = sts.WithdrawalPower[p.scenario - 1] - sts.InjectionPower[p.scenario - 1]

            # We arbitrarily choose that any positive power flow (from the equipment to the grid) is added to the hydro equipment output power
            # using the ratio calculated before
            # QB: we should only account for positive flow and scale it down
            power_to_add_to_hydro = (power_timeseries.Abs() + power_timeseries) / 2 * total_closed_ratio
            power_to_add_to_hydro = power_to_add_to_hydro.Round()

            one_year_days_index = API.DatetimeIndex.NewIndex(p.start_date, p.start_date.AddYears(1), "1d")
            power_to_add_to_hydro.ChangeIndex(one_year_days_index)
            one_day_max_energy = API.TimeSeries.NewTimeSeries(
                "OneDayMaxEnergy",
                API.TimeSeries.Constant,
                "MWh",
                one_year_days_index,
                0,
            )
            one_day_min_energy = API.TimeSeries.NewTimeSeries(
                "OneDayMinEnergy",
                API.TimeSeries.Constant,
                "MWh",
                one_year_days_index,
                0,
            )

            for time in one_year_days_index:
                one_day_energy = power_to_add_to_hydro.Slice(time, time.AddDays(1).AddHours(-1))
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
    msg = f"Creating phs equipment in Node {node_name}"
    API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

    instance_name = f"{node_name}_phs_open"
    atlas_output_marker.Equipment.Storage.CreateInstance(instance_name)

    open_phs = atlas_output_marker.Equipment.Storage.GetInstanceByName(instance_name)

    binding_constraint = functions.find_binding_constraint_phs(antares_input_marker, link)

    if p.consumption_production_separation:
        portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(f"generator_{node_name}")
    else:
        portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(f"portfolio_{node_name}")

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
    open_phs.MaximumPower = link.IndirectTransferCapacity[str(p.scenario)]

    # Pmin
    open_phs.MinimumPower = -1.0 * link.IndirectTransferCapacity[str(p.scenario)]

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
        "MinimumStateOfCharge",
        API.TimeSeries.Constant,
        p.start_date.ToString(),
        "1Y",
        2,
        0,
        "",
    )

    # Initial level
    open_phs.StorageInitialLevel = p.phs_initial_level

    open_phs_list.append(node_name)

    return open_phs_list
