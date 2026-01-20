import API


# Function adding the modulation part to FR nuclear equipments
def add_nuclear_modulation(antares_dataset, atlas_dataset, p):
    # Retrieve all nuclear equipments from area fr, and impose a DailyMaximumEnergy constraint
    # based on the binding constraint nuc_modulation_daily

    for equipment in atlas_dataset.Equipment.Thermic.GetAllInstances():
        # Filter only relevant equipments
        if "fr_" not in equipment.Name:
            continue

        if "Nuclear" not in equipment.Name:
            continue

        # Delete all "Nuclear_peak" instances
        if "Nuclear_peak" in equipment.Name:
            atlas_dataset.Equipment.Thermic.DeleteInstanceByName(equipment.Name)
            continue

        # Set HasDailyEnergyConstraint to True
        equipment.HasDailyEnergyConstraint = True

        # Load the binding constraint
        binding_constraint = antares_dataset.BindingConstraint.GetInstanceByName("nuc_modulation_daily")

        # Update MaximumDailyEnergy
        one_year_days_index = API.DatetimeIndex.NewIndex(p.start_date, p.start_date.AddYears(1).AddHours(-1), "1d")

        for time_index in one_year_days_index:
            day_index = API.DatetimeIndex.NewIndex(time_index, time_index.AddDays(1).AddHours(-1), "1h")
            one_day_energy = equipment.MaximumPower.Extract("", day_index)
            equipment.MaximumDailyEnergy[time_index] = round(one_day_energy.Sum() * abs(binding_constraint.Weights[5]))
