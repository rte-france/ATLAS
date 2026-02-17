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
from atlas.models.equipment.thermal import Thermal
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters

_THERMIC_PROPERTIES = [
    "MinimumStablePowerDuration",
    "StartupDelayProbability",
    "StartupDuration",
    "ShutdownDuration",
    "MaximumGradient",
    "Strategy",
    "SetupDelay",
]

# Antares technology group names
_ANTARES_TECHNOLOGIES = ["Nuclear", "Lignite", "Oil", "Other", "Hard_Coal", "Mixed_fuel", "Gas"]

# Technology name fragments for CO2 factor fallback matching
_CO2_TECHNOLOGY_KEYWORDS = ["Nuclear", "Lignite", "Oil", "Gas", "Coal", "CCGT", "OCGT"]


def convert_thermal_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> tuple[AtlasDataset, dict, list]:
    """Convert Thermal cluster units from Antares to Atlas Thermal equipment.

    Loads optional thermal parameters from the thermic config CSV, then creates
    one Thermal equipment per cluster that:
    - Belongs to a market area in parameters.market_areas
    - Is not in an excluded group (parameters.excluded_thermic_groups)
    - Has non-zero maximum power and installed capacity

    :return: Tuple of (atlas_dataset, thermic_parameter, thermic_properties)
             thermic_parameter and thermic_properties are passed to mixed_fuel conversion.
    """
    logger.info("Converting Thermal units")

    thermic_parameter = _load_thermic_config(parameters)

    areas = study.get_areas()
    thermal_units: list[Thermal] = []

    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]

        thermals = area.get_thermals()

        for _, thermal in thermals.items():
            thermal_unit = _convert_single_thermal(
                area=area,
                thermal=thermal,
                parameters=parameters,
                atlas_dataset=atlas_dataset,
                thermic_parameter=thermic_parameter,
            )
            if thermal_unit:
                thermal_units.append(thermal_unit)

    atlas_dataset.thermal = thermal_units

    logger.info(f"Converted {len(thermal_units)} thermal units")
    return atlas_dataset, thermic_parameter, _THERMIC_PROPERTIES


def _load_thermic_config(parameters: AntaresToAtlasParameters) -> dict:
    """Load optional per-technology/per-instance thermal parameters from CSV.

    The CSV columns map to _THERMIC_PROPERTIES. Rows are either an Antares
    technology group name or a specific thermal cluster instance name.

    Returns dict[property_name][tech_or_instance_name] = value
    """
    thermic_parameter: dict = {}

    if parameters.thermic_config_file and parameters.thermic_config_file.is_file():
        logger.debug("No thermic config file found, using defaults")
        return thermic_parameter

    logger.debug(f"Loading thermic config from: {parameters.thermic_config_file}")

    try:
        with open(parameters.thermic_config_file) as f:
            lines_list = f.readlines()

        headers: list[str] = []
        thermic_index: dict[str, int] = {}

        for row_index, line in enumerate(lines_list):
            splitted_line = line.split(";")

            if row_index == 0:
                headers = splitted_line
                for i, header in enumerate(headers):
                    if header.strip() in _THERMIC_PROPERTIES:
                        thermic_parameter[header.strip()] = {}
                        thermic_index[header.strip()] = i
                continue

            if len(splitted_line) != len(headers):
                raise ValueError(
                    f"Invalid number of columns on line {row_index + 1}. Please modify the ThermicParameters file."
                )

            row_name = splitted_line[0]

            # TODO: Verify how to check if a thermal instance exists in the new API
            # In old code: antares_dataset.ThermalTechnology.CheckInstanceExists(row_name)
            is_known = row_name in _ANTARES_TECHNOLOGIES  # TODO: also check instance existence

            if not is_known:
                logger.warning(
                    f"{row_name} on line {row_index + 1} in ThermicParameters does not match a known "
                    "technology or instance. It will be ignored."
                )
                continue

            for prop_name, col_index in thermic_index.items():
                value = splitted_line[col_index].strip()
                if prop_name == "Strategy":
                    thermic_parameter[prop_name][row_name] = value
                else:
                    thermic_parameter[prop_name][row_name] = float(value)

    except Exception as e:
        logger.error(f"Error loading thermic config file: {e}")
        return {}

    # Log loaded values
    for prop_name in _THERMIC_PROPERTIES:
        if prop_name in thermic_parameter:
            logger.debug(f"{prop_name} values: {thermic_parameter[prop_name]}")

    return thermic_parameter


