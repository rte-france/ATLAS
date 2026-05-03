import API
import os
import inflows

def conversion_hydraulic(antares_input_marker, atlas_output_marker, p):

    # Hydraulic reservoir file
    hydro_reservoirs = {}
    hydro_index = {}
    inflows_dictionary = {}

    if os.path.isfile(p.hydro_reservoirs_file): 
        f = open(p.hydro_reservoirs_file,"r")
        lines_list = f.readlines()
        f.close()
        interval_length = len(lines_list)
        
        for row_index, line in enumerate(lines_list[0:interval_length]):
            if row_index == 0:
                headers = line.split(";")
                for i in range(len(headers)):
                    if i == 0:
                        continue
                    hydro_reservoirs[headers[i].strip()] = {}
                    hydro_index[headers[i].strip()] = i
                    
            if row_index > 0:
                splitted_line = line.split(";") 
                if not len(splitted_line) == len(headers):
                    msg = "The number of columns is invalid on line {}. "\
                    "Please modify the HydraulicReservoirs file before proceeding again.".format(str(row_index+1))
                    raise ValueError(msg)
                
                for key,value in hydro_index.items():
                    hydro_reservoirs[key][splitted_line[0]] = float(splitted_line[value])

    for antares_node in antares_input_marker.Node.GetAllInstances():
        if antares_node.Name in p.market_areas_list:

            # define the indices used to access the desired MC scenario in the Antares marker        
            try:
                sc_hydro = antares_node.HydroReservoir.HydroSelectedScenario[p.scenario - 1]
            except SystemError:
                msg = "Error with scenario {} for unit {}_hydro, potentially out of bounds".format(p.scenario, antares_node.Name)
                raise SystemError(msg)
                        
            if str(p.scenario) in antares_node.HydroReservoir.CalculatedStorageProduction.Index:
                if antares_node.HydroReservoir.GeneratingMaxPower.Abs().Max() == 0.:
                    continue
                if antares_node.Name in hydro_reservoirs.keys() and hydro_reservoirs[antares_node.Name]["ReservoirCapacity"] == 0:
                    continue
                hydro = atlas_output_marker.Equipment.Hydraulic.CreateInstance("{}_hydro".format(antares_node.Name))
                if p.consumption_production_separation:
                    hydro.Portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName("generator_{}".format(antares_node.Name))
                else:
                    hydro.Portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName("portfolio_{}".format(antares_node.Name))
                hydro.Node = atlas_output_marker.Network.Node.GetInstanceByName(antares_node.Name)  
                hydro.EnergyTargetFrequency = "Daily"
                hydro.InflowFrequency = "Daily"
                hydro.MaximumPower = antares_node.HydroReservoir.GeneratingMaxPower
                hydro.MinimumPower = API.TimeSeries.NewTimeSeries('MinPower', API.TimeSeries.Constant, 
                                                                  p.start_date.ToString(), "1Y", 2, 0.0, 'MW')

                # Retrieve the Hydraulic Reservoir Capacity from the Antares marker
                # If it is missing, retrieve it from the HydraulicReservoirs csv
                if (antares_node.HydroReservoir.ReservoirCapacity > 0) or (antares_node.Name not in hydro_reservoirs.keys()):
                    hydro.MaximumEnergy = API.TimeSeries.NewTimeSeries('MaximumEnergy', API.TimeSeries.Constant, p.start_date.ToString(), 
                                                                       '1Y', 2, antares_node.HydroReservoir.ReservoirCapacity, 'MWh')
                                        
                    if antares_node.HydroReservoir.ReservoirCapacity == 0:
                        API.IO.Trace.Log("Warning, Reservoir Capacity of Equipment {} is set to 0. "\
                                         "Water values won't be calculated for this Equipment".format(hydro.Name))
                    
                else:
                    hydro.MaximumEnergy = API.TimeSeries.NewTimeSeries('MaximumEnergy', API.TimeSeries.Constant, p.start_date.ToString(), 
                                                                       '1Y', 2, hydro_reservoirs[antares_node.Name]["ReservoirCapacity"], 'MWh')
                                        
                    if hydro_reservoirs[antares_node.Name] == 0:
                        API.IO.Trace.Log("Warning, Reservoir Capacity of Equipment {} is set to 0. "\
                                         "Water values won't be calculated for this Equipment".format(hydro.Name))
                        
                # Retrieve or recompute Inflows and generate water values, based on the following logic:
                # _ For a given Antares node, if ReservoirManagement is OFF, then Inflow timeseries (stored in 'Modulation')
                #   give the actual inflows of the node, and can be directly utilized as such.
                # _ However, if ReservoirManagement is ON, the hydro equipment is allowed to postpone or advance its usage of 
                #   the energy brought by inflows. Consequently, the information contained in Modulation does not directly 
                #   give inflows, but instead the energy produced over a given period (which can integrate advance or postponment of inflows).
                #   In that case, generic historical inflow profiles are used for each node. These profiles should be given by the user
                #   in its data folder on Prometheus, at the path indicated by the parameter PathInflows
                # FC: this should be reworked, to point to the SAMBA folder instead
                
                if (p.use_hydro_heuristic or antares_node.HydroReservoir.ReservoirManagement) and p.use_water_value:
                    # Inflows
                    if antares_node.HydroReservoir.Modulation.Count > sc_hydro - 1:
                        if antares_node.HydroReservoir.ReservoirManagement:
                            
                            hydro.Inflows = antares_node.HydroReservoir.Modulation.GetTimeSeriesByName(str(sc_hydro))
                            node_inflows_dictionary = {}
                            
                            # Store the inflows that will be used during water values computation in node_inflows_dictionary
                            available_scenarios = [ts.Name for ts in antares_node.CalculatedMarginalPrice.TimeSeries]
                            if p.water_value_scenarios == "All":
                                scenarios = available_scenarios
                            else:
                                scenarios = p.water_value_scenarios.split(sep = ";")

                            for scenario_index, scenario in enumerate(scenarios):
                                local_hydro_sc = antares_node.HydroReservoir.HydroSelectedScenario[int(scenario) -1]

                                node_inflows_dictionary[scenario] = antares_node.HydroReservoir.Modulation.GetTimeSeriesByName(str(local_hydro_sc))
                        else:
                            node_inflows_dictionary = inflows.AddInflows(antares_node, hydro, antares_node.HydroReservoir.Modulation, sc_hydro, p)
                                            
                        inflows_dictionary[antares_node.Name] = node_inflows_dictionary
                                            
                else:
                    if str(sc_hydro) in antares_node.HydroReservoir.Modulation.Index:
                        hydro.EnergyTarget = antares_node.HydroReservoir.Modulation.GetTimeSeriesByName(str(sc_hydro))                 
                    
                hydro.MinimumEnergy = API.TimeSeries.NewTimeSeries('MinimumEnergy', API.TimeSeries.Constant, 
                                                                   p.start_date.ToString(), '1Y', 2, 0, 'MWh')
                
                one_year_days_index = API.DatetimeIndex.NewIndex(p.start_date, p.start_date.AddYears(1),'1d')
                one_year_hours_index = API.DatetimeIndex.NewIndex(p.start_date, p.start_date.AddYears(1), '1h')                
            
                hydro.HasDailyEnergyConstraint = True
                hydro.MinimumDailyEnergy = API.TimeSeries.NewTimeSeries('MinimumDailyEnergy', API.TimeSeries.Constant, 
                                                                        'MWh', one_year_days_index, 0.0)
                hydro.MaximumDailyEnergy = API.TimeSeries.NewTimeSeries('MaximumDailyEnergy', API.TimeSeries.Constant, 
                                                                        'MWh', one_year_days_index, 0.0) 
                power_hourly = antares_node.HydroReservoir.CalculatedStorageProduction.GetTimeSeriesByName(str(p.scenario))
                power_hourly.ChangeIndex(one_year_hours_index)
                for time_step in range(len(one_year_days_index) - 1):
                    one_day_energy = power_hourly.Slice(one_year_days_index[time_step], one_year_days_index[time_step].AddDays(1).AddHours(-1))
                    hydro.MinimumDailyEnergy[one_year_days_index[time_step]] = one_day_energy.Sum() * p.hydro_min_energy_coeff                
                    hydro.MaximumDailyEnergy[one_year_days_index[time_step]] = one_day_energy.Sum() * p.hydro_max_energy_coeff
                    
                # Fill FragmentVolumes and FragmentPrices attributes
                if antares_node.Name in p.fragment_prices.keys():
                    local_prices = p.fragment_prices[antares_node.Name]
                else:
                    local_prices = p.fragment_prices["Generic"]
                for price in local_prices:
                    hydro.FragmentPrices.Add(price)
                    
                if antares_node.Name in p.fragment_volumes.keys():
                    local_volumes = p.fragment_volumes[antares_node.Name]
                else:
                    local_volumes = p.fragment_volumes["Generic"]
                for volume in local_volumes:
                    hydro.FragmentVolumes.Add(volume)
                                       

    return inflows_dictionary, hydro_reservoirs                        