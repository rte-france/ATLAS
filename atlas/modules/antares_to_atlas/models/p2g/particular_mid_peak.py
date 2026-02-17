"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.study import Study
from antares.craft.model.thermal import ThermalCluster
from loguru import logger
from pendulum import duration

from atlas.enums import ThermalStrategy
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.thermal import Thermal
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters

# Hardcoded properties for pcomp_mid (CCG / Gas)
_PCOMP_MID_PROPERTIES = {
    "minimum_stable_power_duration": duration(minutes=30),  # 0.5h
    "startup_delay_probability": 0.26,
    "startup_duration": duration(hours=1),
    "shutdown_duration": duration(hours=1),
    "maximum_gradient_per_unit": 30.0,  # MW/h per unit
    "strategy": ThermalStrategy.INTERMEDIATE,
    "setup_delay": 0.0,
    "co2_factor_key": "H2_CCG",
}

# Hardcoded properties for pcomp_peak (TAC)
_PCOMP_PEAK_PROPERTIES = {
    "minimum_stable_power_duration": duration(minutes=0),
    "startup_delay_probability": 0.26,
    "startup_duration": duration(minutes=24),  # 0.4h
    "shutdown_duration": duration(minutes=24),  # 0.4h
    "maximum_gradient_per_unit": 30.0,  # MW/h per unit
    "strategy": ThermalStrategy.PEAK,
    "setup_delay": 0.0,
    "co2_factor_key": "H2_TAC",
}


def convert_pcomp_mid_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Convert pcomp_mid thermal clusters to Atlas Thermal equipment (CCG / Gas profile).

    pcomp_mid clusters represent hydrogen-powered combined-cycle gas turbines.
    They are identified by a thermal cluster named "{area}_{area_fmt}_Gas_pcomp_mid"
    and receive hardcoded CCG-like technical parameters.

    Units that are disabled or have zero installed capacity are skipped.
    If the unit already exists in atlas_dataset (e.g. created by thermal.py),
    it is reused; otherwise a new one is created.
    """
    logger.info("Converting pcomp_mid units")

    new_units = _convert_pcomp_units(
        study=study,
        parameters=parameters,
        atlas_dataset=atlas_dataset,
        suffix="Gas_pcomp_mid",
        properties=_PCOMP_MID_PROPERTIES,
    )

    atlas_dataset.thermal.add(new_units)
    logger.info(f"Converted {len(new_units)} pcomp_mid units")
    return atlas_dataset


def convert_pcomp_peak_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Convert pcomp_peak thermal clusters to Atlas Thermal equipment (TAC / peak profile).

    pcomp_peak clusters represent hydrogen-powered open-cycle gas turbines.
    They are identified by a thermal cluster named "{area}_{area_fmt}_Gas_pcomp_peak"
    and receive hardcoded TAC-like technical parameters.
    """
    logger.info("Converting pcomp_peak units")

    new_units = _convert_pcomp_units(
        study=study,
        parameters=parameters,
        atlas_dataset=atlas_dataset,
        suffix="Gas_pcomp_peak",
        properties=_PCOMP_PEAK_PROPERTIES,
    )

    atlas_dataset.thermal.add(new_units)
    logger.info(f"Converted {len(new_units)} pcomp_peak units")
    return atlas_dataset


def _convert_pcomp_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    suffix: str,
    properties: dict,
) -> list[Thermal]:
    """Generic helper to convert pcomp_mid or pcomp_peak clusters."""
    areas = study.get_areas()
    new_units: list[Thermal] = []

    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]

        # TODO: Verify the thermal cluster naming convention
        # In old code: f"{area.Name}_{functions.node_special_format(area.Name)}_{suffix}"
        # node_special_format() uppercases the first letter and replaces spaces with underscores
        # For now, using a simple format — verify the exact naming
        thermal_name = f"{area.id}_{suffix}"  # TODO: apply node_special_format

        # Find the thermal cluster in this area
        try:
            thermals = area.get_thermals()
        except Exception as e:
            logger.warning(f"Could not get thermals for area {area.id}: {e}")
            continue

        thermal = None
        for thermal_key, thermal_obj in thermals.items():
            if thermal_name.lower() in thermal_key.lower():
                thermal = thermal_obj
                break

        if thermal is None:
            continue

        # TODO: Verify how to check if a thermal cluster is enabled
        # In old code: not antares_instance.Enabled
        enabled = True  # TODO: thermal.properties.enabled or similar
        if not enabled:
            continue

        # Filter zero-capacity units
        # TODO: Verify field names NominalCapacity and UnitCount
        installed_capacity = 0.0  # TODO: float(thermal.nominal_capacity) * float(thermal.unit_count)
        if installed_capacity == 0.0:
            continue

        logger.info(f"Creating pcomp thermal unit: {thermal_name}")

        # Check if already created by thermal.py (avoid duplicates)
        existing = next((t for t in atlas_dataset.thermal if t.name == thermal_name), None)
        if existing:
            _apply_pcomp_properties(existing, thermal, properties, installed_capacity)
            continue

        unit = _create_pcomp_equipment(
            area_name=area_name,
            thermal_name=thermal_name,
            thermal=thermal,
            parameters=parameters,
            atlas_dataset=atlas_dataset,
            installed_capacity=installed_capacity,
            properties=properties,
        )
        if unit:
            new_units.append(unit)

    return new_units