def _convert_single_thermal(
    area: Area,
    thermal: ThermalCluster,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    thermic_parameter: dict,
) -> Thermal | None:
    """Convert a single Antares thermal cluster to Atlas Thermal equipment."""
    # TODO: Verify how to get the thermal cluster name and group
    # In old code: antares_thermal.Name (e.g. "fr_Nuclear_1") and antares_thermal.Group (e.g. "Nuclear")
    thermal_name = thermal.name
    thermal_group = thermal.properties.group
    # Filter excluded groups

    if thermal_group in parameters.excluded_thermic_groups:
        return None

    # Compute maximum power
    maximum_power_ts = _get_maximum_power(area, thermal, parameters)
    if maximum_power_ts is None:
        return None

    # Filter zero-capacity units
    # TODO: Verify how to get NominalCapacity and UnitCount
    # In old code: antares_thermal.NominalCapacity * antares_thermal.UnitCount == 0.0
    installed_capacity = _get_installed_capacity(thermal)
    if installed_capacity == 0.0:
        return None

    # Build minimum power timeseries from MinStablePower
    # TODO: Verify how to get MinStablePower from thermal cluster
    # In old code: float(antares_thermal.MinStablePower)
    min_stable_power = 0.0  # TODO: thermal.min_stable_power
    minimum_power_ts = Timeseries.from_index(
        start_date=parameters.start_date,
        frequency="1h",
        end_date=parameters.start_date + duration(years=1),
        default_value=min_stable_power,
    )

    # Variable cost: prefer MarketBidCost, fall back to MarginalCost
    # TODO: Verify how to get MarketBidCost, MarginalCost and modulation time series
    variable_cost_ts = _get_variable_cost(thermal, parameters)

    # Startup cost timeseries
    # TODO: Verify how to get StartupCost from thermal cluster
    startup_cost_value = 0.0  # TODO: float(thermal.startup_cost)
    startup_cost_ts = Timeseries.from_index(
        start_date=parameters.start_date,
        frequency="1h",
        end_date=parameters.start_date + duration(years=1),
        default_value=startup_cost_value,
    )

    # CO2 emission factor
    co2_factor = _get_co2_factor(thermal, thermal_name, thermal_group, parameters)

    # Outage and scheduled shutdown statistics
    # TODO: Verify how to get FODuration, PODuration, FORate, PORate
    outage_mean_duration = _get_duration_average(thermal, "fo_duration")
    scheduled_shutdown_mean_duration = _get_duration_average(thermal, "po_duration")
    outage_probability = _get_rate_average(thermal, "fo_rate")
    scheduled_shutdown_probability = _get_rate_average(thermal, "po_rate")

    # Min up/down times
    # TODO: Verify field names for MinDownTime and MinUpTime
    minimum_time_off = None  # TODO: duration(hours=thermal.min_down_time)
    minimum_time_on = None  # TODO: duration(hours=thermal.min_up_time)

    # Unit count
    # TODO: Verify how to get UnitCount
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

    # Apply extra properties from thermic config CSV
    _apply_thermic_config_properties(equipment, thermal_name, thermal_group, thermic_parameter, unit_count)

    logger.debug(f"Created thermal unit: {thermal_name}")
    return equipment


def _get_maximum_power(
    area: Area,
    thermal: ThermalCluster,
    parameters: AntaresToAtlasParameters,
) -> Timeseries | None:
    """Get maximum power timeseries for a thermal cluster.

    Tries to use the pre-computed Disponibility time series for the selected scenario.
    Falls back to computing from NominalCapacity * UnitCount * CapacityModulation * (1 - FORate) * (1 - PORate).
    Returns None if the resulting timeseries is all zeros.
    """
    try:
        # TODO: Verify how to get ThermalSelectedScenario and Disponibility
        # In old code:
        #   sc = antares_thermal.ThermalSelectedScenario[p.scenario - 1]
        #   maximum_power_ts = antares_thermal.Disponibility[sc - 1]
        maximum_power_ts = None  # TODO

        if maximum_power_ts is None:
            raise ValueError("Disponibility not available")

    except Exception:
        # Fallback: compute from nominal capacity
        # TODO: Verify field names NominalCapacity, UnitCount, CapacityModulation, FORate, PORate
        # In old code:
        #   NominalCapacity * UnitCount * CapacityModulation * (1 - FORate) * (1 - PORate)
        logger.debug(f"Falling back to computed maximum power for {getattr(thermal, 'name', thermal)}")
        maximum_power_ts = Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=0.0,
        )  # TODO: Replace with actual computation

    # Filter zero-power units
    # TODO: Verify .abs().max() equivalent on Timeseries
    # if maximum_power_ts.abs().max() == 0.0:
    #     return None

    return maximum_power_ts


def _get_installed_capacity(thermal: ThermalCluster) -> float:
    """Get installed capacity = NominalCapacity * UnitCount."""
    # TODO: Verify field names on ThermalCluster
    # In old code: antares_thermal.NominalCapacity * antares_thermal.UnitCount
    return 0.0  # TODO: float(thermal.nominal_capacity) * float(thermal.unit_count)


