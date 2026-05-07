"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft import Frequency, MCIndAreasDataType
from antares.craft.model.area import Area
from antares.craft.model.link import Link
from antares.craft.model.study import Study
from loguru import logger
from pendulum import duration

from atlas.enums import StorageType
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.modules.antares_to_atlas.utils import get_portfolio, get_weight_for_cluster
from atlas.objects.equipment.storage import Storage


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

    link = links.get(parameters.storage.battery_normal_link, None)
    link_pcomp = links.get(parameters.storage.battery_pcomp_link, None)

    normal_battery = None
    pcomp_battery = None
    normal_area_id: str | None = None
    pcomp_area_id: str | None = None

    if link is not None:
        normal_area_id = link.area_to_id
        if normal_area_id in parameters.market_areas and normal_area_id in areas:
            prefix = parameters.storage.battery_normal_link.removeprefix("z_")
            normal_battery = _convert_battery(
                areas[normal_area_id], study, parameters, atlas_dataset, link, prefix=prefix
            )

    if link_pcomp is not None:
        pcomp_area_id = link_pcomp.area_to_id
        if pcomp_area_id in parameters.market_areas and pcomp_area_id in areas:
            prefix = parameters.storage.battery_pcomp_link.removeprefix("z_")
            pcomp_battery = _convert_battery(
                areas[pcomp_area_id], study, parameters, atlas_dataset, link_pcomp, prefix=prefix
            )

    if normal_battery and pcomp_battery:
        if normal_area_id != pcomp_area_id:
            raise AssertionError(
                f"Cannot merge batteries from different areas: "
                f"normal={normal_area_id!r} vs pcomp={pcomp_area_id!r}"
            )
        logger.debug(f"Merging normal and pcomp batteries for area {normal_area_id}")
        _merge_batteries(normal_battery, pcomp_battery, parameters)
        batteries.append(normal_battery)
    elif normal_battery:
        batteries.append(normal_battery)
    elif pcomp_battery:
        batteries.append(pcomp_battery)

    atlas_dataset.storage.add(batteries)

    return atlas_dataset


