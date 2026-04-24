"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.study import Study
from loguru import logger

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def compute_initial_levels(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Compute and set the initial reservoir level for all hydraulic equipment.

    Two strategies depending on ReservoirManagement in Antares:
    - ReservoirManagement ON: use RemainingEnergyLevel from Antares (percentage * MaximumEnergy)
    - ReservoirManagement OFF: use a generic guide curve from a CSV file (percentage * MaximumEnergy)

    :param study: Antares study
    :param parameters: Conversion parameters
    :param atlas_dataset: Atlas dataset containing hydraulic equipment
    :return: Updated atlas_dataset
    """
    logger.info("Computing initial levels for hydraulic equipment")

    if len(atlas_dataset.hydro) == 0:
        logger.debug("No hydraulic equipment found, skipping initial level computation")
        return atlas_dataset

    if parameters.hydro.initialization_curve is None:
        logger.warning("No hydro initialization curve configured, skipping initial level computation")
        return atlas_dataset

    res_curve = _load_initialization_curve(parameters)

    areas = study.get_areas()

    for hydro in atlas_dataset.hydro:
        area_name = hydro.node.name if hydro.node else None
        if not area_name or area_name not in parameters.market_areas:
            continue

        if area_name not in areas:
            logger.warning(f"Area {area_name} not found in study for initial level computation")
            continue

        area = areas[area_name]
        reservoir_management = area.hydro.properties.reservoir

        if reservoir_management:
            # ReservoirManagement ON: use Antares RemainingEnergyLevel (in %)
            # TODO: area.hydro.get_reservoir() returns the reservoir guide curve, not the
            # per-MC-year RemainingEnergyLevel. Verify the correct antares-craft API to
            # retrieve the initial reservoir level for each MC year (legacy: RemainingEnergyLevel).
            logger.debug(f"Setting initial level from RemainingEnergyLevel for {hydro.name} (TODO: implement)")
        elif res_curve is not None and hydro.maximum_energy is not None:
            logger.debug(f"Setting initial level from guide curve for {hydro.name}")
            hydro.initial_level = res_curve * (hydro.maximum_energy.first_value() / 100.0)
        else:
            logger.warning(f"Could not set initial level for {hydro.name}: no guide curve or RemainingEnergyLevel")

    logger.info("Initial level computation done")
    return atlas_dataset


def _load_initialization_curve(parameters: AntaresToAtlasParameters) -> Timeseries | None:
    """Load the hydro initialization guide curve from CSV file.

    The CSV is a single-column file with hourly percentage values (0-100)
    representing the reservoir fill level over the time horizon.

    :return: Timeseries of reservoir fill percentages, or None if file not found
    """
    path = parameters.hydro.initialization_curve
    logger.debug(f"Loading hydro initialization curve from: {path}")

    try:
        with open(path) as f:
            lines_list = f.readlines()

        curve_values = [float(line.strip()) for line in lines_list if line.strip()]

        if not curve_values:
            logger.warning("Hydro initialization curve file is empty")
            return None

        res_curve = Timeseries.from_values(
            start_date=parameters.start_date,
            frequency="1h",
            values=curve_values,
        )

        logger.debug(f"Loaded hydro initialization curve: first={curve_values[0]}, last={curve_values[-1]}")
        return res_curve

    except Exception as e:
        logger.error(f"Error loading hydro initialization curve: {e}")
        return None