def _get_variable_cost(thermal: ThermalCluster, parameters: AntaresToAtlasParameters) -> Timeseries | None:
    """Get variable cost timeseries.

    Prefers MarketBidCost * MarketBidModulation if MarketBidCost > 0,
    otherwise falls back to MarginalCost * MarginalCostModulation.
    """
    # TODO: Verify field names on ThermalCluster
    # In old code:
    #   if antares_thermal.MarketBidCost > 0:
    #       equipment.VariableCost = float(antares_thermal.MarketBidCost) * antares_thermal.MarketBidModulation
    #   else:
    #       equipment.VariableCost = float(antares_thermal.MarginalCost) * antares_thermal.MarginalCostModulation
    return None  # TODO


def _get_co2_factor(
    thermal: ThermalCluster,
    thermal_name: str,
    thermal_group: str,
    parameters: AntaresToAtlasParameters,
) -> float | None:
    """Get CO2 emission factor.

    Uses antares CO2 field if non-zero, otherwise looks up by technology keyword
    from parameters.co2_emission_factors.
    """
    # TODO: Verify field name for CO2 on ThermalCluster
    # In old code: antares_thermal.CO2
    co2_value = 0.0  # TODO: float(thermal.co2)

    if co2_value != 0.0:
        return co2_value

    # Fallback: match by technology keyword
    for techno in _CO2_TECHNOLOGY_KEYWORDS:
        if techno in thermal_name or techno in thermal_group:
            return parameters.co2_emission_factors.get(techno)

    logger.warning(
        f"Thermal {thermal_name} did not match any known technology group. CO2EmissionFactor set to default."
    )
    return None


def _get_duration_average(thermal: ThermalCluster, field: str) -> float | None:
    """Get average duration in hours (multiplied by 24 to convert from days)."""
    # TODO: Verify field names and how to check if empty / get average
    # In old code:
    #   if antares_thermal.FODuration.IsEmpty: return 0
    #   else: return antares_thermal.FODuration.Average() * 24
    return None  # TODO


def _get_rate_average(thermal: ThermalCluster, field: str) -> float | None:
    """Get average rate (probability between 0 and 1)."""
    # TODO: Verify field names and how to check if empty / get average
    # In old code:
    #   if antares_thermal.FORate.IsEmpty: return 0
    #   else: return antares_thermal.FORate.Average()
    return None  # TODO


def _apply_thermic_config_properties(
    equipment: Thermal,
    thermal_name: str,
    thermal_group: str,
    thermic_parameter: dict,
    unit_count: int | None,
) -> None:
    """Apply extra properties from the thermic config CSV to the equipment.

    MaximumGradient is multiplied by UnitCount (it is defined per unit).
    All other properties are set as-is, with instance-level values taking
    priority over group-level values.
    """
    for prop_name in _THERMIC_PROPERTIES:
        if prop_name not in thermic_parameter:
            continue

        prop_values = thermic_parameter[prop_name]

        # Resolve value: instance-level takes priority over group-level
        if thermal_name in prop_values:
            value = prop_values[thermal_name]
        elif thermal_group in prop_values:
            value = prop_values[thermal_group]
        else:
            continue

        # MaximumGradient is per-unit and must be scaled by UnitCount
        if prop_name == "MaximumGradient" and unit_count:
            value = value * unit_count

        # TODO: Map CSV property names to Thermal model field names
        # In old code: equipment.SetPropertyByName(name, value)
        # Mapping:
        #   "MinimumStablePowerDuration" -> equipment.minimum_stable_power_duration
        #   "StartupDelayProbability"    -> equipment.startup_delay_probability
        #   "StartupDuration"            -> equipment.startup_duration
        #   "ShutdownDuration"           -> equipment.shutdown_duration
        #   "MaximumGradient"            -> equipment.maximum_gradient
        #   "Strategy"                   -> equipment.strategy (ThermalStrategy enum)
        #   "SetupDelay"                 -> equipment.setup_delay
        _PROP_NAME_MAP = {
            "MinimumStablePowerDuration": "minimum_stable_power_duration",
            "StartupDelayProbability": "startup_delay_probability",
            "StartupDuration": "startup_duration",
            "ShutdownDuration": "shutdown_duration",
            "MaximumGradient": "maximum_gradient",
            "Strategy": "strategy",
            "SetupDelay": "setup_delay",
        }
        atlas_field = _PROP_NAME_MAP.get(prop_name)
        if atlas_field:
            # TODO: For duration fields, wrap value in duration(hours=value)
            # For Strategy, convert string to ThermalStrategy enum
            setattr(equipment, atlas_field, value)
