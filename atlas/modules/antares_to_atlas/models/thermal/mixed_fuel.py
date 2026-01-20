import API


# Function adding the modulation part to FR nuclear equipments
def add_mixed_fuel(antares_dataset, atlas_dataset, thermic_parameter, thermic_properties, p):
    # Retrieve all Mixed Fuel thermal equipments
    for antares_thermal in antares_dataset.ThermalTechnology.GetAllInstances():
        if antares_thermal.Group != "Mixed_fuel":
            continue

        mkt_name = antares_thermal.Name.split("_")[0]
        # Apply the converter only on thermal clusters non excluded and belonging to the areas defined in market_areas_list
        if mkt_name in p.market_areas_list:
            # Waste technologies
            if "Waste" in antares_thermal.Name:
                sc = antares_thermal.ThermalSelectedScenario[p.scenario - 1]
                prod = antares_thermal.Disponibility[sc - 1]

                if prod.Abs().Max() > 0:
                    # Check if a Waste equipment already exists for this market_area
                    waste_equipment = atlas_dataset.Equipment.OtherNonDispatchable.GetInstanceByName(
                        f"{mkt_name}_Waste"
                    )

                    if not waste_equipment:
                        previous_power = 0

                        waste_equipment = atlas_dataset.Equipment.OtherNonDispatchable.CreateInstance(
                            f"{mkt_name}_Waste"
                        )

                        if p.consumption_production_separation:
                            atlas_portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(
                                f"generator_{mkt_name}"
                            )
                        else:
                            atlas_portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(
                                f"portfolio_{mkt_name}"
                            )

                        waste_equipment.Portfolio = atlas_portfolio
                        waste_equipment.Node = atlas_dataset.Network.Node.GetInstanceByName(str(mkt_name))

                    else:
                        previous_power = waste_equipment.Power[p.execution_date]

                    if not previous_power:
                        waste_equipment.MaximumPowerForecast.AddTimeSeries(p.execution_date, prod)
                    else:
                        new_power = previous_power + prod
                        waste_equipment.MaximumPowerForecast.DeleteTimeSeries(p.execution_date)
                        waste_equipment.MaximumPowerForecast.AddTimeSeries(p.execution_date, new_power)

                    continue

            # ------ Classic thermal technologies ------
            if "Coal" in antares_thermal.Name:
                techno = "Coal"
            if "coal" in antares_thermal.Name:
                techno = "Coal"
            if "Lignite" in antares_thermal.Name:
                techno = "Lignite"
            if "CCGT" in antares_thermal.Name:
                techno = "CCGT"
            if "OCGT" in antares_thermal.Name:
                techno = "OCGT"
            if "Oil" in antares_thermal.Name:
                techno = "Oil"
            if "oil" in antares_thermal.Name:
                techno = "Oil"

            if antares_thermal.NominalCapacity * antares_thermal.UnitCount == 0.0:
                continue

            equipment = atlas_dataset.Equipment.Thermic.CreateInstance(antares_thermal.Name)

            # FC: Following property previously set to True, corrected to False because
            # Thermic equipments have no value in MinimumDailyEnergy and MaximumDailyEnergy as of February 2022
            equipment.HasDailyEnergyConstraint = False

            node = atlas_dataset.Network.Node.GetInstanceByName(mkt_name)
            equipment.Node = node

            if p.consumption_production_separation:
                equipment.Portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(f"generator_{mkt_name}")
            else:
                equipment.Portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(f"portfolio_{mkt_name}")

            try:
                sc = antares_thermal.ThermalSelectedScenario[p.scenario - 1]
                equipment.MaximumPower = antares_thermal.Disponibility[sc - 1]
            except:
                equipment.MaximumPower = (
                    antares_thermal.NominalCapacity
                    * antares_thermal.UnitCount
                    * antares_thermal.CapacityModulation
                    * (1.0 - antares_thermal.FORate)
                    * (1.0 - antares_thermal.PORate)
                )

            equipment.MinimumPower = API.TimeSeries.NewTimeSeries(
                "MinPower",
                API.TimeSeries.Constant,
                p.start_date.ToString(),
                "1Y",
                2,
                float(antares_thermal.MinStablePower),
                "MW",
            )
            equipment.InstalledCapacity = antares_thermal.NominalCapacity * antares_thermal.UnitCount

            if antares_thermal.MarketBidCost > 0:
                equipment.VariableCost = float(antares_thermal.MarketBidCost) * antares_thermal.MarketBidModulation
            else:
                equipment.VariableCost = float(antares_thermal.MarginalCost) * antares_thermal.MarginalCostModulation

            equipment.StartupCost = API.TimeSeries.NewTimeSeries(
                "StartupCost",
                API.TimeSeries.Constant,
                p.start_date.ToString(),
                "1Y",
                2,
                float(antares_thermal.StartupCost),
                "MW",
            )

            # the unit of emissions is the same in Antares and Atlas
            equipment.CO2EmissionFactor = (
                float(antares_thermal.CO2) if antares_thermal.CO2 != 0.0 else p.co2_emission_factors[techno]
            )

            if antares_thermal.FODuration.IsEmpty:
                equipment.OutageMeanDuration = 0
            else:
                equipment.OutageMeanDuration = antares_thermal.FODuration.Average() * 24

            if antares_thermal.PODuration.IsEmpty:
                equipment.ScheduledShutdownMeanDuration = 0
            else:
                equipment.ScheduledShutdownMeanDuration = antares_thermal.PODuration.Average() * 24

            if antares_thermal.FORate.IsEmpty:
                equipment.OutageProbability = 0
            else:
                equipment.OutageProbability = antares_thermal.FORate.Average()

            if antares_thermal.PORate.IsEmpty:
                equipment.ScheduledShutdownProbability = 0
            else:
                equipment.ScheduledShutdownProbability = antares_thermal.PORate.Average()

            equipment.MinimumTimeOff = antares_thermal.MinDownTime
            equipment.MinimumTimeOn = antares_thermal.MinUpTime

            # Store properties indicated in the ThermicParameters csv
            for name in thermic_properties:
                if name == "MaximumGradient":
                    if name in thermic_parameter.keys():
                        if antares_thermal.Name in thermic_parameter[name].keys():
                            equipment.SetPropertyByName(
                                name, thermic_parameter[name][antares_thermal.Name] * antares_thermal.UnitCount
                            )
                        elif techno in thermic_parameter[name].keys():
                            equipment.SetPropertyByName(
                                name, thermic_parameter[name][techno] * antares_thermal.UnitCount
                            )
                else:
                    if name in thermic_parameter.keys():
                        if antares_thermal.Name in thermic_parameter[name].keys():
                            equipment.SetPropertyByName(name, thermic_parameter[name][antares_thermal.Name])
                        elif techno in thermic_parameter[name].keys():
                            equipment.SetPropertyByName(name, thermic_parameter[name][techno])
