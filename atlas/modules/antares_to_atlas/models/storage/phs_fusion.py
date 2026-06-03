"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from loguru import logger

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def merge_open_and_closed_phs(
    atlas_dataset: AtlasDataset,
    closed_phs_list: list[str],
    open_phs_list: list[str],
    parameters: AntaresToAtlasParameters,
) -> AtlasDataset:
    """Merge open-loop and closed-loop PHS equipment when both exist for the same node.

    When a node has both:
    - Open-loop PHS (name: {node}_step_open)
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

    for node_name in open_phs_list:
        if node_name in closed_phs_list:
            _merge_phs_for_node(atlas_dataset, node_name, parameters)
        else:
            _rename_open_phs_to_standard(atlas_dataset, node_name)
            closed_phs_list.append(node_name)

    logger.info("PHS fusion completed")
    return atlas_dataset


def _merge_phs_for_node(atlas_dataset: AtlasDataset, node_name: str, parameters: AntaresToAtlasParameters) -> None:
    """Merge open and closed PHS for a specific node.

    Finds both PHS equipment, adds their capacities together,
    and removes the open PHS.
    """
    closed_name = f"{node_name}_step_closed"
    open_name = f"{node_name}_step_open"

    try:
        closed_phs = atlas_dataset.storage.get(closed_name)
    except KeyError:
        logger.warning(f"Closed PHS {closed_name} not found for merging")
        return

    try:
        open_phs = atlas_dataset.storage.get(open_name)
    except KeyError:
        logger.warning(f"Open PHS {open_name} not found for merging")
        return

    logger.debug(f"Merging PHS for node {node_name}")

    try:
        if closed_phs.maximum_power is not None and open_phs.maximum_power is not None:
            closed_phs.maximum_power += open_phs.maximum_power

        if closed_phs.minimum_power is not None and open_phs.minimum_power is not None:
            closed_phs.minimum_power += open_phs.minimum_power

        if closed_phs.maximum_energy is not None and open_phs.maximum_energy is not None:
            closed_phs.maximum_energy += open_phs.maximum_energy

        if isinstance(open_phs.power, ForecastingMatrix):
            exec_key = parameters.execution_date.format(open_phs.power.date_format)
            open_ts = open_phs.power[exec_key]
            if isinstance(closed_phs.power, ForecastingMatrix) and exec_key in closed_phs.power.indexes:
                closed_ts = closed_phs.power[exec_key]
                closed_phs.power.replace(parameters.execution_date, closed_ts + open_ts)
            elif isinstance(closed_phs.power, ForecastingMatrix):
                closed_phs.power.add(open_ts, parameters.execution_date)
            else:
                closed_phs.power = open_phs.power

    except Exception as e:
        logger.error(f"Error merging PHS capacities for node {node_name}: {e}")
        return

    atlas_dataset.storage.remove(open_name)
    logger.debug(f"Merged and removed {open_name}, kept {closed_name}")


def _rename_open_phs_to_standard(atlas_dataset: AtlasDataset, node_name: str) -> None:
    """Rename open PHS to standard name when no closed PHS exists.

    Changes {node}_step_open to {node}_phs.
    """
    open_name = f"{node_name}_step_open"
    new_name = f"{node_name}_step_closed"

    try:
        storage = atlas_dataset.storage.get(open_name)
    except KeyError:
        logger.warning(f"Open PHS {open_name} not found for renaming")
        return

    atlas_dataset.storage.remove(open_name)
    storage.name = new_name
    atlas_dataset.storage.add(storage)
    logger.debug(f"Renamed {open_name} to {new_name}")
