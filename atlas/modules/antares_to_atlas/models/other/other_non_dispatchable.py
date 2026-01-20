def conversion_non_dispatchable(antares_dataset, atlas_dataset, p):
    for antares_node in antares_dataset.Node.GetAllInstances():
        if antares_node.Name in p.market_areas_list:
            # define the indices used to access the desired MC scenario in the Antares marker
            try:
                sc_hydro = antares_node.HydroReservoir.HydroSelectedScenario[p.scenario - 1]
            except SystemError:
                msg = f"Error with scenario {p.scenario} for unit {antares_node.Name}_hydro, potentially out of bounds"
                raise SystemError(msg)

            if antares_node.HydroReservoir.ROR.Count > sc_hydro - 1:
                ror = antares_node.HydroReservoir.ROR.TimeSeries[sc_hydro - 1]
                if ror.Abs().Max() > 0:
                    non_dispatch = atlas_dataset.Equipment.OtherNonDispatchable.CreateInstance(
                        f"{antares_node.Name}_ror"
                    )
                    non_dispatch.MaximumPowerForecast.AddTimeSeries(p.execution_date, ror)
                    if p.consumption_production_separation:
                        non_dispatch.Portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(
                            f"generator_{antares_node.Name}"
                        )
                    else:
                        non_dispatch.Portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(
                            f"portfolio_{antares_node.Name}"
                        )
                    non_dispatch.Node = atlas_dataset.Network.Node.GetInstanceByName(antares_node.Name)

            for source in antares_node.MiscGenProduction.Index:
                prod = antares_node.MiscGenProduction[source]
                if prod.Abs().Max() > 0:
                    non_dispatch = atlas_dataset.Equipment.OtherNonDispatchable.CreateInstance(
                        antares_node.Name + "_" + str(source)
                    )
                    non_dispatch.MaximumPowerForecast.AddTimeSeries(p.execution_date, prod)
                    if p.consumption_production_separation:
                        non_dispatch.Portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(
                            f"generator_{antares_node.Name}"
                        )
                    else:
                        non_dispatch.Portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(
                            f"portfolio_{antares_node.Name}"
                        )
                    non_dispatch.Node = atlas_dataset.Network.Node.GetInstanceByName(antares_node.Name)

    return None
