import API
import functions

# First function :
# If there is a pcomp_mid in the node, we create a thermic group with caracteristics of CCG (=Gas in this study)

# Secund fonction :
# If there is a pcomp_peak in the node, we create a thermic group with caracteristics of TAC


def pcomp_mid(antares_dataset, atlas_dataset, p):
    # If there is a pcomp_mid in the node, we create a thermic group with caracteristics of CCG (=Gas in this study)

    for antares_node in antares_dataset.Node.GetAllInstances():
        if antares_node.Name in p.market_areas_list:
            thermal_node = f"{antares_node.Name}_{functions.node_special_format(antares_node.Name)}_Gas_pcomp_mid"
            antares_instance = antares_dataset.ThermalTechnology.GetInstanceByName(thermal_node)
            if antares_instance:
                # We create a thermic group with caracteristics of CCG (=Gas)
                if not antares_instance.Enabled or antares_instance.NominalCapacity * antares_instance.UnitCount == 0.0:
                    continue

                msg = f"Creating a thermic group named {thermal_node}"
                API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

                # Check if the unit already exists, possible in some specific Antares studies
                pcomp_mid_equipment = atlas_dataset.Equipment.Thermic.GetInstanceByName(thermal_node)

                if not pcomp_mid_equipment:
                    pcomp_mid_equipment = atlas_dataset.Equipment.Thermic.CreateInstance(thermal_node)

                # general properties of a group
                if p.consumption_production_separation:
                    portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(f"generator_{antares_node.Name}")
                else:
                    portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(f"portfolio_{antares_node.Name}")

                pcomp_mid_equipment.Node = atlas_dataset.Network.Node.GetInstanceByName(antares_node.Name)
                pcomp_mid_equipment.Portfolio = portfolio

                # special properties of a thermic group
                # CCG

                pcomp_mid_equipment.MinimumStablePowerDuration = 0.5
                pcomp_mid_equipment.StartupDelayProbability = 0.26
                pcomp_mid_equipment.StartupDuration = 1
                pcomp_mid_equipment.ShutdownDuration = 1
                pcomp_mid_equipment.MaximumGradient = 30 * antares_instance.UnitCount
                pcomp_mid_equipment.Strategy = "Intermediate"
                pcomp_mid_equipment.SetupDelay = 0

                try:
                    sc = antares_instance.ThermalSelectedScenario[p.scenario - 1]
                    pcomp_mid_equipment.MaximumPower = antares_instance.Disponibility[sc - 1]
                except:
                    pcomp_mid_equipment.MaximumPower = (
                        antares_instance.NominalCapacity
                        * antares_instance.UnitCount
                        * antares_instance.CapacityModulation
                        * (1.0 - antares_instance.FORate)
                        * (1.0 - antares_instance.PORate)
                    )

                pcomp_mid_equipment.MinimumPower = API.TimeSeries.NewTimeSeries(
                    "MinPower",
                    API.TimeSeries.Constant,
                    p.start_date.ToString(),
                    "1Y",
                    2,
                    float(antares_instance.MinStablePower),
                    "MW",
                )
                pcomp_mid_equipment.InstalledCapacity = antares_instance.NominalCapacity * antares_instance.UnitCount

                if antares_instance.MarketBidCost > 0:
                    pcomp_mid_equipment.VariableCost = (
                        float(antares_instance.MarketBidCost) * antares_instance.MarketBidModulation
                    )
                else:
                    pcomp_mid_equipment.VariableCost = (
                        float(antares_instance.MarginalCost) * antares_instance.MarginalCostModulation
                    )

                pcomp_mid_equipment.StartupCost = API.TimeSeries.NewTimeSeries(
                    "StartupCost",
                    API.TimeSeries.Constant,
                    p.start_date.ToString(),
                    "1Y",
                    2,
                    float(antares_instance.StartupCost * antares_instance.UnitCount),
                    "MW",
                )

                pcomp_mid_equipment.CO2EmissionFactor = (
                    float(antares_instance.CO2) if antares_instance.CO2 != 0.0 else p.co2_emission_factors["H2_CCG"]
                )

    return 0


