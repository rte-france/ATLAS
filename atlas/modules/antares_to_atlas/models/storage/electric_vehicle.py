import os

import API
import functions


# Core
def convert_electric_vehicle(antares_dataset, atlas_dataset, p):
    # Load file parameters, and convert csv into dictionaries or timeseries
    # ==============
    # Baseline DisplacementEnergy
    if os.path.isfile(p.baseline_displacement_energy):
        f = open(p.baseline_displacement_energy)
        lines_list = f.readlines()
        f.close()
        csv_length = len(lines_list)

        disp_energy_index = API.DatetimeIndex.NewIndex(p.start_date, p.start_date.AddYears(1), csv_length)
        baseline_displacement_energy_ts = API.TimeSeries.NewTimeSeries(
            "Baseline Displacement Energy", API.TimeSeries.Constant, "MW", disp_energy_index, 0
        )

        for row_index, line in enumerate(lines_list[0:csv_length]):
            if row_index > 0:
                splitted_line = line.split(";")
                baseline_displacement_energy_ts.SetValue(
                    disp_energy_index[row_index - 1], round(float(splitted_line[0]))
                )

    else:
        API.IO.Trace.Log("WARNING, BaselineDisplacementEnergy parameter is empty", API.IO.LogTypeError)

    # Specific node parameters
    specific_node_parameters = {}

    if os.path.isfile(p.disp_energy_node_parameters):
        f = open(p.disp_energy_node_parameters)
        lines_list = f.readlines()
        f.close()
        csv_length = len(lines_list)

        for row_index, line in enumerate(lines_list[0:csv_length]):
            if row_index > 0:
                splitted_line = line.split(";")
                specific_node_parameters[splitted_line[0].lower()] = [splitted_line[1], splitted_line[2]]

    else:
        API.IO.Trace.Log("WARNING, DispEnergyNodeParameters parameter is empty", API.IO.LogTypeError)

    # Standard nodes
    # ==============
    API.IO.Trace.Log("*** Converting standard EV ***")

    for antares_node in antares_dataset.Node.GetAllInstances():
        if antares_node.Name not in p.market_areas_list:
            continue

        # FR EV is treated separately, as it is modeled in a specific way in Antares
        # QB: je ne comprend pas bien pourquoi pl est ignoré, je commente pour le moment
        # if antares_node.Name in ["fr", "pl"]:
        if antares_node.Name in ["fr"]:
            continue

        API.IO.Trace.Log(f"Node {antares_node.Name}")

        # Get all useful data and instances
        if p.consumption_production_separation:
            atlas_portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(f"generator_{antares_node.Name}")
        else:
            atlas_portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(f"portfolio_{antares_node.Name}")
        atlas_node = atlas_dataset.Network.Node.GetInstanceByName(antares_node.Name)

        ev_inj = antares_dataset.ThermalTechnology.GetInstanceByName(
            f"{antares_node.Name}_{functions.node_special_format(antares_node.Name)}_VE_inj"
        )

        # Check if ev_inj instance exists, if not skip this node
        if not ev_inj:
            continue

        dispo_scenario = ev_inj.ThermalSelectedScenario[p.scenario - 1]

        ev_link = antares_dataset.Link.GetInstanceByName(f"{antares_node.Name}_ve_eu")
        ev_stock_bc = antares_dataset.BindingConstraint.GetInstanceByName(f"ve_stock_{antares_node.Name}")

        ev_stor = antares_dataset.ThermalTechnology.GetInstanceByName(
            f"ve_vhr_storage_VE_VHR_storage_VE_{functions.node_special_format(antares_node.Name)}_1"
        )

        if ev_stock_bc:
            # Create an ATLAS Storage instance and fill its properties
            if (
                ev_inj.Disponibility.GetTimeSeriesByName(str(dispo_scenario)).Abs().Max() == 0.0
                or ev_stor.Disponibility.GetTimeSeriesByName(str(dispo_scenario)).Abs().Max() == 0.0
            ):
                continue
            ev_instance = atlas_dataset.Equipment.Storage.CreateInstance(antares_node.Name + "_ev")
            ev_instance.Portfolio = atlas_portfolio
            ev_instance.Node = atlas_node
            ev_instance.isV2G = True
            ev_instance.StorageType = "ElectricVehicle"

            ev_instance.MaximumPower = ev_inj.Disponibility.GetTimeSeriesByName(str(dispo_scenario))
            ev_instance.MinimumPower = -1 * ev_link.DirectTransferCapacity.GetTimeSeriesByName("1")
            ev_instance.ChargeEfficiency = abs(ev_stock_bc.Weights[0])
            if ev_stock_bc.Weights[1] != 0:
                ev_instance.DischargeEfficiency = abs(1 / ev_stock_bc.Weights[1])
            else:
                ev_instance.DischargeEfficiency = 1

            ev_instance.MaximumEnergy = ev_stor.Disponibility.GetTimeSeriesByName(str(dispo_scenario))
            ev_instance.MinimumStateOfCharge = API.TimeSeries.NewTimeSeries(
                "MinimumStateOfCharge", API.TimeSeries.Constant, p.start_date.ToString(), "1Y", 2, 0.3, ""
            )

            # Initial level
            ev_instance.StorageInitialLevel = p.ev_initial_level

            # DisplacementEnergy
            local_specific_node_parameters = specific_node_parameters[antares_node.Name]

            unshifted_disp_energy = (float(local_specific_node_parameters[1]) * baseline_displacement_energy_ts).Round()

            new_index = API.DatetimeIndex.Shift(disp_energy_index, str((-1) * local_specific_node_parameters[0]) + "h")

            # ev_instance.DisplacementEnergy = unshifted_disp_energy.ChangeIndex(new_index)
            ev_instance.DisplacementEnergy = API.TimeSeries.NewTimeSeries(
                "DisplacementEnergy", API.TimeSeries.Constant, "MWh", new_index, unshifted_disp_energy.Values
            )

        else:
            API.IO.Trace.Log(f"No binding constraint found for node {antares_node.Name}, no EV instance created")

    API.IO.Trace.Log("*** Standard EV conversion done ***")

    # FR EV
    # =====
    if "fr" in p.market_areas_list:
        API.IO.Trace.Log("*** Converting FR EV ***")

        # --- Night only EV ---

        # Compute the ratio between the minimum load at night, and the minimum load per day
        # This ratio will be used to allocate the following properties to the night only EV:
        # - MaximumPower
        # - MinimumPower
        # - MaximumEnergy
        # - DisplacementEnergy

        # Retrieve useful data from the Antares input marker
        antares_node = antares_dataset.Node.GetInstanceByName("fr")
        ve_fr_total_node = antares_dataset.Node.GetInstanceByName("ve_fr_load_total")

        ev_link_total = antares_dataset.Link.GetInstanceByName(antares_node.Name + "_ve_fr_load_total")
        ev_inj = antares_dataset.ThermalTechnology.GetInstanceByName("fr_FR_VE_inj")
        ev_stor = antares_dataset.ThermalTechnology.GetInstanceByName("ve_vhr_storage_VE_VHR_storage_VE_FR_1")

        ve_fr_load_min = antares_dataset.BindingConstraint.GetInstanceByName("ve_fr_load_min")
        ve_fr_night_load_min = antares_dataset.BindingConstraint.GetInstanceByName("ve_fr_night_load_min")
        ve_stock_fr = antares_dataset.BindingConstraint.GetInstanceByName("ve_stock_fr")

        # Create a timeseries of 1 and 0 indicating when night EV are connected
        night_connection_capacity = ev_link_total.DirectTransferCapacity.GetTimeSeriesByName("1")
        if night_connection_capacity.Max() != 0:
            night_connection_hours = (1 / night_connection_capacity.Max()) * night_connection_capacity
        else:
            API.IO.Trace.Log(
                "WARNING: Possible error on the DirectTransferCapacity of ve_fr_load_total", API.IO.LogTypeWarn
            )
            night_connection_hours = night_connection_capacity

        one_year_index = API.DatetimeIndex.NewIndex(p.start_date, p.start_date.AddYears(1), "1h")

        # Compute the ratio of night only EV, based on the average of the entire year
        night_only_ev_ratio_raw = API.TimeSeries.NewTimeSeries(
            "Raw Night EV Ratio", API.TimeSeries.Constant, "", one_year_index, 0
        )

        for local_time in night_only_ev_ratio_raw.Index:
            if ve_fr_load_min.GreaterThan.GetValue(local_time) != 0:
                night_only_ev_ratio_raw.SetValue(
                    local_time,
                    (
                        ve_fr_night_load_min.GreaterThan.GetValue(local_time)
                        / ve_fr_load_min.GreaterThan.GetValue(local_time)
                    ),
                )

        night_only_ev_ratio = night_only_ev_ratio_raw.Average()

        # Store it in two different timeseries, used later on
        night_only_ev_ratio_complete = API.TimeSeries.NewTimeSeries(
            "Night EV Ratio Complete", API.TimeSeries.Constant, "", one_year_index, night_only_ev_ratio
        )

        # The following loop may seems unefficient but is actually required
        night_only_ev_ratio_ts = API.TimeSeries.NewTimeSeries(
            "Night EV Ratio", API.TimeSeries.Constant, "", one_year_index, 0
        )
        for local_time in night_only_ev_ratio_ts.Index:
            if ve_fr_load_min.GreaterThan.GetValue(local_time) != 0:
                night_only_ev_ratio_ts.SetValue(
                    local_time, (night_connection_hours.GetValue(local_time) * night_only_ev_ratio)
                )

        # Create an ATLAS Storage instance and fill its properties
        if p.consumption_production_separation:
            atlas_portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(f"generator_{antares_node.Name}")
        else:
            atlas_portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(f"portfolio_{antares_node.Name}")
        atlas_node = atlas_dataset.Network.Node.GetInstanceByName(antares_node.Name)

        ev_instance = atlas_dataset.Equipment.Storage.CreateInstance(f"{antares_node.Name}_ev_night")
        ev_instance.Portfolio = atlas_portfolio
        ev_instance.Node = atlas_node
        ev_instance.isV2G = True
        ev_instance.StorageType = "ElectricVehicle"

        # MaximumPower and MinimumPower
        night_maximum_power = API.TimeSeries.NewTimeSeries(
            "Night EV Maximum Power",
            API.TimeSeries.Constant,
            "MW",
            night_only_ev_ratio_ts.Index,
            night_only_ev_ratio_ts.Values,
        )
        night_maximum_power.Multiply(ev_inj.Disponibility.GetTimeSeriesByName(str(dispo_scenario)))
        ev_instance.MaximumPower = night_maximum_power.Round()

        night_minimum_power = API.TimeSeries.NewTimeSeries(
            "Night EV Minimum Power",
            API.TimeSeries.Constant,
            "MW",
            night_only_ev_ratio_ts.Index,
            night_only_ev_ratio_ts.Values,
        )
        night_minimum_power.Multiply(ve_fr_total_node.MiscGenProduction.GetTimeSeriesByName("ROWBalance"))
        ev_instance.MinimumPower = night_minimum_power.Round()

        ev_instance.ChargeEfficiency = abs(ve_stock_fr.Weights[0])
        if ve_stock_fr.Weights[2] != 0:
            ev_instance.DischargeEfficiency = abs(1 / ve_stock_fr.Weights[2])
        else:
            ev_instance.DischargeEfficiency = 1

        night_maximum_energy = API.TimeSeries.NewTimeSeries(
            "Night EV Maximum Energy",
            API.TimeSeries.Constant,
            "MWh",
            night_only_ev_ratio_ts.Index,
            night_only_ev_ratio_ts.Values,
        )
        night_maximum_energy.Multiply(ev_stor.Disponibility.GetTimeSeriesByName(str(dispo_scenario)))
        ev_instance.MaximumEnergy = night_maximum_energy.Round()
        # Quick Fix for MaximumEnergy being set to 0 during day in Antares ; in ATLAS we want it to remain constant, and the instance is already disabled during the day through its MaximumPower
        for t in ev_instance.MaximumEnergy.Index:
            if ev_instance.MaximumEnergy.GetValue(t) == 0.0:
                ev_instance.MaximumEnergy.SetValue(t, ev_instance.MaximumEnergy.GetValue(t.AddMinutes(-60)))

        ev_instance.MinimumStateOfCharge = API.TimeSeries.NewTimeSeries(
            "MinimumStateOfCharge", API.TimeSeries.Constant, p.start_date.ToString(), "1Y", 2, 0.3, ""
        )

        # Initial level
        ev_instance.StorageInitialLevel = p.ev_initial_level

        # DisplacementEnergy
        # For night EV, the corresponding DisplacementEnergy is calculated over the whole day (and not only night hours)
        # Then, this total value is divided on night hours only.

        local_specific_node_parameters = specific_node_parameters["fr"]
        unshifted_disp_energy = (float(local_specific_node_parameters[1]) * baseline_displacement_energy_ts).Round()
        new_index = API.DatetimeIndex.Shift(disp_energy_index, str((-1) * local_specific_node_parameters[0]) + "h")

        night_displacement_energy = API.TimeSeries.NewTimeSeries(
            "RawDisplacementEnergy", API.TimeSeries.Constant, "MWh", new_index, unshifted_disp_energy.Values
        )
        night_displacement_energy.Multiply(night_only_ev_ratio_complete)

        ev_instance.DisplacementEnergy = night_displacement_energy.Round()

        # --- Regular EV ---
        ev_link_total = antares_dataset.Link.GetInstanceByName(f"{antares_node.Name}_ve_fr_load_total")

        # Create an ATLAS Storage instance and fill its properties
        ev_instance = atlas_dataset.Equipment.Storage.CreateInstance(f"{antares_node.Name}_ev_regular")
        ev_instance.Portfolio = atlas_portfolio
        ev_instance.Node = atlas_node
        ev_instance.isV2G = True
        ev_instance.StorageType = "ElectricVehicle"

        ev_instance.ChargeEfficiency = abs(ve_stock_fr.Weights[0])
        if ve_stock_fr.Weights[2] != 0:
            ev_instance.DischargeEfficiency = abs(1 / ve_stock_fr.Weights[2])
        else:
            ev_instance.DischargeEfficiency = 1

        # MaximumPower, MinimumPower, MaximumEnergy and DisplacementEnergy are recomputed
        # by susbtracting the part associated with the night only EV.

        ev_instance.MaximumPower = (
            ev_inj.Disponibility.GetTimeSeriesByName(str(dispo_scenario)) - night_maximum_power
        ).Round()
        ev_instance.MinimumPower = (
            ve_fr_total_node.MiscGenProduction.GetTimeSeriesByName("ROWBalance") - night_minimum_power
        ).Round()

        ev_instance.MaximumEnergy = (
            ev_stor.Disponibility.GetTimeSeriesByName(str(dispo_scenario)) - night_maximum_energy
        )
        ev_instance.MinimumStateOfCharge = API.TimeSeries.NewTimeSeries(
            "MinimumStateOfCharge", API.TimeSeries.Constant, p.start_date.ToString(), "1Y", 2, 0.3, ""
        )

        # Initial level
        ev_instance.StorageInitialLevel = p.ev_initial_level

        shifted_disp_energy = API.TimeSeries.NewTimeSeries(
            "DisplacementEnergy", API.TimeSeries.Constant, "MWh", new_index, unshifted_disp_energy.Values
        )
        ev_instance.DisplacementEnergy = (shifted_disp_energy - night_displacement_energy).Round()

        # QB: For multi-energy only ?
        """#Maximum V2G constraint is stored in the fr_ev_regular instance but applies to the sum of both fr ev instances
        ve_fr_p2g_max_daily = antares_dataset.BindingConstraint.GetInstanceByName("VE_P2G_limit")
        one_year_days_index = API.DatetimeIndex.NewIndex(p.start_date, p.start_date.AddYears(1).AddHours(-1), "1d")
        ev_instance.MaximumDailyEnergy = ve_fr_p2g_max_daily.LessThan.Extract("", one_year_days_index) * ve_fr_p2g_max_daily.Weights[0]"""

        API.IO.Trace.Log("*** FR EV conversion done ***")

        # FR Mobilite lourde
        # =====
        API.IO.Trace.Log("*** Converting FR Mobilite lourde ***")

        # Retrieve useful informations
        antares_node = antares_dataset.Node.GetInstanceByName("fr")
        HV_link = antares_dataset.Link.GetInstanceByName("fr_ve_fr_mobilite_lourde")

        # Create a Load equipment in the Atlas output marker
        if p.consumption_production_separation:
            atlas_portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(f"supplier_{antares_node.Name}")
        else:
            atlas_portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(f"portfolio_{antares_node.Name}")
        atlas_node = atlas_dataset.Network.Node.GetInstanceByName(antares_node.Name)

        hv_instance = atlas_dataset.Equipment.Load.CreateInstance("fr_heavy_vehicles")
        hv_instance.Portfolio = atlas_portfolio
        hv_instance.Node = atlas_node

        # For now, we only consider a fix load given by the calculated flow on the link between the node and the Mobilite Lourde node.
        if str(p.scenario) in HV_link.CalculatedTransit.Index:
            hv_instance.MaximumPowerForecast.AddTimeSeries(
                p.execution_date, -1.0 * HV_link.CalculatedTransit.GetTimeSeriesByName(str(p.scenario))
            )
        hv_instance.LoadType = "OtherNonDispatchableLoad"

        API.IO.Trace.Log("*** FR Mobilite lourde conversion done ***")
