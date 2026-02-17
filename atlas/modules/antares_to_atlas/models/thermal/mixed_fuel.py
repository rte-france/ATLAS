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
from atlas.models.equipment.load import Load
from atlas.models.equipment.thermal import Thermal
from atlas.modules.antares_to_atlas.models.thermal.thermal import (
    _apply_thermic_config_properties,
    _get_duration_average,
    _get_rate_average,
    _get_variable_cost,
)
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters

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
    thermic_parameter: dict,
) -> AtlasDataset:
    """Convert Mixed_fuel thermal clusters from Antares to Atlas equipment.

    Mixed_fuel clusters are handled separately from standard thermals because:
    - "Waste" sub-technologies become OtherNonDispatchable (Load) equipment
    - Classic sub-technologies (Coal, CCGT, etc.) become Thermal equipment
    - Waste units from the same area are aggregated into a single Load equipment

    The thermic_parameter dict (from thermal.py) is reused to apply CSV-defined properties.
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
            # TODO: Verify how to get the Group from ThermalCluster
            # In old code: antares_thermal.Group
            thermal_group = thermal.group if hasattr(thermal, "group") else ""

            if thermal_group != "Mixed_fuel":
                continue

            thermal_name = thermal.name if hasattr(thermal, "name") else str(thermal)

            # Waste sub-technologies -> OtherNonDispatchable Load
            if "Waste" in thermal_name:
                _process_waste_unit(
                    area=area,
                    thermal=thermal,
                    thermal_name=thermal_name,
                    parameters=parameters,
                    atlas_dataset=atlas_dataset,
                    new_load_units=new_load_units,
                )
                continue

            # Classic sub-technologies -> Thermal equipment
            thermal_unit = _process_classic_mixed_fuel(
                area=area,
                thermal=thermal,
                thermal_name=thermal_name,
                parameters=parameters,
                atlas_dataset=atlas_dataset,
                thermic_parameter=thermic_parameter,
            )
            if thermal_unit:
                new_thermal_units.append(thermal_unit)

    atlas_dataset.thermal = getattr(atlas_dataset, "thermal", []) + new_thermal_units
    atlas_dataset.load = getattr(atlas_dataset, "load", []) + new_load_units

    logger.info(f"Converted {len(new_thermal_units)} mixed fuel thermal units and {len(new_load_units)} waste units")
    return atlas_dataset


def _process_waste_unit(
    area: Area,
    thermal: ThermalCluster,
    thermal_name: str,
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

    # Look for existing Waste Load in new_load_units (accumulate if found)
    existing_waste = next((u for u in new_load_units if u.name == waste_name), None)

    # Also check already-added loads in atlas_dataset
    if existing_waste is None and hasattr(atlas_dataset, "load"):
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
    thermal_name: str,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    thermic_parameter: dict,
) -> Thermal | None:
    """Convert a classic Mixed_fuel cluster (Coal, CCGT, OCGT, Oil, Lignite) to Thermal equipment."""
    # Detect technology from name
    techno = _detect_mixed_fuel_technology(thermal_name)
    if techno is None:
        logger.warning(f"Could not detect technology for Mixed_fuel unit {thermal_name}, skipping")
        return None

    # Filter zero-capacity units
    # TODO: Verify field names NominalCapacity and UnitCount
    # In old code: antares_thermal.NominalCapacity * antares_thermal.UnitCount == 0.0
    installed_capacity = 0.0  # TODO: float(thermal.nominal_capacity) * float(thermal.unit_count)
    if installed_capacity == 0.0:
        return None

    # Maximum power
    try:
        # TODO: Get ThermalSelectedScenario and Disponibility
        # In old code:
        #   sc = antares_thermal.ThermalSelectedScenario[p.scenario - 1]
        #   equipment.MaximumPower = antares_thermal.Disponibility[sc - 1]
        maximum_power_ts = None  # TODO
        if maximum_power_ts is None:
            raise ValueError("Disponibility not available")
    except Exception:
        # Fallback: compute from nominal capacity
        # TODO: NominalCapacity * UnitCount * CapacityModulation * (1 - FORate) * (1 - PORate)
        maximum_power_ts = Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=0.0,
        )  # TODO: Replace with actual computation

    # Minimum power from MinStablePower
    # TODO: Verify field name
    min_stable_power = 0.0  # TODO: float(thermal.min_stable_power)
    minimum_power_ts = Timeseries.from_index(
        start_date=parameters.start_date,
        frequency="1h",
        end_date=parameters.start_date + duration(years=1),
        default_value=min_stable_power,
    )

    # Variable cost
    variable_cost_ts = _get_variable_cost(thermal, parameters)

    # Startup cost
    startup_cost_value = 0.0  # TODO: float(thermal.startup_cost)
    startup_cost_ts = Timeseries.from_index(
        start_date=parameters.start_date,
        frequency="1h",
        end_date=parameters.start_date + duration(years=1),
        default_value=startup_cost_value,
    )

    # CO2 factor: use antares value if non-zero, else look up by technology
    # TODO: Verify field name for CO2
    co2_value = 0.0  # TODO: float(thermal.co2)
    co2_factor = co2_value if co2_value != 0.0 else parameters.co2_emission_factors.get(techno)

    # Outage/shutdown statistics
    outage_mean_duration = _get_duration_average(thermal, "fo_duration")
    scheduled_shutdown_mean_duration = _get_duration_average(thermal, "po_duration")
    outage_probability = _get_rate_average(thermal, "fo_rate")
    scheduled_shutdown_probability = _get_rate_average(thermal, "po_rate")

    # Min up/down times
    minimum_time_off = None  # TODO: duration(hours=thermal.min_down_time)
    minimum_time_on = None  # TODO: duration(hours=thermal.min_up_time)
    unit_count = None  # TODO: int(thermal.unit_count)

    equipment = Thermal(
        name=thermal_name,
        node=atlas_dataset.get("node", area.id),
        portfolio=atlas_dataset.get(
            "portfolio",
            f"generator_{area.id}" if parameters.consumption_production_separation else f"portfolio_{area.id}",
        ),
        has_daily_energy_constraint=False,
        maximum_power=maximum_power_ts,
        minimum_power=minimum_power_ts,
        installed_capacity=installed_capacity,
        variable_cost=variable_cost_ts,
        startup_cost=startup_cost_ts,
        co2_emission_factor=co2_factor,
        outage_mean_duration=outage_mean_duration,
        scheduled_shutdown_mean_duration=scheduled_shutdown_mean_duration,
        outage_probability=outage_probability,
        scheduled_shutdown_probability=scheduled_shutdown_probability,
        minimum_time_off=minimum_time_off,
        minimum_time_on=minimum_time_on,
        unit_count=unit_count,
    )

    # Apply extra properties from thermic config (using techno as group key)
    _apply_thermic_config_properties(equipment, thermal_name, techno, thermic_parameter, unit_count)

    logger.debug(f"Created mixed fuel thermal unit: {thermal_name} ({techno})")
    return equipment


def _detect_mixed_fuel_technology(thermal_name: str) -> str | None:
    """Detect the canonical technology name from a Mixed_fuel cluster name."""
    for keyword, techno in _MIXED_FUEL_TECH_MAP.items():
        if keyword in thermal_name:
            return techno
    return None
