import sys

import API


def compute_water_value(antares_dataset, atlas_dataset, inflows_dictionary, p):
    for antares_node in antares_dataset.Node.GetAllInstances():
        if antares_node.Name in p.market_areas_list:
            hydro = atlas_dataset.Equipment.Hydraulic.GetInstanceByName(antares_node.Name + "_hydro")

            node_water_value_computation(antares_node, hydro, inflows_dictionary, p)


# This function calculates the water values of a hydraulic reservoir defined in the antares marker
def node_water_value_computation(antares_node, hydro, inflows_dictionary, p):
    # We retrieve the MC scenarios to use for the computation...
    scenario_parameter = p.water_value_scenarios
    available_scenarios = [int(ts.Name) for ts in antares_node.CalculatedMarginalPrice.TimeSeries]
    if scenario_parameter == "All":
        scenarios = available_scenarios
    else:
        scenarios = scenario_parameter.split(sep=";")
        for s in range(len(scenarios)):
            scenarios[s] = int(scenarios[s])
            if scenarios[s] not in available_scenarios:
                msg = (
                    f"Cannot compute water values for {hydro.Name}: the scenario '{scenarios[s]}' specified in the parameter WaterValueScenarios does not exist "
                    f"in the CalculatedMarginalPrice matrix of node {antares_node.Name}. Available price scenarios in {antares_node.Name} are: {available_scenarios}"
                )
                raise Exception(msg)

    # ... And we trace them in the logs:
    msg = "Antares node : " + str(antares_node.Name)
    API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

    if antares_node.Name not in inflows_dictionary:
        msg = f"No hydro unit for node {antares_node.Name}, no water values computed"
        API.IO.Trace.Log(msg, API.IO.LogTypeInfo)
        return None

    msg = "Scenarios for computing water values: " + str(scenarios)
    API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

    # We build all the time index we need for computing the water value matrix
    one_year_hours_index = API.DatetimeIndex.NewIndex(
        p.start_date, p.start_date.AddYears(1), str(p.water_value_time_step) + "m"
    )
    Time = range(len(one_year_hours_index) * p.water_value_nb_years)

    # QB: Unused, commented for now
    # inflowScenario = antares_node.HydroReservoir.HydroSelectedScenario

    inflows = []
    for s in scenarios:
        # We distribute inflows evenly over the hourly time period, based on the
        # inflows associated with the current scenario contained in inflows_dictionary:
        input_inflow = inflows_dictionary[antares_node.Name][str(s)]

        # In Antares v7, modulated inflows have a daily frequency, so the even distribution
        # simply consists in a division by 24 of the entire time series:
        hourly_inflow = input_inflow / 24.0
        inflows.append(hourly_inflow)

    Power = hydro.MaximumPower.Average()
    CapacityStep = int(Power / p.hydro_storage_subdivision)

    Capacity = int(hydro.MaximumEnergy.FirstValue)
    Stock = range(0, Capacity, CapacityStep)
    msg = f"Total capacity: {Capacity}, capacity step: {CapacityStep}"
    API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

    WV = {}
    for level in range(1, len(Stock)):
        WV[level] = {}
        for t in range(len(one_year_hours_index)):
            WV[level][t] = 0

    # Loop over all the price scenarios in the Antares marker
    for sc in range(len(scenarios)):
        # Water Value per scenario per time per level, time only first year
        WV_sc = {}
        msg = f"Scenario {scenarios[sc]}"
        API.IO.Trace.Log(msg, API.IO.LogTypeInfo)
        PriceForecast_sc = antares_node.CalculatedMarginalPrice.GetTimeSeriesByName(str(scenarios[sc]))
        # Bellman value per time per level
        BV = {}
        # loop backwards over time, from nb years to 0 in hours
        for t in Time[len(Time) - 1 :: -1]:
            # Assign the maximum power capacity and energy price at time T
            # For t > 1yr, maxpower, price and inflows are identical to their value the first year at the same hour
            MaxPower_t = hydro.MaximumPower.GetValue(one_year_hours_index[t % len(one_year_hours_index)])
            Price_t = PriceForecast_sc.GetValue(one_year_hours_index[t % len(one_year_hours_index)])
            Inflows_t = inflows[sc].GetValue(one_year_hours_index[t % len(one_year_hours_index)])
            BV[t] = {}
            # Define the WV_sc[sc][t] vector for the first year
            if t < len(one_year_hours_index):
                WV_sc[t] = {}
            # loop over stock levels
            for level in range(len(Stock)):
                # if t = t_final, BV[t][level] = 0
                if t == Time[len(Time) - 1]:
                    BV[t][level] = 0
                else:
                    # else, loop on lower possible levels starting from level to determine BV[t][level]
                    BV[t][level] = BV[t + 1][level] * p.beta
                    m = level
                    if level:
                        for j in range(p.hydro_storage_subdivision + 1):
                            # stock_j is the stock level after turbining at MaxPower * j / subdivision_parameter
                            Stock_i = Stock[level] + Inflows_t
                            Stock_j = Stock[level] - j * MaxPower_t / p.hydro_storage_subdivision + Inflows_t

                            if j == 0:
                                # case where we turbine the inflows
                                G1 = BV[t + 1][level] * p.beta + Inflows_t * Price_t
                                # stock level above Stock_i
                                n = int((Stock[level] + Inflows_t) // CapacityStep + 1)
                                G2 = 0
                                # case where we keep the inflows and increase stock
                                if n != level and n < len(Stock):
                                    G2 = BV[t + 1][n] + (Stock[level] + Inflows_t - Stock[n]) / (
                                        Stock[n] - Stock[n - 1]
                                    ) * (BV[t + 1][n] - BV[t + 1][n - 1])
                                G = max(G1, G2)

                            else:
                                if Stock_j > 0:
                                    while m > 0 and Stock[m] > Stock_j:
                                        m = m - 1
                                    # at the lowest level, the price is fixed at the price of failure
                                    if level == 1:
                                        if p.use_bellman_interpolation:
                                            gain = (Stock_i - Stock_j) * (-5000)
                                            stock_value = p.beta * (
                                                (BV[t + 1][m] - BV[t + 1][m + 1])
                                                * (Stock[m + 1] - Stock_j)
                                                / (Stock[m + 1] - Stock[m])
                                                + BV[t + 1][m + 1]
                                            )
                                        else:
                                            gain = (Stock_i - Stock[m]) * (-5000)
                                            stock_value = p.beta * BV[t + 1][m]
                                        G = gain + stock_value
                                    # case when we turbine at Pmax *j/subdivision_parameter
                                    elif m + 1 <= len(Stock) - 1:
                                        if p.use_bellman_interpolation:
                                            gain = (Stock_i - Stock_j) * Price_t
                                            stock_value = p.beta * (
                                                (BV[t + 1][m] - BV[t + 1][m + 1])
                                                * (Stock[m + 1] - Stock_j)
                                                / (Stock[m + 1] - Stock[m])
                                                + BV[t + 1][m + 1]
                                            )
                                        else:
                                            gain = (Stock_i - Stock[m]) * Price_t
                                            stock_value = p.beta * BV[t + 1][m]
                                        G = gain + stock_value
                            if G > BV[t][level]:
                                BV[t][level] = G

                    # we only keep values for the last year
                    if level and t < len(one_year_hours_index):
                        WV_sc[t][level] = (BV[t + 1][level] - BV[t + 1][level - 1]) / CapacityStep

        for level in range(1, len(Stock)):
            for t in range(len(one_year_hours_index)):
                # summing water values over all scenarios
                try:
                    WV[level][t] = WV[level][t] + WV_sc[t][level]
                except Exception as e:
                    API.IO.Trace.Log(str(e), API.IO.LogTypeError)
                    sys.exit()

    if p.nb_storage_levels > 0:
        M = int(len(Stock) / p.nb_storage_levels)

    if p.nb_storage_levels == 0 or M == 0:
        for level in range(1, len(Stock)):
            my_TimeSeries = API.TimeSeries.NewTimeSeries(
                str(level), API.TimeSeries.Linear, "MW", one_year_hours_index, 0
            )
            for t in range(len(one_year_hours_index)):
                # we keep the average water value over all scenarios
                WV[level][t] = WV[level][t] / len(scenarios)
                # FC: modification to bound the output water values below
                # the value of loss load, chosen at 26000 euros/MWh here.
                # This value can be modified or parametrized later.
                my_TimeSeries.SetValue(one_year_hours_index[t], min(WV[level][t], 26000))
            hydro.StorageMarginalValue.AddTimeSeries(str(int(round(Stock[level], 0))), my_TimeSeries)
    else:
        levels = []
        for level in range(1, len(Stock)):
            if (level - 1) % M == 0:
                levels.append(level)

        delta = len(levels) - p.nb_storage_levels
        levels_cutoff = levels[
            int(delta / 2) if delta % 2 == 0 else delta - int(delta / 2) : len(levels) - int(delta / 2)
        ]
        # loop over a subset of the levels
        for level in levels_cutoff:
            my_TimeSeries = API.TimeSeries.NewTimeSeries(
                str(level), API.TimeSeries.Linear, "MW", one_year_hours_index, 0
            )
            for t in range(len(one_year_hours_index)):
                # we keep the average water value over all scenarios
                WV[level][t] = WV[level][t] / len(scenarios)
                # FC: modification to bound the output water values below
                # the value of loss load, chosen at 26000 euros/MWh here.
                # This value can be modified or parametrized later.
                my_TimeSeries.SetValue(one_year_hours_index[t], min(WV[level][t], 26000))
            hydro.StorageMarginalValue.AddTimeSeries(str(int(round(Stock[level], 0))), my_TimeSeries)
