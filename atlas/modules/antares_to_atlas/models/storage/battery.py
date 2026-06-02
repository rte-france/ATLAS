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

_SKIPPED_GROUPS = {STStorageGroup.PSP_OPEN.value, STStorageGroup.PSP_CLOSED.value, STStorageGroup.PONDAGE.value}


def convert_battery_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Convert short-term storage battery units from Antares to Atlas.

    Processes all st_storage units that are not PSP_OPEN, PSP_CLOSED, or PONDAGE,
    as those are handled by dedicated PHS converters.

    :param study: Antares study object.
    :param parameters: Conversion parameters.
    :param atlas_dataset: Atlas dataset to populate.
    :return: Updated atlas dataset.
    """
    logger.info("Converting battery units")

    areas = study.get_areas()
    battery_list: list[Storage] = []

    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]

        for storage in area.get_st_storages().values():
            if storage.properties.group in _SKIPPED_GROUPS:
                continue

            battery = _create_battery(
                storage=storage,
                area_id=area.id,
                study=study,
                parameters=parameters,
                atlas_dataset=atlas_dataset,
            )
            if battery is not None:
                battery_list.append(battery)
                logger.debug(f"Created battery unit {storage.id} in area {area.id}")

    atlas_dataset.storage.add(battery_list)
    logger.info(f"Converted {len(battery_list)} battery units")
    return atlas_dataset


def _create_battery(
    storage: STStorage,
    area_id: str,
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> Storage | None:
    """Create a Storage equipment from an Antares st_storage unit.

    :param storage: Antares st_storage object.
    :param area_id: Area identifier.
    :param study: Antares study object.
    :param parameters: Conversion parameters.
    :param atlas_dataset: Atlas dataset for node/portfolio lookup.
    :return: Storage equipment, or None if it should be skipped.
    """
    props = storage.properties

    if props.reservoir_capacity == 0.0:
        logger.debug(f"Skipping battery {storage.id} in {area_id}: zero reservoir capacity")
        return None

    try:
        scenario = (
            study.get_output(parameters.output_name)
            .get_st_storage_inflows_numbers(area_id, storage.id)
            .get(parameters.scenario, None)
        )
    except Exception:
        scenario = None

    maximum_injection_power_ts, maximum_withdrawal_power_ts = get_power_bounds(
        storage=storage,
        scenario=scenario,
        parameters=parameters,
    )

    minimum_soc_ts = get_minimum_soc(
        storage=storage,
        scenario=scenario,
        parameters=parameters,
    )

    end_date = parameters.start_date + duration(years=1)
    days_in_year = (end_date - parameters.start_date).days

    return Storage(
        name=storage.id,
        node=atlas_dataset.get("node", area_id),
        portfolio=get_portfolio(atlas_dataset, parameters, area_id),
        storage_type=StorageType.BATTERY,
        # In Antares: injection = power from grid to storage (charge), withdrawal = power from storage to grid (discharge)
        minimum_power=maximum_injection_power_ts * (-1),
        maximum_power=maximum_withdrawal_power_ts,
        maximum_energy=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency=f"{days_in_year}d",
            end_date=end_date,
            default_value=props.reservoir_capacity,
        ),
        minimum_state_of_charge=minimum_soc_ts,
        charge_efficiency=props.efficiency,
        discharge_efficiency=1.0,
        storage_initial_level=parameters.storage.battery_initial_level,
        transition_duration=duration(hours=0),
        additional_hours=duration(days=2),
        is_v2g=False,
        co2_emission_factor=0.0,
        has_daily_energy_constraint=False,
        maximum_afrr=0.0,
        maximum_fcr=0.0,
        maximum_gradient=0.0,
        setup_delay=0.0,
        unit_count=0,
    )
