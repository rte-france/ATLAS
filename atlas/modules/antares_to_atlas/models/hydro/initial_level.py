"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.study import Study
from loguru import logger
from pendulum import duration

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

    # Load the guide curve from CSV (used when ReservoirManagement is OFF)
    res_curve = _load_initialization_curve(parameters)

    areas = study.get_areas()

    for hydro in atlas_dataset.hydro:
        area_name = hydro.node.name if hydro.node else None
        if not area_name or area_name not in parameters.market_areas:
            continue

        if area_name not in areas:
            logger.warning(f"Area {area_name} not found in study for initial level computation")
            continue

        # TODO: Verify how to access HydroReservoir.ReservoirManagement from area
        # area = areas[area_name]
        # In old code: antares_node.HydroReservoir.ReservoirManagement
        # and: antares_node.HydroReservoir.RemainingEnergyLevel
        reservoir_management = False  # TODO: Get from area hydro reservoir
        remaining_energy_level_ts = None  # TODO: Get from area hydro reservoir

        if reservoir_management and remaining_energy_level_ts is not None:
            # ReservoirManagement ON: use Antares RemainingEnergyLevel (in %)
            # initial_level = (1/100) * remaining_energy_level * maximum_energy
            logger.debug(f"Setting initial level from RemainingEnergyLevel for {hydro.name}")

            # TODO: Compute initial_level from remaining_energy_level_ts and hydro.maximum_energy
            # In old code:
            #   instance.InitialLevel = 1/100.0 * remaining_energy_level_ts * instance.MaximumEnergy
            hydro.initial_level = None

        elif res_curve is not None and hydro.maximum_energy is not None:
            # ReservoirManagement OFF: use guide curve from CSV (in %)
            # initial_level = (1/100) * res_curve * maximum_energy
            logger.debug(f"Setting initial level from guide curve for {hydro.name}")

            # TODO: Compute initial_level from res_curve and hydro.maximum_energy
            # In old code:
            #   instance.InitialLevel = 1/100.0 * res_curve * instance.MaximumEnergy
            hydro.initial_level = None

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

    if parameters.hydro.initialization_curve.is_file():
        logger.warning(f"Hydro initialization curve file not found: {parameters.hydro.initialization_curve}")
        return None

    logger.debug(f"Loading hydro initialization curve from: {parameters.hydro.initialization_curve}")

    try:
        with open(parameters.hydro.initialization_curve) as f:
            lines_list = f.readlines()

        curve_values = [float(line.strip()) for line in lines_list if line.strip()]

        if not curve_values:
            logger.warning("Hydro initialization curve file is empty")
            return None

        # Build a timeseries from the hourly values
        # The curve spans the start_date to start_date + len(curve_values) hours
        res_curve = Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(hours=len(curve_values) - 1),
            default_value=0.0,
        )

        # TODO: Set individual values from curve_values
        # In old code: creates a TimeSeries with the list of values directly
        # Need to verify how to populate a Timeseries from a list of values

        logger.debug(f"Loaded hydro initialization curve: first={curve_values[0]}, last={curve_values[-1]}")
        return res_curve

    except Exception as e:
        logger.error(f"Error loading hydro initialization curve: {e}")
        return None
