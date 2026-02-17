"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.area import Area
from antares.craft.model.link import Link
from antares.craft.model.study import Study
from loguru import logger
from pendulum import duration

from atlas.enums import StorageType
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.storage import Storage
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def convert_battery_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Convert Battery technologies from Antares to Atlas Storage equipment.

    Batteries are modeled as Storage equipment with two variants:
    - Normal batteries (linked to z_batteries virtual node)
    - PCOMP batteries (linked to z_batteries_pcomp virtual node)

    When both exist for the same node, they are merged into a single battery.
    """
    logger.info("Converting Battery units")

    areas = study.get_areas()
    links = study.get_links()
    batteries: list[Storage] = []

    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]
        logger.debug(f"Processing battery units for area {area.id}")

        # Process normal battery
        normal_battery = _convert_normal_battery(
            area=area,
            study=study,
            parameters=parameters,
            atlas_dataset=atlas_dataset,
            links=links,
        )
        if normal_battery:
            batteries.append(normal_battery)

        pcomp_battery = _convert_pcomp_battery(
            area=area,
            study=study,
            links=links,
        )
        if pcomp_battery:
            batteries.append(pcomp_battery)

        # Merge if both exist
        if normal_battery and pcomp_battery:
            logger.debug(f"Merging normal and pcomp batteries for area {area.id}")
            _merge_batteries(normal_battery, pcomp_battery, parameters)
            batteries.remove(pcomp_battery)

    atlas_dataset.storage.add(batteries)

    return atlas_dataset


def _convert_normal_battery(
    area: Area,
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    links: dict[str, Link],
) -> Storage | None:
    """Convert normal battery unit."""
    link_name = f"{area.id}_z_batteries"

    link = None
    for link_id, link_obj in links.items():
        if link_name.lower() in link_id.lower():
            link = link_obj
            break

    if not link:
        return None

    # Get binding constraint for efficiency values
    binding_constraints = study.get_binding_constraints()
    binding_constraint_name = f"batteries_{area.id}"
    binding_constraint = None
    for bc_id, bc_obj in binding_constraints.items():
        if binding_constraint_name.lower() in bc_id.lower():
            binding_constraint = bc_obj
            break

    if not binding_constraint:
        logger.warning(f"Binding constraint {binding_constraint_name} not found for battery in area {area.id}")

    # Get maximum power and power discharge data
    # TODO: Verify how to access thermal cluster data for batteries_inj
    # In old code: ThermalTechnology.GetInstanceByName(f"{area.id}_{node_special_format}_batteries_inj")
    try:
        # TODO: Need to access thermal clusters to get batteries_inj data
        # This requires accessing the area's thermal clusters
        thermals = area.get_thermals()
        batteries_inj_thermal = None
        for thermal_key, thermal_obj in thermals.items():
            if "batteries_inj" in thermal_key.lower():
                batteries_inj_thermal = thermal_obj
                break

        if not batteries_inj_thermal:
            return None

        # TODO: Verify how to get Disponibility and CalculatedPower time series
        # In old code: thermal.Disponibility[str(p.scenario)] and thermal.CalculatedPower[str(p.scenario)]
        maximum_power_df = batteries_inj_thermal.series  # TODO: Get correct time series
        power_discharge_df = batteries_inj_thermal.series  # TODO: Get correct time series

        if maximum_power_df.abs().max().max() == 0:
            return None

        maximum_power_ts = Timeseries(maximum_power_df)
        power_discharge_ts = Timeseries(power_discharge_df) if power_discharge_df is not None else None

    except Exception as e:
        logger.warning(f"Could not get thermal data for batteries_inj in area {area.id}: {e}")
        return None

    # Get MaximumEnergy from stock thermal technology
    # TODO: Verify how to access thermal cluster for stock_1
    # In old code: ThermalTechnology.GetInstanceByName(f"z_batteries_batteries_{node_special_format}_1")
    try:
        # TODO: Need to access z_batteries area thermal clusters
        areas_dict = study.get_areas()
        if "z_batteries" not in areas_dict:
            return None

        z_batteries_thermals = areas_dict["z_batteries"].get_thermals()
        stock_thermal = None
        for thermal_key, thermal_obj in z_batteries_thermals.items():
            if area.id.lower() in thermal_key.lower() and "_1" in thermal_key:
                stock_thermal = thermal_obj
                break

        if not stock_thermal:
            return None

        # TODO: Verify how to get Disponibility time series
        maximum_energy_df = stock_thermal.series  # TODO: Get correct time series
        maximum_energy_ts = Timeseries(maximum_energy_df)

    except Exception as e:
        logger.warning(f"Could not get stock data for battery in area {area.id}: {e}")
        return None

    # Get efficiencies from binding constraint
    charge_efficiency = 1.0
    discharge_efficiency = 1.0
    if binding_constraint:
        # TODO: Verify how to access Weights from binding constraint
        # In old code: binding_constraint.Weights[0] and binding_constraint.Weights[1]
        try:
            terms = binding_constraint.get_terms()
            # TODO: The weights structure might be different in new API
            # May need to extract weights from terms
            charge_efficiency = 1.0  # TODO: Extract from binding constraint
            discharge_efficiency = 1.0  # TODO: Extract from binding constraint
        except Exception as e:
            logger.warning(f"Could not get efficiency values from binding constraint: {e}")

    # Get transit data for power calculation
    try:
        # TODO: Verify how to get CalculatedTransit time series
        # In old code: link.CalculatedTransit[str(p.scenario)]
        power_charge_df = link.get_capacity_direct()  # TODO: Get correct transit data
        power_charge_ts = Timeseries(power_charge_df * -1.0)

        if power_discharge_ts is None:
            power_discharge_ts = Timeseries.from_index(
                start_date=parameters.start_date,
                frequency="1h",
                end_date=parameters.start_date + duration(years=1),
                default_value=0.0,
            )

        power_ts = power_discharge_ts + power_charge_ts

    except Exception as e:
        logger.warning(f"Could not calculate power for battery in area {area.id}: {e}")
        return None

    # Get minimum power from link capacity
    try:
        # TODO: Verify how to get DirectTransferCapacity time series
        minimum_power_df = link.get_capacity_direct()
        minimum_power_value = float(minimum_power_df.abs().max().max())
        minimum_power_ts = Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=-minimum_power_value,
        )
    except Exception as e:
        logger.warning(f"Could not get minimum power for battery in area {area.id}: {e}")
        minimum_power_ts = Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=0.0,
        )

    # Create battery equipment
    battery = Storage(
        name=f"{area.id}_battery",
        node=atlas_dataset.get("node", area.id),
        portfolio=atlas_dataset.get(
            "portfolio",
            f"generator_{area.id}" if parameters.consumption_production_separation else f"portfolio_{area.id}",
        ),
        storage_type=StorageType.BATTERY,
        maximum_power=maximum_power_ts,
        minimum_power=minimum_power_ts,
        maximum_energy=maximum_energy_ts,
        minimum_state_of_charge=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=0.0,
        ),
        charge_efficiency=charge_efficiency,
        discharge_efficiency=discharge_efficiency,
        storage_initial_level=parameters.battery_initial_level,
        # TODO: unit_count=1,  # To be refined when battery unit counts are indicated in Antares
    )

    # Add power forecast
    # TODO: Verify if power should be added as a forecast matrix
    # battery.power.add(parameters.execution_date, power_ts)

    logger.debug(f"Created normal battery for area: {area.id}")
    return battery


def _convert_pcomp_battery(
    area: Area,
    study: Study,
    links: dict[str, Link],
) -> Storage | None:
    """Convert PCOMP battery unit."""
    link_name = f"{area.id}_z_batteries_pcomp"

    # TODO: Verify if links are indexed by name or by ID
    link = None
    for link_id, link_obj in links.items():
        if link_name.lower() in link_id.lower():
            link = link_obj
            break

    if not link:
        return None

    # Get binding constraint
    binding_constraints = study.get_binding_constraints()
    binding_constraint_name = f"batteries_pcomp_{area.id}"
    binding_constraint = None
    for bc_id, bc_obj in binding_constraints.items():
        if binding_constraint_name.lower() in bc_id.lower():
            binding_constraint = bc_obj
            break

    if not binding_constraint:
        logger.warning(f"Binding constraint {binding_constraint_name} not found for PCOMP battery in area {area.id}")

    # TODO: Similar implementation as normal battery
    # This would follow the same pattern as _convert_normal_battery
    # with different link and thermal technology names
    logger.debug(f"TODO: Implement PCOMP battery conversion for area {area.id}")
    return None


def _merge_batteries(normal_battery: Storage, pcomp_battery: Storage, parameters: AntaresToAtlasParameters) -> None:
    """Merge normal and PCOMP batteries into a single battery.

    Merges capacities and calculates weighted average efficiencies.
    """
    # TODO: Implement battery merging logic
    # - Add maximum_power, minimum_power, maximum_energy
    # - Calculate weighted average for charge_efficiency and discharge_efficiency
    # - Merge power time series
    logger.debug("TODO: Implement battery merging logic")
    pass
