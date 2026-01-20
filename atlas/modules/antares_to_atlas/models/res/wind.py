import API


def conversion_wind(antares_input_marker, atlas_output_marker, p):
    if antares_input_marker.GeneralSettings.GetInstanceByName("Settings").RenewableGenerationModelling == "clusters":
        for instance in antares_input_marker.Renewables.GetAllInstances():
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
                        wind = atlas_output_marker.Equipment.Wind.CreateInstance("{}_wind".format(instance.Node.Name))

                        if p.consumption_production_separation:
                            wind.Portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                                "generator_{}".format(instance.Node.Name)
                            )
                        else:
                            wind.Portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                                "portfolio_{}".format(instance.Node.Name)
                            )

                        wind.Node = atlas_output_marker.Network.Node.GetInstanceByName(instance.Node.Name)
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
                        if antares_input_marker.Renewables.CheckInstanceExists(
                            instance.Node.Name + "_wind_offshore"
                        ) and instance.Node.Name.lower() not in ["dekf", "dkkf"]:
                            offshore_instance = antares_input_marker.Renewables.GetInstanceByName(
                                instance.Node.Name + "_wind_offshore"
                            )

                            if offshore_instance.Enabled:
                                wind.InstalledCapacity += offshore_instance.NominalCapacity

    else:
        for antares_node in antares_input_marker.Node.GetAllInstances():
            if antares_node.Name in p.market_areas_list:
                # FC: Replacing the try except here, correct in theory but which is not working in ATLAS
                # for some reason (if the try fails, the code crashes without going into the except...)
                if p.scenario - 1 >= len(antares_node.WindSelectedScenario):
                    continue

                sc_wind = antares_node.WindSelectedScenario[p.scenario - 1]

                if str(sc_wind) in antares_node.WindProduction.Index:
                    if antares_node.WindProduction.Abs().Max() > 0:
                        wind = atlas_output_marker.Equipment.Wind.CreateInstance("{}_w".format(antares_node.Name))

                        if p.consumption_production_separation:
                            wind.Portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                                "supplier_{}".format(antares_node.Name)
                            )
                        else:
                            wind.Portfolio = atlas_output_marker.MarketAgent.Portfolio.GetInstanceByName(
                                "portfolio_{}".format(antares_node.Name)
                            )

                        wind.Node = atlas_output_marker.Network.Node.GetInstanceByName(antares_node.Name)
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
