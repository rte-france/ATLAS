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
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.modules.antares_to_atlas.utils import get_co2_factor, get_maximum_power, get_variable_cost
from atlas.objects.equipment.other_non_dispatchable import OtherNonDispatchable
from atlas.objects.equipment.thermal import Thermal

# Mapping from name keyword to canonical technology name (for CO2 / config lookup)
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
    - "Waste" sub-technologies become OtherNonDispatchable equipment
    - Classic sub-technologies (Coal, CCGT, etc.) become Thermal equipment
    - Waste units from the same area are aggregated into a single OtherNonDispatchable
    """
    logger.info("Converting Mixed_fuel units")

    areas = study.get_areas()
    new_thermal_units: list[Thermal] = []
    new_waste_units: list[OtherNonDispatchable] = []

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
            if thermal.properties.group != parameters.thermal.mixed_fuel_group:
                continue

            # Waste sub-technologies -> OtherNonDispatchable
            if parameters.thermal.waste_identifier in thermal.name:
                _process_waste_unit(
                    area=area,
                    thermal=thermal,
                    parameters=parameters,
                    atlas_dataset=atlas_dataset,
                    new_waste_units=new_waste_units,
                    study=study,
                )
                continue

            # Classic sub-technologies -> Thermal equipment
            thermal_unit = _process_classic_mixed_fuel(
                area=area,
                thermal=thermal,
                parameters=parameters,
                atlas_dataset=atlas_dataset,
                study=study,
            )
            if thermal_unit:
                new_thermal_units.append(thermal_unit)

    atlas_dataset.thermal.add(new_thermal_units)
    atlas_dataset.other_non_dispatchable.add(new_waste_units)

    logger.info(f"Converted {len(new_thermal_units)} mixed fuel thermal units and {len(new_waste_units)} waste units")
    return atlas_dataset


def _process_waste_unit(
    area: Area,
    thermal: ThermalCluster,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    new_waste_units: list[OtherNonDispatchable],
    study: Study,
) -> None:
    """Convert a Waste Mixed_fuel cluster to OtherNonDispatchable equipment.

    Waste units from the same area are merged (power is accumulated) into a
    single OtherNonDispatchable named "{area}_Waste".
    """
    scenario = (
        study.get_output(parameters.output_name)
        .get_thermal_ts_numbers(area.name, thermal.name)
        .get(parameters.scenario, None)
    )
    if scenario is None:
        logger.warning(f"Could not find thermal time series for area {area.id} and scenario {parameters.scenario}")
        return

    prod_ts = Timeseries.from_values(
        parameters.start_date, frequency="1h", values=thermal.get_series_matrix()[scenario - 1]
    )

    if prod_ts is None:
        return

    if prod_ts.abs().max() == 0:
        return

    waste_name = f"{area.id}_Waste"

    existing_waste = next((u for u in new_waste_units if u.name == waste_name), None)

    if existing_waste is None:
        existing_waste = next((u for u in atlas_dataset.other_non_dispatchable if u.name == waste_name), None)

    if existing_waste is None:
        waste_unit = OtherNonDispatchable(
            name=waste_name,
            node=atlas_dataset.get("node", area.id),
            portfolio=atlas_dataset.get(
                "portfolio",
                f"generator_{area.id}" if parameters.consumption_production_separation else f"portfolio_{area.id}",
            ),
            maximum_power_forecast=ForecastingMatrix().add(prod_ts, parameters.execution_date, inplace=False),
        )
        new_waste_units.append(waste_unit)
        logger.debug(f"Created Waste unit: {waste_name}")

    else:
        # Accumulate power into existing Waste unit for the same execution date
        fm = existing_waste.maximum_power_forecast
        if isinstance(fm, ForecastingMatrix):
            exec_key = parameters.execution_date.format(fm.date_format)
            prev_ts = fm[exec_key]
            fm.replace(parameters.execution_date, prev_ts + prod_ts)
        logger.debug(f"Accumulated power into existing Waste unit {waste_name}")


def _process_classic_mixed_fuel(
    area: Area,
    thermal: ThermalCluster,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    study: Study,
) -> Thermal | None:
    """Convert a classic Mixed_fuel cluster (Coal, CCGT, OCGT, Oil, Lignite) to Thermal equipment."""
    techno = _detect_mixed_fuel_technology(thermal)
    if techno is None:
        logger.warning(f"Could not detect technology for Mixed_fuel unit {thermal.name}, skipping")
        return None

    maximum_power_ts = get_maximum_power(area, thermal, parameters, study)
    if maximum_power_ts is None:
        return None

    installed_capacity = thermal.properties.nominal_capacity * thermal.properties.unit_count
    if installed_capacity == 0:
        return None

    thermal_group_params = parameters.thermal.get(techno)
    if thermal_group_params is None:
        logger.warning(f"No thermal config found for Mixed_fuel technology {techno}, skipping {thermal.name}")
        return None

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
        variable_cost=get_variable_cost(thermal, parameters),
        startup_cost=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=thermal.properties.startup_cost,
        ),
        co2_emission_factor=get_co2_factor(thermal, techno, parameters),
        outage_mean_duration=thermal.get_prepro_data_matrix()[0].mean(),  # FODuration
        scheduled_shutdown_mean_duration=thermal.get_prepro_data_matrix()[1].mean(),  # PODuration
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

    logger.debug(f"Created mixed fuel thermal unit: {thermal.name} ({techno})")
    return equipment


def _detect_mixed_fuel_technology(thermal: ThermalCluster) -> str | None:
    """Detect the canonical technology name from a Mixed_fuel cluster name."""
    for keyword, techno in _MIXED_FUEL_TECH_MAP.items():
        if keyword in thermal.name:
            return techno
    return None
