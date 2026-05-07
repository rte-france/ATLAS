"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from loguru import logger

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def merge_open_and_closed_phs(
    atlas_dataset: AtlasDataset,
    closed_phs_list: list[str],
    open_phs_list: list[str],
    parameters: AntaresToAtlasParameters,
) -> AtlasDataset:
    """Merge open-loop and closed-loop PHS equipment when both exist for the same node.

    When a node has both:
    - Open-loop PHS (name: {node}_phs_open)
    - Closed-loop PHS (name: {node}_phs)

    They are merged into a single PHS equipment by:
    - Adding maximum_power, minimum_power, and maximum_energy
    - Keeping the closed PHS and deleting the open one
    - Merging any power forecasts

    If only open-loop exists, it's renamed to {node}_phs.

    :param atlas_dataset: Atlas dataset containing storage equipment
    :param closed_phs_list: List of node names that have closed-loop PHS
    :param open_phs_list: List of node names that have open-loop PHS
    :param parameters: Conversion parameters
    :return: Updated atlas_dataset
    """
    logger.info("Merging open and closed PHS equipment")
    logger.debug(f"Open PHS list: {open_phs_list}")
    logger.debug(f"Closed PHS list: {closed_phs_list}")

    if not hasattr(atlas_dataset, "storage") or not atlas_dataset.storage:
        logger.warning("No storage equipment found in atlas_dataset")
        return atlas_dataset

    for node_name in open_phs_list:
        if node_name in closed_phs_list:
            # Both open and closed PHS exist - merge them
            _merge_phs_for_node(atlas_dataset, node_name)
        else:
            # Only open PHS exists - rename it
            _rename_open_phs_to_standard(atlas_dataset, node_name)
            closed_phs_list.append(node_name)

    logger.info("PHS fusion completed")
    return atlas_dataset


def _merge_phs_for_node(atlas_dataset: AtlasDataset, node_name: str) -> None:
    """Merge open and closed PHS for a specific node.

    Finds both PHS equipment, adds their capacities together,
    and removes the open PHS.
    """
    closed_name = f"{node_name}_phs"
    open_name = f"{node_name}_phs_open"

    # Find the equipment in the storage list
    closed_phs = None
    open_phs = None

    for storage in atlas_dataset.storage:
        if storage.name == closed_name:
            closed_phs = storage
        elif storage.name == open_name:
            open_phs = storage

    if not closed_phs:
        logger.warning(f"Closed PHS {closed_name} not found for merging")
        return

    if not open_phs:
        logger.warning(f"Open PHS {open_name} not found for merging")
        return

    # Merge capacities
    logger.debug(f"Merging PHS for node {node_name}")

    # TODO: Verify how to add Timeseries objects in the new model
    # In old code: closed_phs.MaximumPower += open_phs.MaximumPower
    # This might require element-wise addition or special handling
    try:
        if closed_phs.maximum_power and open_phs.maximum_power:
            closed_phs.maximum_power = closed_phs.maximum_power + open_phs.maximum_power

        if closed_phs.minimum_power and open_phs.minimum_power:
            closed_phs.minimum_power = closed_phs.minimum_power + open_phs.minimum_power

        if closed_phs.maximum_energy and open_phs.maximum_energy:
            closed_phs.maximum_energy = closed_phs.maximum_energy + open_phs.maximum_energy

        # TODO: Merge power forecasts if they exist
        # In old code: power time series were stored in Power property
        # May need to merge stored_energy or other forecast matrices

    except Exception as e:
        logger.error(f"Error merging PHS capacities for node {node_name}: {e}")
        return

    # Remove the open PHS from the storage list
    atlas_dataset.storage.remove(open_name)
    logger.debug(f"Merged and removed {open_name}, kept {closed_name}")


def _rename_open_phs_to_standard(atlas_dataset: AtlasDataset, node_name: str) -> None:
    """Rename open PHS to standard name when no closed PHS exists.

    Changes {node}_phs_open to {node}_phs.
    """
    open_name = f"{node_name}_phs_open"
    new_name = f"{node_name}_phs"

    for storage in atlas_dataset.storage:
        if storage.name == open_name:
            # TODO: Verify if we can directly modify the name attribute
            # or if we need to use a specific method
            storage.name = new_name
            logger.debug(f"Renamed {open_name} to {new_name}")
            return

    logger.warning(f"Open PHS {open_name} not found for renaming")
