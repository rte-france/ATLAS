"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.area import Area
from antares.craft.model.study import Study
from antares.craft.model.thermal import ThermalCluster
from loguru import logger
from pendulum import duration

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.io_utils.container import Container
from atlas.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.modules.antares_to_atlas.utils import get_maximum_power, get_portfolio, get_variable_cost
from atlas.objects.equipment.thermal import Thermal


def convert_thermal_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Convert Thermal cluster units from Antares to Atlas Thermal equipment.

    Creates one Thermal equipment per cluster that:
    - Belongs to a market area in parameters.market_areas
    - Is not in an excluded group (parameters.excluded_thermic_groups)
    - Has non-zero maximum power and installed capacity
    """
    logger.info("Converting Thermal units")

    areas = study.get_areas()
    thermal_units: list[Thermal] = []

    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]

        for _, thermal in area.get_thermals().items():
            thermal_unit = _convert_single_thermal(
                area=area,
                thermal=thermal,
                parameters=parameters,
                atlas_dataset=atlas_dataset,
                study=study,
            )
            if thermal_unit:
                thermal_units.append(thermal_unit)

    atlas_dataset.thermal = Container(thermal_units)

    logger.info(f"Converted {len(thermal_units)} thermal units")
    return atlas_dataset


def _convert_single_thermal(
    area: Area,
    thermal: ThermalCluster,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    study: Study,
) -> Thermal | None:
    """Convert a single Antares thermal cluster to Atlas Thermal equipment."""

    thermal_name = f"{area.id}_{thermal.id}"
    thermal_group = thermal.properties.group

    if thermal_group in parameters.excluded_thermic_groups:
        return None

    maximum_power_ts = get_maximum_power(area, thermal, parameters, study)
    if maximum_power_ts is None:
        return None

    installed_capacity = thermal.properties.nominal_capacity * thermal.properties.unit_count
    if installed_capacity == 0:
        return None

    # Refine Gas group into ccgt/ocgt based on cluster name when possible
    refined_group = thermal_group
    if thermal_group.lower() == "gas":
        cluster_id = thermal.id.lower()
        if "ocgt" in cluster_id:
            refined_group = "ocgt"
        elif "ccgt" in cluster_id:
            refined_group = "ccgt"

    thermal_group_params = parameters.thermal.get(refined_group) or parameters.thermal.get(thermal_group)
    if thermal_group_params is None:
        logger.warning(f"No thermal config for group '{thermal_group}', skipping {thermal_name}")
        return None

    end_date = parameters.start_date + duration(years=1)
    days_in_year = (end_date - parameters.start_date).days

    equipment = Thermal(
        name=thermal_name,
        node=atlas_dataset.get("node", area.id),
        portfolio=get_portfolio(atlas_dataset, parameters, area.id),
        has_daily_energy_constraint=False,
        maximum_power=maximum_power_ts,
        minimum_power=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency=f"{days_in_year}d",
            end_date=end_date,
            default_value=thermal.properties.min_stable_power,
        ),
        installed_capacity=installed_capacity,
        variable_cost=get_variable_cost(thermal, parameters),
        startup_cost=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency=f"{days_in_year}d",
            end_date=end_date,
            default_value=thermal.properties.startup_cost,
        ),
        additional_hours=duration(hours=12),
        maximum_afrr=0.0,
        maximum_fcr=0.0,
        co2_emission_factor=thermal.properties.co2,
        outage_mean_duration=duration(hours=thermal.get_prepro_data_matrix()[0].mean()),  # FODuration
        scheduled_shutdown_mean_duration=duration(hours=thermal.get_prepro_data_matrix()[1].mean()),  # PODuration
        outage_probability=thermal.get_prepro_data_matrix()[2].mean(),  # FORate
        scheduled_shutdown_probability=thermal.get_prepro_data_matrix()[3].mean(),  # PORate
        minimum_time_off=duration(hours=thermal.properties.min_down_time),
        minimum_time_on=duration(hours=thermal.properties.min_up_time),
        unit_count=thermal.properties.unit_count,
        minimum_stable_power_duration=thermal_group_params.minimum_stable_power_duration,
        startup_delay_probability=thermal_group_params.startup_delay_probability,
        startup_duration=thermal_group_params.startup_duration,
        shutdown_duration=thermal_group_params.shutdown_duration,
        maximum_gradient=thermal_group_params.maximum_gradient * thermal.properties.unit_count,
        strategy=thermal_group_params.strategy,
        setup_delay=thermal_group_params.setup_delay,
    )

    logger.debug(f"Created thermal unit: {thermal_name}")
    return equipment