def _convert_battery(
    area: Area,
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    link: Link,
    prefix: str,
) -> Storage | None:
    """Convert a battery unit for the given prefix ('batteries' or 'batteries_pcomp')."""
    binding_constraints = study.get_binding_constraints()
    binding_constraint = binding_constraints.get(f"{prefix}_{area.id}", None)

    scenario = (
        study.get_output(parameters.output_name)
        .get_thermal_ts_numbers(area.id, f"{prefix}_{area.id}")
        .get(parameters.scenario, None)
    )

    if scenario is None:
        logger.warning(f"No scenario found for {prefix}_{area.id}, skipping battery conversion for area {area.id}")
        return None

    if not binding_constraint:
        return None

    thermals = area.get_thermals()
    inj_thermal_name = f"{prefix}_inj"
    inj_thermal = thermals.get(inj_thermal_name, None)

    if not inj_thermal:
        return None

    maximum_power_df = inj_thermal.get_series_matrix()[scenario - 1]

    # TODO get the columns corresponding to CalculatedPower (column key not yet known).
    # Until the column is identified, we fall back to a None timeseries handled below.
    power_discharge_ts: Timeseries | None = None
    power_discharge_max = 0.0
    try:
        power_discharge_df = study.get_output(parameters.output_name).get_mc_ind_area(
            parameters.scenario, Frequency.HOURLY, data_type=MCIndAreasDataType.VALUES, area=area.id
        )[()]
        power_discharge_max = float(power_discharge_df.abs().max().max())
        power_discharge_ts = Timeseries.from_values(
            start_date=parameters.start_date, frequency="1h", values=power_discharge_df
        )
    except (KeyError, TypeError) as e:
        logger.debug(f"Could not get CalculatedPower for area {area.id}: {e}. Falling back to default.")

    if maximum_power_df.abs().max().max() == 0 and power_discharge_max == 0:
        return None

    maximum_power_ts = Timeseries.from_values(start_date=parameters.start_date, frequency="1h", values=maximum_power_df)

    stock_thermal = thermals.get(f"z_{prefix}_{prefix}_{area.id}_1", None)
    if stock_thermal is None:
        logger.warning(f"Stock thermal z_{prefix}_{prefix}_{area.id}_1 not found, skipping battery conversion")
        return None
    maximum_energy_df = stock_thermal.get_series_matrix()[scenario - 1]
    maximum_energy_ts = Timeseries.from_values(
        start_date=parameters.start_date, frequency="1h", values=maximum_energy_df
    )

    weight = get_weight_for_cluster(study, area.id, inj_thermal_name)
    charge_efficiency = weight if weight is not None else 1.0
    discharge_efficiency = 1.0 / weight if weight is not None else 1.0

    power_charge_df = link.get_capacity_direct()[scenario - 1]
    power_charge_ts = Timeseries.from_values(
        start_date=parameters.start_date, frequency="1h", values=power_charge_df * -1.0
    )

    if power_discharge_ts is None:
        power_discharge_ts = Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=0.0,
        )

    power_ts = power_discharge_ts + power_charge_ts

    minimum_power_value = float(power_charge_df.abs().max().max())
    minimum_power_ts = Timeseries.from_index(
        start_date=parameters.start_date,
        frequency="1h",
        end_date=parameters.start_date + duration(years=1),
        default_value=-minimum_power_value,
    )

    # "batteries" → "battery", "batteries_pcomp" → "battery_pcomp"
    name_suffix = prefix.replace("batteries", "battery")
    label = "normal" if prefix == "batteries" else "PCOMP"

    battery = Storage(
        name=f"{area.id}_{name_suffix}",
        node=atlas_dataset.get("node", area.id),
        portfolio=get_portfolio(atlas_dataset, parameters, area.id),
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
        storage_initial_level=parameters.storage.battery_initial_level,
        unit_count=1,
        power=ForecastingMatrix().add(power_ts, parameters.execution_date, inplace=False),
    )

    logger.debug(f"Created {label} battery for area: {area.id}")
    return battery


def _merge_batteries(normal_battery: Storage, pcomp_battery: Storage, parameters: AntaresToAtlasParameters) -> None:
    """Merge normal and PCOMP batteries into a single battery.

    Merges capacities and calculates weighted average efficiencies.
    """
    if normal_battery.maximum_power is None or pcomp_battery.maximum_power is None or normal_battery.power is None:
        logger.warning("Cannot merge batteries: missing capacity data")
        return

    # Capture weights before mutation (bug: maximum_power is updated in-place below)
    normal_max = normal_battery.maximum_power.first_value()
    pcomp_max = pcomp_battery.maximum_power.first_value()
    total_max = normal_max + pcomp_max

    normal_battery.maximum_power += pcomp_battery.maximum_power
    normal_battery.minimum_power += pcomp_battery.minimum_power
    normal_battery.maximum_energy += pcomp_battery.maximum_energy

    if total_max > 0:
        normal_battery.discharge_efficiency = (
            normal_battery.discharge_efficiency * normal_max
            + pcomp_battery.discharge_efficiency * pcomp_max
        ) / total_max

        normal_battery.charge_efficiency = (
            normal_battery.charge_efficiency * normal_max
            + pcomp_battery.charge_efficiency * pcomp_max
        ) / total_max

    # Merge power ForecastingMatrix by extracting and summing the underlying timeseries
    if isinstance(pcomp_battery.power, type(normal_battery.power)):
        exec_key = parameters.execution_date.format(normal_battery.power.date_format)
        if exec_key in normal_battery.power.indexes and exec_key in pcomp_battery.power.indexes:
            normal_ts = normal_battery.power[exec_key]
            pcomp_ts = pcomp_battery.power[exec_key]
            normal_battery.power.replace(parameters.execution_date, normal_ts + pcomp_ts)