def pcomp_peak(antares_dataset, atlas_dataset, p):
    # If there is a pcomp_mid in the node, we create a thermic group with caracteristics of CCG (=Gas in this study)

    for antares_node in antares_dataset.Node.GetAllInstances():
        if antares_node.Name in p.market_areas_list:
            thermal_node = f"{antares_node.Name}_{functions.node_special_format(antares_node.Name)}_Gas_pcomp_peak"
            antares_instance = antares_dataset.ThermalTechnology.GetInstanceByName(thermal_node)
            if antares_instance:
                # We create a thermic group with caracteristics of CCG (=Gas)
                if not antares_instance.Enabled or antares_instance.NominalCapacity * antares_instance.UnitCount == 0.0:
                    continue

                msg = f"Creating a thermic group named {thermal_node}"
                API.IO.Trace.Log(msg, API.IO.LogTypeInfo)

                # Check if the unit already exists, possible in some specific Antares studies
                pcomp_peak_equipment = atlas_dataset.Equipment.Thermic.GetInstanceByName(thermal_node)

                if not pcomp_peak_equipment:
                    pcomp_peak_equipment = atlas_dataset.Equipment.Thermic.CreateInstance(thermal_node)

                # general properties of a group
                if p.consumption_production_separation:
                    portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(f"generator_{antares_node.Name}")
                else:
                    portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(f"portfolio_{antares_node.Name}")

                pcomp_peak_equipment.Node = atlas_dataset.Network.Node.GetInstanceByName(antares_node.Name)
                pcomp_peak_equipment.Portfolio = portfolio

                # special properties of a thermic group
                # TAC

                pcomp_peak_equipment.MinimumStablePowerDuration = 0
                pcomp_peak_equipment.StartupDelayProbability = 0.26
                pcomp_peak_equipment.StartupDuration = 0.4
                pcomp_peak_equipment.ShutdownDuration = 0.4
                pcomp_peak_equipment.MaximumGradient = 30 * antares_instance.UnitCount
                pcomp_peak_equipment.Strategy = "Peak"
                pcomp_peak_equipment.SetupDelay = 0

                try:
                    sc = antares_instance.ThermalSelectedScenario[p.scenario - 1]
                    pcomp_peak_equipment.MaximumPower = antares_instance.Disponibility[sc - 1]
                except:
                    pcomp_peak_equipment.MaximumPower = (
                        antares_instance.NominalCapacity
                        * antares_instance.UnitCount
                        * antares_instance.CapacityModulation
                        * (1.0 - antares_instance.FORate)
                        * (1.0 - antares_instance.PORate)
                    )

                pcomp_peak_equipment.MinimumPower = API.TimeSeries.NewTimeSeries(
                    "MinPower",
                    API.TimeSeries.Constant,
                    p.start_date.ToString(),
                    "1Y",
                    2,
                    float(antares_instance.MinStablePower),
                    "MW",
                )
                pcomp_peak_equipment.InstalledCapacity = antares_instance.NominalCapacity * antares_instance.UnitCount

                if antares_instance.MarketBidCost > 0:
                    pcomp_peak_equipment.VariableCost = (
                        float(antares_instance.MarketBidCost) * antares_instance.MarketBidModulation
                    )
                else:
                    pcomp_peak_equipment.VariableCost = (
                        float(antares_instance.MarginalCost) * antares_instance.MarginalCostModulation
                    )

                pcomp_peak_equipment.StartupCost = API.TimeSeries.NewTimeSeries(
                    "StartupCost",
                    API.TimeSeries.Constant,
                    p.start_date.ToString(),
                    "1Y",
                    2,
                    float(antares_instance.StartupCost * antares_instance.UnitCount),
                    "MW",
                )

                pcomp_peak_equipment.CO2EmissionFactor = (
                    float(antares_instance.CO2) if antares_instance.CO2 != 0.0 else p.co2_emission_factors["H2_TAC"]
                )

    return 0
