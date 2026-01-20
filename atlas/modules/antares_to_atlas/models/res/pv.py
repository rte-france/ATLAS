import API


def conversion_pv(antares_dataset, atlas_dataset, p):
    if antares_dataset.GeneralSettings.GetInstanceByName("Settings").RenewableGenerationModelling == "clusters":
        for instance in antares_dataset.Renewables.GetAllInstances():
            # Note that SolarThermal and SolarRooftop group are currently merged with SolarPV due to the lack of data for the forecasting model
            if instance.Group != "SolarPV":
                continue

            if not instance.Enabled:
                continue

            if instance.Node.Name in p.market_areas_list:
                # FC: Replacing the try except here, correct in theory but which is not working in ATLAS
                # for some reason (if the try fails, the code crashes without going into the except...)
                if p.scenario - 1 >= len(instance.RenewablesSelectedScenario):
                    continue

                sc_solar = instance.RenewablesSelectedScenario[p.scenario - 1]

                if str(sc_solar) in instance.Disponibility.Index:
                    if instance.Disponibility[sc_solar].Abs().Max() > 0:
                        pv = atlas_dataset.Equipment.Photovoltaic.CreateInstance(f"{instance.Node.Name}_pv")

                        if p.consumption_production_separation:
                            pv.Portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(
                                f"generator_{instance.Node.Name}"
                            )
                        else:
                            pv.Portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(
                                f"portfolio_{instance.Node.Name}"
                            )

                        pv.Node = atlas_dataset.Network.Node.GetInstanceByName(instance.Node.Name)
                        pv.MaximumCurtailmentRatio = API.TimeSeries.NewTimeSeries(
                            "MaximumCurtailmentRatio",
                            API.TimeSeries.Constant,
                            p.start_date.ToString(),
                            "1Y",
                            2,
                            p.pv_max_curtailment_ratio,
                            "",
                        )
                        pv.CurtailmentCost = API.TimeSeries.NewTimeSeries(
                            "CurtailmentCost",
                            API.TimeSeries.Constant,
                            p.start_date.ToString(),
                            "1Y",
                            2,
                            p.pv_curtailment_cost,
                            "",
                        )

                        pv.InstalledCapacity = instance.NominalCapacity
                        if antares_dataset.Renewables.CheckInstanceExists(instance.Node.Name + "_solar_thermo"):
                            thermo_instance = antares_dataset.Renewables.GetInstanceByName(
                                instance.Node.Name + "_solar_thermo"
                            )

                            if thermo_instance.Enabled:
                                pv.InstalledCapacity += thermo_instance.NominalCapacity

    else:
        for antares_node in antares_dataset.Node.GetAllInstances():
            if antares_node.Name in p.market_areas_list:
                # FC: Replacing the try except here, correct in theory but which is not working in ATLAS
                # for some reason (if the try fails, the code crashes without going into the except...)
                if p.scenario - 1 >= len(antares_node.SolarSelectedScenario):
                    continue

                sc_solar = antares_node.SolarSelectedScenario[p.scenario - 1]

                if str(sc_solar) in antares_node.SolarProduction.Index:
                    if antares_node.SolarProduction.Abs().Max() > 0:
                        pv = atlas_dataset.Equipment.Photovoltaic.CreateInstance(f"{antares_node.Name}_pv")

                        if p.consumption_production_separation:
                            pv.Portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(
                                f"supplier_{antares_node.Name}"
                            )
                        else:
                            pv.Portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(
                                f"portfolio_{antares_node.Name}"
                            )

                        pv.Node = atlas_dataset.Network.Node.GetInstanceByName(antares_node.Name)
                        pv.MaximumCurtailmentRatio = API.TimeSeries.NewTimeSeries(
                            "MaximumCurtailmentRatio",
                            API.TimeSeries.Constant,
                            p.start_date.ToString(),
                            "1Y",
                            2,
                            p.pv_max_curtailment_ratio,
                            "",
                        )

    return None
