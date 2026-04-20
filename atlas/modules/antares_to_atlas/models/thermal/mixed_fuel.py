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
from atlas.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.models.thermal.thermal import (
    _get_co2_factor,
    _get_maximum_power,
    _get_variable_cost,
)
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.objects.equipment.load import Load
from atlas.objects.equipment.thermal import Thermal

# Technology keywords used to classify Mixed_fuel clusters
_MIXED_FUEL_TECH_KEYWORDS = ["Coal", "coal", "Lignite", "CCGT", "OCGT", "Oil", "oil"]

# Mapping from name keyword to canonical technology name (for CO2 lookup)
_MIXED_FUEL_TECH_MAP = {
    "Coal": "Coal",
    "coal": "Coal",
    "Lignite": "Lignite",
    "CCGT": "CCGT",
    "OCGT": "OCGT",
    "Oil": "Oil",
    "oil": "Oil",
}


def convert_mixed_fuel_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Convert Mixed_fuel thermal clusters from Antares to Atlas equipment.

    Mixed_fuel clusters are handled separately from standard thermals because:
    - "Waste" sub-technologies become OtherNonDispatchable (Load) equipment
    - Classic sub-technologies (Coal, CCGT, etc.) become Thermal equipment
    - Waste units from the same area are aggregated into a single Load equipment
    """
    logger.info("Converting Mixed_fuel units")

    areas = study.get_areas()
    new_thermal_units: list[Thermal] = []
    new_load_units: list[Load] = []

    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]

        try:
            thermals = area.get_thermals()
        except Exception as e:
            logger.warning(f"Could not get thermals for area {area.id}: {e}")
            continue

        for _, thermal in thermals.items():
            if thermal.properties.group != "Mixed_fuel":
                continue

            # Waste sub-technologies -> OtherNonDispatchable Load
            if "Waste" in thermal.name:
                _process_waste_unit(
                    area=area,
                    thermal=thermal,
                    parameters=parameters,
                    atlas_dataset=atlas_dataset,
                    new_load_units=new_load_units,
                )
                continue

            # Classic sub-technologies -> Thermal equipment
            thermal_unit = _process_classic_mixed_fuel(
                area=area,
                thermal=thermal,
                parameters=parameters,
                atlas_dataset=atlas_dataset,
            )
            if thermal_unit:
                new_thermal_units.append(thermal_unit)

    atlas_dataset.thermal.add(new_thermal_units)
    atlas_dataset.load.add(new_load_units)

    logger.info(f"Converted {len(new_thermal_units)} mixed fuel thermal units and {len(new_load_units)} waste units")
    return atlas_dataset


def _process_waste_unit(
    area: Area,
    thermal: ThermalCluster,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    new_load_units: list[Load],
) -> None:
    """Convert a Waste Mixed_fuel cluster to OtherNonDispatchable Load equipment.

    Waste units from the same area are merged (power is accumulated) into a
    single Load equipment named "{area}_Waste".
    """
    # TODO: Get production time series
    # In old code:
    #   sc = antares_thermal.ThermalSelectedScenario[p.scenario - 1]
    #   prod = antares_thermal.Disponibility[sc - 1]
    prod_ts = None  # TODO: Get Disponibility for selected scenario

    if prod_ts is None:
        return

    # TODO: Check if prod_ts has non-zero values
    # if prod_ts.abs().max() == 0:
    #     return

    waste_name = f"{area.id}_Waste"

    existing_waste = next((u for u in new_load_units if u.name == waste_name), None)

    if existing_waste is None:
        existing_waste = next((u for u in atlas_dataset.load if u.name == waste_name), None)

    if existing_waste is None:
        # Create new Waste Load equipment
        waste_load = Load(
            name=waste_name,
            node=atlas_dataset.get("node", area.id),
            portfolio=atlas_dataset.get(
                "portfolio",
                f"generator_{area.id}" if parameters.consumption_production_separation else f"portfolio_{area.id}",
            ),
            # TODO: Set maximum_power_forecast with ForecastingMatrix
            # In old code: waste_equipment.MaximumPowerForecast.AddTimeSeries(p.execution_date, prod)
        )
        new_load_units.append(waste_load)
        logger.debug(f"Created Waste load unit: {waste_name}")

    else:
        # Accumulate power into existing Waste Load
        # TODO: Add prod_ts to existing waste power forecast
        # In old code:
        #   previous_power = waste_equipment.Power[p.execution_date]
        #   new_power = previous_power + prod
        #   waste_equipment.MaximumPowerForecast.DeleteTimeSeries(p.execution_date)
        #   waste_equipment.MaximumPowerForecast.AddTimeSeries(p.execution_date, new_power)
        logger.debug(f"TODO: Accumulate power into existing Waste load unit {waste_name}")


def _process_classic_mixed_fuel(
    area: Area,
    thermal: ThermalCluster,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> Thermal | None:
    """Convert a classic Mixed_fuel cluster (Coal, CCGT, OCGT, Oil, Lignite) to Thermal equipment."""
    # Detect technology from name
    techno = _detect_mixed_fuel_technology(thermal.name)
    if techno is None:
        logger.warning(f"Could not detect technology for Mixed_fuel unit {thermal.name}, skipping")
        return None

    maximum_power_ts = _get_maximum_power(area, thermal, parameters)
    if maximum_power_ts is None:
        return None

    installed_capacity = thermal.properties.nominal_capacity * thermal.properties.unit_count
    if installed_capacity == 0:
        return None

    # Variable cost
    variable_cost_ts = _get_variable_cost(thermal, parameters)
    thermal_group_params = parameters.thermal.get(thermal.properties.group)

    equipment = Thermal(
        name=thermal.name,
        node=atlas_dataset.get("node", area.id),
        portfolio=atlas_dataset.get(
            "portfolio",
            f"generator_{area.id}" if parameters.consumption_production_separation else f"portfolio_{area.id}",
        ),
        has_daily_energy_constraint=False,
        maximum_power=maximum_power_ts,
        minimum_power=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=thermal.properties.min_stable_power,
        ),
        installed_capacity=installed_capacity,
        variable_cost=variable_cost_ts,
        startup_cost=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=thermal.properties.startup_cost,
        ),
        co2_emission_factor=_get_co2_factor(thermal, thermal.name, thermal.properties.group, parameters),
        outage_mean_duration=thermal.get_prepro_data_matrix()[0].mean(),  # FODuration
        scheduled_shutdown_mean_duration=thermal.get_prepro_data_matrix()[1].mean(),  # PODuration
        outage_probability=thermal.get_prepro_data_matrix()[2].mean(),  # FORate
        scheduled_shutdown_probability=thermal.get_prepro_data_matrix()[0].mean(),  # PORate
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

    logger.debug(f"Created mixed fuel thermal unit: {thermal.name} ({techno})")
    return equipment


def _detect_mixed_fuel_technology(thermal: ThermalCluster) -> str | None:
    """Detect the canonical technology name from a Mixed_fuel cluster name."""
    for keyword, techno in _MIXED_FUEL_TECH_MAP.items():
        if keyword in thermal.name:
            return techno
    return None
