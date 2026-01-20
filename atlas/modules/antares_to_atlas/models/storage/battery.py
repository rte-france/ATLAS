import API
import functions


# Convert battery technologies of the Antares input marker into ATLAS Storage Equipments
def creation_battery(antares_dataset, atlas_dataset, p):
    ### NORMAL
    for links in antares_dataset.Link.GetAllInstances():
        if links.DownhillNode.Name == "z_batteries":
            # looking for the node name, and filtering nodes that should not be considered

            node_name = links.UphillNode.Name

            if node_name not in p.market_areas_list:
                continue

            ### NORMAL battery
            binding_constraint = antares_dataset.BindingConstraint.GetInstanceByName(f"batteries_{node_name}")
            if not binding_constraint:
                API.IO.Trace.Log(
                    "WARNING for techno {}, binding constraint not found".format(f"batteries_{node_name}"),
                    API.IO.LogTypeWarn,
                )

            # Create the Storage Equipment only if the corresponding BindingConstraint exists
            if binding_constraint:
                power_discharge, maximum_power = get_batteries_inj_data(antares_dataset, node_name, p, False)

                if not maximum_power or maximum_power.Abs().Max() == 0:
                    continue

                # MaximumEnergy (ie: reservoir capacity). Convention : stock_1 is in MWh and not in MW so ok
                try:  # for nodes that do not have thermaltechnology
                    stock_1 = antares_dataset.ThermalTechnology.GetInstanceByName(
                        "z_batteries_batteries_" + functions.node_special_format(node_name) + "_1"
                    ).Disponibility[str(p.scenario)]
                except:  # If Stock 1 is empty, MaximumEnergy is 0 so no battery instance is created
                    continue

                msg = f"Creating battery equipment in Node {node_name}"
                API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

                instance_name = f"{node_name}_battery"
                atlas_dataset.Equipment.Storage.CreateInstance(instance_name)

                battery = atlas_dataset.Equipment.Storage.GetInstanceByName(instance_name)

                battery.MaximumPower = maximum_power
                battery.MaximumEnergy = stock_1

                if p.consumption_production_separation:
                    portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(f"generator_{node_name}")
                else:
                    portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(f"portfolio_{node_name}")

                # general properties of a storage equipment
                battery.Node = atlas_dataset.Network.Node.GetInstanceByName(node_name)
                battery.Portfolio = portfolio
                battery.StorageType = "Battery"
                try:
                    if binding_constraint.Weights[1] != 0:
                        battery.DischargeEfficiency = abs(1 / binding_constraint.Weights[1])
                    else:
                        battery.DischargeEfficiency = 1
                    battery.ChargeEfficiency = abs(binding_constraint.Weights[0])
                except:
                    battery.DischargeEfficiency = 1
                    battery.ChargeEfficiency = 1

                battery.SetupDelay = 0  # look at description !! ??

                # POWER
                # time series of the discharge of the battery
                # signe : + (because give power to electric system)
                if not power_discharge:
                    power_discharge = API.TimeSeries.NewTimeSeries(
                        "Power_discharge", API.TimeSeries.Constant, p.start_date.ToString(), "1Y", 2, 0, "MW"
                    )

                # time series of the charge of the battery
                # signe : - (because loss of energy view from electric system)
                power_charge = -links.CalculatedTransit[str(p.scenario)]

                # power time series
                power_timeseries = power_discharge + power_charge
                battery.Power.AddTimeSeries(p.execution_date, power_timeseries)

                # Pmin
                # =capacity of the link
                minimum_power = -links.DirectTransferCapacity.GetTimeSeriesByName("1")
                battery.MinimumPower = API.TimeSeries.NewTimeSeries(
                    "MinimumPower",
                    API.TimeSeries.Constant,
                    p.start_date.ToString(),
                    "1Y",
                    2,
                    minimum_power[p.start_date],
                    "MW",
                )

                # Minimum State of Charge  = 0 for batteries
                battery.MinimumStateOfCharge = API.TimeSeries.NewTimeSeries(
                    "MinimumStateOfCharge", API.TimeSeries.Constant, p.start_date.ToString(), "1Y", 2, 0, "MW"
                )
                # Initial level
                battery.StorageInitialLevel = p.battery_initial_level

                # TODO: to be refined later, when battery unit counts are indicated in Antares
                battery.UnitCount = 1

            elif p.verbose:
                API.IO.Trace.Log(
                    f"No BindingConstraint found for batteries of node {node_name}, no Storage equipment created",
                    API.IO.LogTypeInfo,
                )

    ### PCOMP battery
    for links in antares_dataset.Link.GetAllInstances():
        if links.DownhillNode.Name == "z_batteries_pcomp":
            node_name = links.UphillNode.Name

            binding_constraint = antares_dataset.BindingConstraint.GetInstanceByName(f"batteries_pcomp_{node_name}")

            # Create the Storage Equipment only if the corresponding BindingConstraint exists
            if binding_constraint:
                power_discharge, maximum_power = get_batteries_inj_data(antares_dataset, node_name, p, True)

                if not maximum_power or maximum_power.Abs().Max() == 0:
                    continue

                # MaximumEnergy (ie: reservoir capacity). Convention : stock_1 is in MWh and not in MW so ok
                try:  # for nodes that do not have thermaltechnology
                    stock_1 = antares_dataset.ThermalTechnology.GetInstanceByName(
                        "z_batteries_pcomp_" + functions.node_special_format(node_name) + "_1"
                    ).Disponibility[str(p.scenario)]
                except:  # If Stock 1 is empty, MaximumEnergy is 0 so no battery instance is created
                    continue

                msg = f"Creating battery_pcomp equipment in Node {node_name}"
                API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

                normal_battery = atlas_dataset.Equipment.Storage.GetInstanceByName(f"{node_name}_battery")
                if not normal_battery:
                    instance_name = f"{node_name}_battery"
                else:
                    instance_name = f"{node_name}_battery_pcomp"
                atlas_dataset.Equipment.Storage.CreateInstance(instance_name)

                battery = atlas_dataset.Equipment.Storage.GetInstanceByName(instance_name)

                battery.MaximumPower = maximum_power
                battery.MaximumEnergy = stock_1

                if p.consumption_production_separation:
                    portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(f"generator_{node_name}")
                else:
                    portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(f"portfolio_{node_name}")

                # general properties of a storage equipment
                battery.Node = atlas_dataset.Network.Node.GetInstanceByName(node_name)
                battery.Portfolio = portfolio
                battery.StorageType = "Battery"
                try:
                    if binding_constraint.Weights[1] != 0:
                        battery.DischargeEfficiency = abs(1 / binding_constraint.Weights[1])
                    else:
                        battery.DischargeEfficiency = 1
                    battery.ChargeEfficiency = abs(binding_constraint.Weights[0])
                except:
                    battery.DischargeEfficiency = 1
                    battery.ChargeEfficiency = 1

                battery.SetupDelay = 0  # look at description !! ??

                # POWER
                # time series of the discharge of the battery
                # signe : + (because give power to electric system)
                if not power_discharge:
                    power_discharge = API.TimeSeries.NewTimeSeries(
                        "Power_discharge", API.TimeSeries.Constant, p.start_date.ToString(), "1Y", 2, 0, "MW"
                    )

                # time series of the charge of the battery
                # signe : - (because loss of energy view from electric system)
                power_charge = -links.CalculatedTransit[str(p.scenario)]

                # power time series
                power_timeseries = power_discharge + power_charge
                battery.Power.AddTimeSeries(p.execution_date, power_timeseries)

                # Pmin
                # =capacity of the link
                minimum_power = -links.DirectTransferCapacity.GetTimeSeriesByName("1")
                battery.MinimumPower = API.TimeSeries.NewTimeSeries(
                    "MinimumPower",
                    API.TimeSeries.Constant,
                    p.start_date.ToString(),
                    "1Y",
                    2,
                    minimum_power[p.start_date],
                    "MW",
                )

                # Minimum State of Charge  = 0 for batteries
                battery.MinimumStateOfCharge = API.TimeSeries.NewTimeSeries(
                    "MinimumStateOfCharge", API.TimeSeries.Constant, p.start_date.ToString(), "1Y", 2, 0, "MW"
                )

                # Initial level
                battery.StorageInitialLevel = p.battery_initial_level

                # TODO: to be refined later, when battery unit counts are indicated in Antares
                battery.UnitCount = 1

            elif p.verbose:
                API.IO.Trace.Log(
                    f"No BindingConstraint found for batteries_pcomp of node {node_name}, no Storage equipment created",
                    API.IO.LogTypeInfo,
                )

    # MERGE
    normal_instance = atlas_dataset.Equipment.Storage.GetInstanceByName(f"{node_name}_battery")
    pcomp_instance = atlas_dataset.Equipment.Storage.GetInstanceByName(f"{node_name}_battery_pcomp")
    if normal_instance and pcomp_instance:
        normal_instance.MaximumPower += pcomp_instance.MaximumPower
        normal_instance.MinimumPower += pcomp_instance.MinimumPower
        normal_instance.MaximumEnergy += pcomp_instance.MaximumEnergy

        # Moyenne pondérée par le MaximumPower/MinimumPower
        max_power_1 = normal_instance.MaximumPower.FirstValue
        max_power_2 = pcomp_instance.MaximumPower.FirstValue
        min_power_1 = normal_instance.MinimumPower.FirstValue
        min_power_2 = pcomp_instance.MinimumPower.FirstValue
        discharge_1 = normal_instance.DischargeEfficiency
        discharge_2 = pcomp_instance.DischargeEfficiency
        charge_1 = normal_instance.ChargeEfficiency
        charge_2 = pcomp_instance.ChargeEfficiency
        normal_instance.DischargeEfficiency = (discharge_1 * max_power_1 + discharge_2 * max_power_2) / (
            max_power_1 + max_power_2
        )
        normal_instance.ChargeEfficiency = (charge_1 * min_power_1 + charge_2 * min_power_2) / (
            min_power_1 + min_power_2
        )

        power_timeseries = normal_instance.Power.TimeSeries[0] + pcomp_instance.Power.TimeSeries[0]
        normal_instance.Power.DeleteTimeSeries(p.execution_date)
        normal_instance.Power.AddTimeSeries(p.execution_date, power_timeseries)

        atlas_dataset.Equipment.Storage.DeleteInstanceByName(f"{node_name}_battery_pcomp")

    return 0


# Retrieve the correct Disponibility TimeSeries of the "batteries_inj" thermal technology
def get_batteries_inj_data(antares_dataset, node, p, is_pcomp):
    # we want to have the time series of the thermal technology "batteries_inj" of the node
    node_special_format = functions.node_special_format(node)
    if is_pcomp:
        node_batteries_inj = f"{node}_{node_special_format}_batteries_pcomp_inj"
    else:
        node_batteries_inj = f"{node}_{node_special_format}_batteries_inj"
    thermal = antares_dataset.ThermalTechnology.GetInstanceByName(node_batteries_inj)
    time_series_pmax = thermal.Disponibility[str(p.scenario)]
    time_series_power = thermal.CalculatedPower[str(p.scenario)]

    return time_series_power, time_series_pmax
