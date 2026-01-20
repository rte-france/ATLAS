import API


def conversion_load(antares_input_marker, atlas_output_marker, p):
    for antares_node in antares_input_marker.Node.GetAllInstances():
        if antares_node.Name in p.market_areas_list:
            # define the indices used to access the desired MC scenario in the Antares marker
            try:
                sc_load = antares_node.LoadSelectedScenario[p.scenario - 1]
            except SystemError:
                msg = "Error with scenario {} for unit {}_l, potentially out of bounds".format(
                    p.scenario, antares_node.Name
                )
                raise SystemError(msg)

            if str(sc_load) in antares_node.Load.Index:
                if antares_node.Load[str(sc_load)].Abs().Max() > 0:
                    load = atlas_output_marker.Equipment.Load.CreateInstance("{}_l".format(antares_node.Name))
                    if p.consumption_production_separation:
                        load.Portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                            "supplier_{}".format(antares_node.Name)
                        )
                    else:
                        load.Portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                            "portfolio_{}".format(antares_node.Name)
                        )
                    load.LoadType = "Baseload"
                    load.Node = atlas_output_marker.Network.Node.GetInstanceByName(antares_node.Name)

    return None
