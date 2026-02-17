"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.study import Study
from loguru import logger

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def add_nuclear_modulation(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Add daily energy modulation constraints to French nuclear thermal units.

    For all FR nuclear units (excluding "Nuclear_peak"):
    - Removes "Nuclear_peak" units entirely
    - Sets has_daily_energy_constraint = True
    - Computes MaximumDailyEnergy per day as:
        sum(MaximumPower over 24h) * abs(nuc_modulation_daily binding constraint weight[5])

    The binding constraint "nuc_modulation_daily" weight[5] acts as a modulation
    factor to cap daily nuclear production below its theoretical maximum.
    """
    logger.info("Adding nuclear modulation to FR nuclear units")

    if not hasattr(atlas_dataset, "thermal") or not atlas_dataset.thermal:
        logger.debug("No thermal equipment found, skipping nuclear modulation")
        return atlas_dataset

    # Get the modulation factor from binding constraint
    modulation_factor = _get_nuclear_modulation_factor(study)

    # Process FR nuclear units
    units_to_remove: list[str] = []

    for equipment in atlas_dataset.thermal:
        if "fr_" not in equipment.name.lower():
            continue

        if "nuclear" not in equipment.name.lower():
            continue

        # Remove Nuclear_peak units
        if "nuclear_peak" in equipment.name.lower():
            units_to_remove.append(equipment.name)
            logger.debug(f"Marking {equipment.name} for removal (Nuclear_peak)")
            continue

        # Enable daily energy constraint
        equipment.has_daily_energy_constraint = True

        # Compute MaximumDailyEnergy per day
        if modulation_factor is not None and equipment.maximum_power is not None:
            _set_maximum_daily_energy(equipment, modulation_factor, parameters)
        else:
            logger.warning(
                f"Could not set MaximumDailyEnergy for {equipment.name}: missing modulation factor or maximum power"
            )

    # Remove Nuclear_peak units
    atlas_dataset.thermal = [t for t in atlas_dataset.thermal if t.name not in units_to_remove]
    logger.debug(f"Removed {len(units_to_remove)} Nuclear_peak units: {units_to_remove}")

    logger.info("Nuclear modulation done")
    return atlas_dataset


def _get_nuclear_modulation_factor(study: Study) -> float | None:
    """Get nuclear modulation factor from binding constraint 'nuc_modulation_daily'.

    Returns abs(weights[5]) of the binding constraint, or None if not found.
    """
    try:
        binding_constraints = study.get_binding_constraints()

        for bc_id, bc_obj in binding_constraints.items():
            if "nuc_modulation_daily" in bc_id.lower():
                # TODO: Verify how to get weights from binding constraint
                # In old code: binding_constraint.Weights[5]
                # May need to access terms or coefficients
                terms = bc_obj.get_terms()
                # TODO: Extract weight at index 5 from terms
                # factor = abs(terms[5].weight) or similar
                logger.debug("TODO: Extract weight[5] from nuc_modulation_daily binding constraint")
                return None  # TODO: return abs(weight)

        logger.warning("Binding constraint 'nuc_modulation_daily' not found")
        return None

    except Exception as e:
        logger.error(f"Error getting nuclear modulation factor: {e}")
        return None


def _set_maximum_daily_energy(equipment, modulation_factor: float, parameters: AntaresToAtlasParameters) -> None:
    """Set MaximumDailyEnergy for each day of the year.

    For each day: MaximumDailyEnergy = round(sum(MaximumPower over 24h) * modulation_factor)
    """
    # TODO: Implement daily energy computation
    # In old code:
    #   one_year_days_index = API.DatetimeIndex.NewIndex(p.start_date, p.start_date.AddYears(1).AddHours(-1), "1d")
    #   for time_index in one_year_days_index:
    #       day_index = API.DatetimeIndex.NewIndex(time_index, time_index.AddDays(1).AddHours(-1), "1h")
    #       one_day_energy = equipment.MaximumPower.Extract("", day_index)
    #       equipment.MaximumDailyEnergy[time_index] = round(one_day_energy.Sum() * modulation_factor)
    #
    # This requires:
    # - Iterating over daily timestamps for the year
    # - Slicing maximum_power for each 24h window
    # - Computing the sum and multiplying by modulation_factor
    # - Setting maximum_daily_energy at each daily timestamp
    logger.debug(f"TODO: Compute and set MaximumDailyEnergy for {equipment.name} with factor {modulation_factor}")
