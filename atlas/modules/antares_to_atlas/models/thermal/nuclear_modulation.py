"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.study import Study
from loguru import logger

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.modules.antares_to_atlas.utils import get_nuclear_modulation_factor


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
    modulation_factor = get_nuclear_modulation_factor(study)

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
            maximum_daily_energy = equipment.maximum_power.groupby("1d", agg="sum", inplace=False)
            equipment.maximum_daily_energy = maximum_daily_energy * abs(modulation_factor)
        else:
            logger.warning(
                f"Could not set MaximumDailyEnergy for {equipment.name}: missing modulation factor or maximum power"
            )

    # Remove Nuclear_peak units
    for name in units_to_remove:
        atlas_dataset.thermal.remove(name)
    logger.debug(f"Removed {len(units_to_remove)} Nuclear_peak units: {units_to_remove}")

    logger.info("Nuclear modulation done")
    return atlas_dataset
