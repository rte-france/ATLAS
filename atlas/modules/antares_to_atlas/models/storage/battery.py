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
from atlas.math.forecasting_matrix import ForecastingMatrix
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

        pcomp_battery = _convert_pcomp_battery(
            area=area,
            study=study,
            parameters=parameters,
            atlas_dataset=atlas_dataset,
            links=links,
        )

        # Merge if both exist
        if normal_battery and pcomp_battery:
            logger.debug(f"Merging normal and pcomp batteries for area {area.id}")
            _merge_batteries(normal_battery, pcomp_battery, parameters)

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

    link = links.get(f"{area.id}_z_batteries", None)

    if not link:
        return None

    binding_constraints = study.get_binding_constraints()
    binding_constraint = binding_constraints.get(f"batteries_{area.id}", None)

    if binding_constraint:
        thermals = area.get_thermals()
        areas = study.get_areas()
        batteries_inj_thermal = thermals.get("batteries_inj", None)

        if not batteries_inj_thermal:
            return None

        maximum_power_df = batteries_inj_thermal.get_series_matrix()[parameters.scenario]  # TODO: Get dispo
        power_discharge_df = batteries_inj_thermal.get_series_matrix()[parameters.scenario]  # TODO: Get dispo

        if maximum_power_df.abs().max().max() == 0:
            return None

        maximum_power_ts = Timeseries(maximum_power_df)
        power_discharge_ts = Timeseries(power_discharge_df)

        z_batteries_thermals = areas["z_batteries"].get_thermals()
        stock_thermal = z_batteries_thermals.get(f"z_batteries_batteries_{area.id}_1", None)
        maximum_energy_df = stock_thermal.get_series_matrix()[parameters.scenario]  # TODO: Get Disponibility
        maximum_energy_ts = Timeseries(maximum_energy_df)

        # In old code: binding_constraint.Weights[0] and binding_constraint.Weights[1]
        # TODO: Extract efficiencies from binding constraint terms = binding_constraint.get_terms()
        charge_efficiency = 1.0
        discharge_efficiency = 1.0

        # In old code: link.CalculatedTransit[str(p.scenario)]
        power_charge_df = link.get_capacity_direct()[parameters.scenario]  # TODO: Get correct transit data
        power_charge_ts = Timeseries(power_charge_df * -1.0)

        if power_discharge_ts is None:
            power_discharge_ts = Timeseries.from_index(
                start_date=parameters.start_date,
                frequency="1h",
                end_date=parameters.start_date + duration(years=1),
                default_value=0.0,
            )

        power_ts = power_discharge_ts + power_charge_ts

        # TODO: Verify how to get DirectTransferCapacity time series
        minimum_power_df = link.get_capacity_direct()[parameters.scenario]
        minimum_power_value = float(minimum_power_df.abs().max().max())
        minimum_power_ts = Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=-minimum_power_value,
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
        unit_count=1,
        power=ForecastingMatrix().add(power_ts, parameters.execution_date),
    )

    logger.debug(f"Created normal battery for area: {area.id}")
    return battery


def _convert_pcomp_battery(
    area: Area,
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    links: dict[str, Link],
) -> Storage | None:
    """Convert PCOMP battery unit."""

    link = links.get(f"{area.id}_z_batteries_pcomp", None)

    if not link:
        return None

    binding_constraints = study.get_binding_constraints()
    binding_constraint = binding_constraints.get(f"batteries_pcomp_{area.id}", None)

    if binding_constraint:
        thermals = area.get_thermals()
        areas = study.get_areas()
        batteries_inj_thermal = thermals.get("batteries_pcomp_inj", None)

        if not batteries_inj_thermal:
            return None

        maximum_power_df = batteries_inj_thermal.get_series_matrix()[parameters.scenario]  # TODO: Get dispo
        power_discharge_df = batteries_inj_thermal.get_series_matrix()[parameters.scenario]  # TODO: Get dispo

        if maximum_power_df.abs().max().max() == 0:
            return None

        maximum_power_ts = Timeseries(maximum_power_df)
        power_discharge_ts = Timeseries(power_discharge_df)

        z_batteries_thermals = areas["z_batteries_pcomp"].get_thermals()
        stock_thermal = z_batteries_thermals.get(f"z_batteries_pcomp_batteries_pcomp_{area.id}_1", None)
        maximum_energy_df = stock_thermal.get_series_matrix()[parameters.scenario]  # TODO: Get Disponibility
        maximum_energy_ts = Timeseries(maximum_energy_df)

        # TODO: Extract efficiencies from binding constraint terms
        charge_efficiency = 1.0
        discharge_efficiency = 1.0

        power_charge_df = link.get_capacity_direct()[parameters.scenario]  # TODO: Get correct transit data
        power_charge_ts = Timeseries(power_charge_df * -1.0)

        if power_discharge_ts is None:
            power_discharge_ts = Timeseries.from_index(
                start_date=parameters.start_date,
                frequency="1h",
                end_date=parameters.start_date + duration(years=1),
                default_value=0.0,
            )

        power_ts = power_discharge_ts + power_charge_ts

        minimum_power_df = link.get_capacity_direct()[parameters.scenario]
        minimum_power_value = float(minimum_power_df.abs().max().max())
        minimum_power_ts = Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=-minimum_power_value,
        )

    # Create battery equipment
    battery = Storage(
        name=f"{area.id}_battery_pcomp",
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
        unit_count=1,
        power=ForecastingMatrix().add(power_ts, parameters.execution_date),
    )

    logger.debug(f"Created PCOMP battery for area: {area.id}")
    return battery


def _merge_batteries(normal_battery: Storage, pcomp_battery: Storage, parameters: AntaresToAtlasParameters) -> None:
    """Merge normal and PCOMP batteries into a single battery.

    Merges capacities and calculates weighted average efficiencies.
    """
    normal_battery.maximum_power += pcomp_battery.maximum_power
    normal_battery.minimum_power += pcomp_battery.minimum_power
    normal_battery.maximum_energy += pcomp_battery.maximum_energy

    normal_battery.discharge_efficiency = (
        normal_battery.discharge_efficiency * normal_battery.maximum_power.first_value()
        + pcomp_battery.discharge_efficiency * pcomp_battery.maximum_power.first_value()
    ) / (normal_battery.maximum_power.first_value() + pcomp_battery.maximum_power.first_value())

    normal_battery.charge_efficiency = (
        normal_battery.charge_efficiency * normal_battery.maximum_power.first_value()
        + pcomp_battery.charge_efficiency * pcomp_battery.maximum_power.first_value()
    ) / (normal_battery.maximum_power.first_value() + pcomp_battery.maximum_power.first_value())

    normal_battery.power = normal_battery.power.replace(
        parameters.execution_date, normal_battery.power + pcomp_battery.power
    )
