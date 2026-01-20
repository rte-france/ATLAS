import API


def conversion_non_dispatchable(antares_input_marker, atlas_output_marker, p):
    for antares_node in antares_input_marker.Node.GetAllInstances():
        if antares_node.Name in p.market_areas_list:
            # define the indices used to access the desired MC scenario in the Antares marker
            try:
                sc_hydro = antares_node.HydroReservoir.HydroSelectedScenario[p.scenario - 1]
            except SystemError:
                msg = "Error with scenario {} for unit {}_hydro, potentially out of bounds".format(
                    p.scenario, antares_node.Name
                )
                raise SystemError(msg)

            if antares_node.HydroReservoir.ROR.Count > sc_hydro - 1:
                ror = antares_node.HydroReservoir.ROR.TimeSeries[sc_hydro - 1]
                if ror.Abs().Max() > 0:
                    non_dispatch = atlas_output_marker.Equipment.OtherNonDispatchable.CreateInstance(
                        "{}_ror".format(antares_node.Name)
                    )
                    non_dispatch.MaximumPowerForecast.AddTimeSeries(p.execution_date, ror)
                    if p.consumption_production_separation:
                        non_dispatch.Portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                            "generator_{}".format(antares_node.Name)
                        )
                    else:
                        non_dispatch.Portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                            "portfolio_{}".format(antares_node.Name)
                        )
                    non_dispatch.Node = atlas_output_marker.Network.Node.GetInstanceByName(antares_node.Name)

            for source in antares_node.MiscGenProduction.Index:
                prod = antares_node.MiscGenProduction[source]
                if prod.Abs().Max() > 0:
                    non_dispatch = atlas_output_marker.Equipment.OtherNonDispatchable.CreateInstance(
                        antares_node.Name + "_" + str(source)
                    )
                    non_dispatch.MaximumPowerForecast.AddTimeSeries(p.execution_date, prod)
                    if p.consumption_production_separation:
                        non_dispatch.Portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                            "generator_{}".format(antares_node.Name)
                        )
                    else:
                        non_dispatch.Portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                            "portfolio_{}".format(antares_node.Name)
                        )
                    non_dispatch.Node = atlas_output_marker.Network.Node.GetInstanceByName(antares_node.Name)

    return None
