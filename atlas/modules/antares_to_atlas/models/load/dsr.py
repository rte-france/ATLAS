import API
import functions

# Description of the script:
# dsr_fr manages the exception of FR due the name of FR nodes, dsr_other_countries for all other nodes
# First, we create the thermic group DSR.
# Then, we assign to the output marker: MaximumDailyEnergy and MaximumPower.
# HasDailyEnergyConstraint is always set to True.


def dsr_fr(antares_dataset, atlas_dataset, p):
    # Retrieve the information from BindingConstraints in the Antares input marker
    time_series_dsr_indus = antares_dataset.BindingConstraint.GetInstanceByName("fr_dsr_industrie_stock").LessThan
    time_series_dsr_tert = antares_dataset.BindingConstraint.GetInstanceByName("fr_dsr_tertiaire_stock").LessThan

    # Now in ATLAS
    # We create equipment for indus and tert as Thermal equipments
    dsr_fr_indus_equipment = atlas_dataset.Equipment.Thermic.CreateInstance("fr_dsr_indus")
    dsr_fr_tert_equipment = atlas_dataset.Equipment.Thermic.CreateInstance("fr_dsr_tert")
    dsr_fr_implicite_equipment = atlas_dataset.Equipment.Thermic.CreateInstance("fr_dsr_implicite")

    # General properties of each unit
    if p.consumption_production_separation:
        portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName("generator_fr")
    else:
        portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName("portfolio_fr")

    dsr_fr_indus_equipment.Node = atlas_dataset.Network.Node.GetInstanceByName("fr")
    dsr_fr_tert_equipment.Node = atlas_dataset.Network.Node.GetInstanceByName("fr")
    dsr_fr_implicite_equipment.Node = atlas_dataset.Network.Node.GetInstanceByName("fr")

    dsr_fr_indus_equipment.Portfolio = portfolio
    dsr_fr_tert_equipment.Portfolio = portfolio
    dsr_fr_implicite_equipment.Portfolio = portfolio

    # MaximumDailyEnergy is directly extracted from the binding constraint
    dsr_fr_indus_equipment.MaximumDailyEnergy = time_series_dsr_indus
    dsr_fr_tert_equipment.MaximumDailyEnergy = time_series_dsr_tert

    # HasDailyEnergyConstraint is always set to True
    dsr_fr_indus_equipment.HasDailyEnergyConstraint = True
    dsr_fr_tert_equipment.HasDailyEnergyConstraint = True
    dsr_fr_implicite_equipment.HasDailyEnergyConstraint = False

    dsr_fr_indus_equipment.Strategy = "Peak"
    dsr_fr_tert_equipment.Strategy = "Peak"
    dsr_fr_implicite_equipment.Strategy = "Peak"

    # MaximumPower is extracted from the Disponibility information in the ThermalTechnology of the Antares marker
    # NB: currently, all Disponibility timeseries are identical for DSR equipments. The p.scenario is taken arbitrarily,
    # this assumption may need to be reevaluated if the DSR modeling is improved in Antares
    dsr_indus_instance_antares = antares_dataset.ThermalTechnology.GetInstanceByName("fr_FR_DSR_industrie")
    dsr_tert_instance_antares = antares_dataset.ThermalTechnology.GetInstanceByName("fr_FR_DSR_tertiaire")
    dsr_implicite_instance_antares = antares_dataset.ThermalTechnology.GetInstanceByName("fr_FR_DSR_implicite")

    dsr_fr_indus_equipment.MaximumPower = dsr_indus_instance_antares.Disponibility[str(p.scenario)]
    dsr_fr_tert_equipment.MaximumPower = dsr_tert_instance_antares.Disponibility[str(p.scenario)]
    dsr_fr_implicite_equipment.MaximumPower = dsr_implicite_instance_antares.Disponibility[str(p.scenario)]

    # VariableCost
    cost_index = API.DatetimeIndex.NewIndex(p.start_date, p.start_date.AddYears(1), 2)

    dsr_fr_indus_equipment.VariableCost = API.TimeSeries.NewTimeSeries(
        "VariableCost", API.TimeSeries.Constant, "", cost_index, dsr_indus_instance_antares.MarginalCost
    )
    dsr_fr_tert_equipment.VariableCost = API.TimeSeries.NewTimeSeries(
        "VariableCost", API.TimeSeries.Constant, "", cost_index, dsr_tert_instance_antares.MarginalCost
    )
    dsr_fr_implicite_equipment.VariableCost = API.TimeSeries.NewTimeSeries(
        "VariableCost", API.TimeSeries.Constant, "", cost_index, dsr_implicite_instance_antares.MarginalCost
    )

    return 0


def dsr_other_countries(antares_dataset, atlas_dataset, p):
    # Loop on nodes in the Antares marker
    for node in antares_dataset.Node.GetAllInstances():
        if node.Name not in p.market_areas_list:
            continue

        # Loop on BindingConstraints and retain only those matching the current node
        for bc in antares_dataset.BindingConstraint.GetAllInstances():
            dsr_node = f"dsr_{node.Name}_stock"

            if bc.Name == dsr_node:
                # We take the time series "less than" related to our antares binding constraint
                bc_dsr = bc.LessThan

                # We take the TS Disponbility from input marker to have the MaximumPower of the output marker
                # Retrieve the thermal techno name
                thermal_name = f"{node.Name}_{functions.node_special_format(node.Name)}_DSR_0"

                # Retrieve the Antares ThermalTechnology
                dsr_instance_antares = antares_dataset.ThermalTechnology.GetInstanceByName(thermal_name)

                if not dsr_instance_antares:
                    API.IO.Trace.Log(f"No instance : {thermal_name}", API.IO.LogType.Warn)

                # We create a thermic group in ATLAS (only for non empty Antares instances)
                if dsr_instance_antares.Disponibility[str(p.scenario)].Abs().Max() == 0.0:
                    continue
                dsr_equipment = atlas_dataset.Equipment.Thermic.CreateInstance(f"{node.Name}_dsr")

                # General properties of a group
                if p.consumption_production_separation:
                    portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(f"generator_{node.Name}")
                else:
                    portfolio = atlas_dataset.MarketAgent.Portfolio.GetInstanceByName(f"portfolio_{node.Name}")

                dsr_equipment.Node = atlas_dataset.Network.Node.GetInstanceByName(node.Name)
                dsr_equipment.Portfolio = portfolio

                # Special properties of dsr
                dsr_equipment.MaximumDailyEnergy = bc_dsr

                # HasDailyEnergyConstraint is always set to True
                dsr_equipment.HasDailyEnergyConstraint = True

                dsr_equipment.Strategy = "Peak"

                dsr_equipment.MaximumPower = dsr_instance_antares.Disponibility[str(p.scenario)]

                # VariableCost
                cost_index = API.DatetimeIndex.NewIndex(p.start_date, p.start_date.AddYears(1), 2)

                dsr_equipment.VariableCost = API.TimeSeries.NewTimeSeries(
                    "VariableCost", API.TimeSeries.Constant, "", cost_index, dsr_instance_antares.MarginalCost
                )

    return 0
