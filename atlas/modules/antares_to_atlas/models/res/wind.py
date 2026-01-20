import API


def conversion_wind(antares_dataset, atlas_dataset, p):
    if antares_dataset.GeneralSettings.GetInstanceByName("Settings").RenewableGenerationModelling == "clusters":
        for instance in antares_dataset.Renewables.GetAllInstances():
            # Note that WindOffshore is currently merged with WindOnshore due to the lack of data for the forecasting model
            if instance.Group != "WindOnshore" and instance.Node.Name.lower() not in ["dekf", "dkkf"]:
                continue

            if not instance.Enabled:
                continue

            if instance.Node.Name in p.market_areas_list:
                # FC: Replacing the try except here, correct in theory but which is not working in ATLAS
                # for some reason (if the try fails, the code crashes without going into the except...)
                if p.scenario - 1 >= len(instance.RenewablesSelectedScenario):
                    continue

                sc_wind = instance.RenewablesSelectedScenario[p.scenario - 1]

                if str(sc_wind) in instance.Disponibility.Index:
                    if instance.Disponibility[sc_wind].Abs().Max() > 0:
                        wind = atlas_dataset.Equipment.Wind.CreateInstance(f"{instance.Node.Name}_wind")

                        if p.consumption_production_separation:
                            wind.Portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(
                                f"generator_{instance.Node.Name}"
                            )
                        else:
                            wind.Portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(
                                f"portfolio_{instance.Node.Name}"
                            )

                        wind.Node = atlas_dataset.Network.Node.GetInstanceByName(instance.Node.Name)
                        wind.MaximumCurtailmentRatio = API.TimeSeries.NewTimeSeries(
                            "MaximumCurtailmentRatio",
                            API.TimeSeries.Constant,
                            p.start_date.ToString(),
                            "1Y",
                            2,
                            p.wind_max_curtailment_ratio,
                            "",
                        )
                        wind.CurtailmentCost = API.TimeSeries.NewTimeSeries(
                            "CurtailmentCost",
                            API.TimeSeries.Constant,
                            p.start_date.ToString(),
                            "1Y",
                            2,
                            p.wind_curtailment_cost,
                            "",
                        )

                        wind.InstalledCapacity = instance.NominalCapacity
                        if antares_dataset.Renewables.CheckInstanceExists(
                            instance.Node.Name + "_wind_offshore"
                        ) and instance.Node.Name.lower() not in ["dekf", "dkkf"]:
                            offshore_instance = antares_dataset.Renewables.GetInstanceByName(
                                instance.Node.Name + "_wind_offshore"
                            )

                            if offshore_instance.Enabled:
                                wind.InstalledCapacity += offshore_instance.NominalCapacity

    else:
        for antares_node in antares_dataset.Node.GetAllInstances():
            if antares_node.Name in p.market_areas_list:
                # FC: Replacing the try except here, correct in theory but which is not working in ATLAS
                # for some reason (if the try fails, the code crashes without going into the except...)
                if p.scenario - 1 >= len(antares_node.WindSelectedScenario):
                    continue

                sc_wind = antares_node.WindSelectedScenario[p.scenario - 1]

                if str(sc_wind) in antares_node.WindProduction.Index:
                    if antares_node.WindProduction.Abs().Max() > 0:
                        wind = atlas_dataset.Equipment.Wind.CreateInstance(f"{antares_node.Name}_w")

                        if p.consumption_production_separation:
                            wind.Portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(
                                f"supplier_{antares_node.Name}"
                            )
                        else:
                            wind.Portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(
                                f"portfolio_{antares_node.Name}"
                            )

                        wind.Node = atlas_dataset.Network.Node.GetInstanceByName(antares_node.Name)
                        wind.MaximumCurtailmentRatio = API.TimeSeries.NewTimeSeries(
                            "MaximumCurtailmentRatio",
                            API.TimeSeries.Constant,
                            p.start_date.ToString(),
                            "1Y",
                            2,
                            p.wind_max_curtailment_ratio,
                            "",
                        )

    return None
