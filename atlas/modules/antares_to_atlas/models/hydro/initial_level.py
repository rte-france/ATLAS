import os

import API


def initial_level_computation(antares_dataset, atlas_dataset, p):
    # The following file contains the evolution of the reservoir level over the time horizon, provided as a 1 column csv file.
    # This curve is only used for hydraulic reservoir whose reservoir management is not active in the Antares input marker.
    # For such reservoirs, the file is used to initialize the InitialLevel property of Hydraulic instances in the ATLAS model.
    # For others, who use the Antares reservoir management feature, the InitialLevel property will be initialized with the
    # Antares property RemainingEnergyLevel
    curve_values = API.Helpers.CreateListDouble()
    if os.path.isfile(p.hydro_initialization_curve):
        f = open(p.hydro_initialization_curve)
        lines_list = f.readlines()
        f.close()
        interval_length = len(lines_list)
        if interval_length > 0:
            for row_index, line in enumerate(lines_list[0:interval_length]):
                curve_values.Add(float(line))

    curve_index = API.DatetimeIndex.NewIndex(p.start_date, p.start_date.AddHours(interval_length - 1), "1h")
    res_curve = API.TimeSeries.NewTimeSeries("GuideCurve", API.TimeSeries.Constant, "", curve_index, curve_values)

    if p.verbose:
        msg = f"The first value of the hydro initialization curve is: {res_curve.GetValue(p.start_date)}"
        API.IO.Trace.Log(msg, API.IO.LogTypeInfo)
        msg = f"The last value of the hydro initialization curve is: {res_curve.GetValue(res_curve.LastDate)}"
        API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

    for instance in atlas_dataset.Equipment.Hydraulic.GetAllInstances():
        antares_node = antares_dataset.Node.GetInstanceByName(instance.Node.Name)
        if antares_node.Name not in p.market_areas_list:
            continue

        if antares_node.HydroReservoir.ReservoirManagement and (
            str(p.scenario) in antares_node.HydroReservoir.RemainingEnergyLevel.Index
        ):
            instance.InitialLevel = (
                1
                / 100.0
                * antares_node.HydroReservoir.RemainingEnergyLevel.GetTimeSeriesByName(str(p.scenario))
                * instance.MaximumEnergy
            )
        else:
            instance.InitialLevel = 1 / 100.0 * res_curve * instance.MaximumEnergy

    return None