def _create_pcomp_equipment(
    area_name: str,
    thermal_name: str,
    thermal: ThermalCluster,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    installed_capacity: float,
    properties: dict,
) -> Thermal | None:
    """Create a new Thermal equipment for a pcomp cluster."""
    # Maximum power
    maximum_power_ts = _get_maximum_power(thermal, parameters)

    # Minimum power from MinStablePower
    # TODO: Verify field name on ThermalCluster
    min_stable_power = 0.0  # TODO: float(thermal.min_stable_power)
    minimum_power_ts = Timeseries.from_index(
        start_date=parameters.start_date,
        frequency="1h",
        end_date=parameters.start_date + duration(years=1),
        default_value=min_stable_power,
    )

    # Variable cost: prefer MarketBidCost, fall back to MarginalCost
    # TODO: Verify field names on ThermalCluster
    variable_cost_ts = _get_variable_cost(thermal, parameters)

    # Startup cost (per unit * unit_count)
    # TODO: Verify field names — StartupCost * UnitCount in old code
    startup_cost_value = 0.0  # TODO: float(thermal.startup_cost) * float(thermal.unit_count)
    startup_cost_ts = Timeseries.from_index(
        start_date=parameters.start_date,
        frequency="1h",
        end_date=parameters.start_date + duration(years=1),
        default_value=startup_cost_value,
    )

    # CO2 factor: use antares value if non-zero, else use hardcoded key
    # TODO: Verify field name for CO2
    co2_value = 0.0  # TODO: float(thermal.co2)
    co2_factor = co2_value if co2_value != 0.0 else parameters.co2_emission_factors.get(properties["co2_factor_key"])

    # Unit count for MaximumGradient scaling
    unit_count = None  # TODO: int(thermal.unit_count)
    maximum_gradient = properties["maximum_gradient_per_unit"] * unit_count if unit_count else None

    equipment = Thermal(
        name=thermal_name,
        node=atlas_dataset.get("node", area_name),
        portfolio=atlas_dataset.get(
            "portfolio",
            f"generator_{area_name}" if parameters.consumption_production_separation else f"portfolio_{area_name}",
        ),
        maximum_power=maximum_power_ts,
        minimum_power=minimum_power_ts,
        installed_capacity=installed_capacity,
        variable_cost=variable_cost_ts,
        startup_cost=startup_cost_ts,
        co2_emission_factor=co2_factor,
        minimum_stable_power_duration=properties["minimum_stable_power_duration"],
        startup_delay_probability=properties["startup_delay_probability"],
        startup_duration=properties["startup_duration"],
        shutdown_duration=properties["shutdown_duration"],
        maximum_gradient=maximum_gradient,
        strategy=properties["strategy"],
        setup_delay=properties["setup_delay"],
        unit_count=unit_count,
    )

    logger.debug(f"Created pcomp thermal unit: {thermal_name}")
    return equipment


def _apply_pcomp_properties(
    equipment: Thermal,
    thermal: ThermalCluster,
    properties: dict,
    installed_capacity: float,
) -> None:
    """Apply pcomp-specific properties to an already-existing Thermal equipment."""
    unit_count = equipment.unit_count
    equipment.minimum_stable_power_duration = properties["minimum_stable_power_duration"]
    equipment.startup_delay_probability = properties["startup_delay_probability"]
    equipment.startup_duration = properties["startup_duration"]
    equipment.shutdown_duration = properties["shutdown_duration"]
    equipment.maximum_gradient = properties["maximum_gradient_per_unit"] * unit_count if unit_count else None
    equipment.strategy = properties["strategy"]
    equipment.setup_delay = properties["setup_delay"]


def _get_maximum_power(thermal: ThermalCluster, parameters: AntaresToAtlasParameters) -> Timeseries:
    """Get maximum power from Disponibility or fallback computation."""
    try:
        # TODO: Verify how to get ThermalSelectedScenario and Disponibility
        # In old code:
        #   sc = antares_instance.ThermalSelectedScenario[p.scenario - 1]
        #   return antares_instance.Disponibility[sc - 1]
        raise NotImplementedError("TODO: Get Disponibility from thermal cluster")
    except Exception:
        # Fallback: NominalCapacity * UnitCount * CapacityModulation * (1 - FORate) * (1 - PORate)
        # TODO: Replace with actual computation
        return Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=0.0,
        )


def _get_variable_cost(thermal: ThermalCluster, parameters: AntaresToAtlasParameters) -> Timeseries | None:
    """Get variable cost: MarketBidCost * modulation if > 0, else MarginalCost * modulation."""
    # TODO: Verify field names on ThermalCluster
    # In old code:
    #   if antares_instance.MarketBidCost > 0:
    #       return float(antares_instance.MarketBidCost) * antares_instance.MarketBidModulation
    #   else:
    #       return float(antares_instance.MarginalCost) * antares_instance.MarginalCostModulation
    return None  # TODO
