"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.st_storage import STStorage, STStorageGroup
from antares.craft.model.study import Study
from loguru import logger
from pendulum import duration

from atlas.enums import StorageType
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.models.storage._helpers import get_minimum_soc, get_power_bounds
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.modules.antares_to_atlas.utils import get_portfolio
from atlas.objects.equipment.storage import Storage


def convert_phs_closed_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Convert closed-loop PHS units from Antares st_storage to Atlas Storage equipment.

    :param study: Antares study object.
    :param parameters: Conversion parameters.
    :param atlas_dataset: Atlas dataset to populate.
    :return: Updated atlas dataset.
    """
    logger.info("Converting closed-loop PHS units")

    areas = study.get_areas()
    phs_list: list[Storage] = []

    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]

        for storage in area.get_st_storages().values():
            if storage.properties.group != STStorageGroup.PSP_CLOSED.value:
                continue

            phs = _create_closed_phs(
                storage=storage,
                area_id=area.id,
                study=study,
                parameters=parameters,
                atlas_dataset=atlas_dataset,
            )
            if phs is not None:
                phs_list.append(phs)
                logger.debug(f"Created closed PHS {storage.id} in area {area.id}")

    atlas_dataset.storage.add(phs_list)
    logger.info(f"Converted {len(phs_list)} closed PHS units")
    return atlas_dataset


def _create_closed_phs(
    storage: STStorage,
    area_id: str,
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> Storage | None:
    """Create a closed-loop PHS Storage equipment from an Antares st_storage unit.

    :param storage: Antares st_storage object.
    :param area_id: Area identifier.
    :param study: Antares study object.
    :param parameters: Conversion parameters.
    :param atlas_dataset: Atlas dataset for node/portfolio lookup.
    :return: Storage equipment, or None if it should be skipped.
    """
    props = storage.properties

    if props.reservoir_capacity == 0.0:
        logger.debug(f"Skipping closed PHS {storage.id} in {area_id}: zero reservoir capacity")
        return None

    scenario = (
        study.get_output(parameters.output_name)
        .get_st_storage_inflows_numbers(area_id, storage.id)
        .get(parameters.scenario, None)
    )

    maximum_injection_power_ts, maximum_withdrawal_power_ts = get_power_bounds(
        storage=storage, scenario=scenario, parameters=parameters
    )

    minimum_soc_ts = get_minimum_soc(storage=storage, scenario=scenario, parameters=parameters)

    return Storage(
        name=f"{area_id}_phs",
        node=atlas_dataset.get("node", area_id),
        portfolio=get_portfolio(atlas_dataset, parameters, area_id),
        storage_type=StorageType.PUMPED_HYDRAULIC_STORAGE,
        # In Antares: injection = power from grid to storage (charge), withdrawal = power from storage to grid (discharge)
        minimum_power=-maximum_injection_power_ts,
        maximum_power=maximum_withdrawal_power_ts,
        maximum_energy=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=props.reservoir_capacity,
        ),
        minimum_state_of_charge=minimum_soc_ts,
        charge_efficiency=props.efficiency,
        discharge_efficiency=1.0,
        storage_initial_level=parameters.storage.phs_initial_level,
        transition_duration=duration(hours=0),
    )
