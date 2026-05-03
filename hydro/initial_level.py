import API
import os

def initial_level_computation(antares_input_marker, atlas_output_marker, p):

    # The following file contains the evolution of the reservoir level over the time horizon, provided as a 1 column csv file.
    # This curve is only used for hydraulic reservoir whose reservoir management is not active in the Antares input marker.
    # For such reservoirs, the file is used to initialize the InitialLevel property of Hydraulic instances in the ATLAS model.
    # For others, who use the Antares reservoir management feature, the InitialLevel property will be initialized with the
    # Antares property RemainingEnergyLevel
    curve_values = API.Helpers.CreateListDouble()
    if os.path.isfile(p.hydro_initialization_curve): 
        f = open(p.hydro_initialization_curve,"r")
        lines_list = f.readlines()
        f.close()
        interval_length = len(lines_list)
        if interval_length > 0:
            for row_index, line in enumerate(lines_list[0:interval_length]):
                curve_values.Add(float(line))
                
    curve_index = API.DatetimeIndex.NewIndex(p.start_date, p.start_date.AddHours(interval_length-1), '1h')
    res_curve = API.TimeSeries.NewTimeSeries('GuideCurve', API.TimeSeries.Constant, '', curve_index, curve_values)

    if p.verbose:
        msg = "The first value of the hydro initialization curve is: {}".format(res_curve.GetValue(p.start_date))
        API.IO.Trace.Log(msg, API.IO.LogTypeInfo) 
        msg = "The last value of the hydro initialization curve is: {}".format(res_curve.GetValue(res_curve.LastDate))
        API.IO.Trace.Log(msg, API.IO.LogTypeInfo)    


    for instance in atlas_output_marker.Equipment.Hydraulic.GetAllInstances():
            
        antares_node = antares_input_marker.Node.GetInstanceByName(instance.Node.Name)
        if antares_node.Name not in p.market_areas_list:
            continue

        if antares_node.HydroReservoir.ReservoirManagement and (str(p.scenario) in antares_node.HydroReservoir.RemainingEnergyLevel.Index):    
            instance.InitialLevel = 1/100. * antares_node.HydroReservoir.RemainingEnergyLevel.GetTimeSeriesByName(str(p.scenario)) * instance.MaximumEnergy
        else:
            instance.InitialLevel = 1/100. * res_curve * instance.MaximumEnergy

    return None

