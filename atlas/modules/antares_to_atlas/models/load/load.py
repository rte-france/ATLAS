def conversion_load(antares_dataset, atlas_dataset, p):
    for antares_node in antares_dataset.Node.GetAllInstances():
        if antares_node.Name in p.market_areas_list:
            # define the indices used to access the desired MC scenario in the Antares marker
            try:
                sc_load = antares_node.LoadSelectedScenario[p.scenario - 1]
            except SystemError:
                msg = f"Error with scenario {p.scenario} for unit {antares_node.Name}_l, potentially out of bounds"
                raise SystemError(msg)

            if str(sc_load) in antares_node.Load.Index:
                if antares_node.Load[str(sc_load)].Abs().Max() > 0:
                    load = atlas_dataset.Equipment.Load.CreateInstance(f"{antares_node.Name}_l")
                    if p.consumption_production_separation:
                        load.Portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(
                            f"supplier_{antares_node.Name}"
                        )
                    else:
                        load.Portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(
                            f"portfolio_{antares_node.Name}"
                        )
                    load.LoadType = "Baseload"
                    load.Node = atlas_dataset.Network.Node.GetInstanceByName(antares_node.Name)

    return None
