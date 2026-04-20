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
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.objects.equipment.thermal import Thermal

# Technology name fragments for CO2 factor fallback matching
_CO2_TECHNOLOGY_KEYWORDS = ["Nuclear", "Lignite", "Oil", "Gas", "Coal", "CCGT", "OCGT"]


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
            )
            if thermal_unit:
                thermal_units.append(thermal_unit)

    atlas_dataset.thermal = thermal_units

    logger.info(f"Converted {len(thermal_units)} thermal units")
    return atlas_dataset


def _convert_single_thermal(
    area: Area,
    thermal: ThermalCluster,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> Thermal | None:
    """Convert a single Antares thermal cluster to Atlas Thermal equipment."""
    # TODO: Verify how to get the thermal cluster name and group
    # In old code: antares_thermal.Name (e.g. "fr_Nuclear_1") and antares_thermal.Group (e.g. "Nuclear")
    thermal_name = thermal.name
    thermal_group = thermal.properties.group

    if thermal_group in parameters.excluded_thermic_groups:
        return None

    maximum_power_ts = _get_maximum_power(area, thermal, parameters)
    if maximum_power_ts is None:
        return None

    installed_capacity = thermal.properties.nominal_capacity * thermal.properties.unit_count
    if installed_capacity == 0:
        return None

    thermal_group_params = parameters.thermal.get(thermal_group)

    equipment = Thermal(
        name=thermal_name,
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
        variable_cost=_get_variable_cost(thermal, parameters),
        startup_cost=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=thermal.properties.startup_cost,
        ),
        co2_emission_factor=_get_co2_factor(thermal, thermal_name, thermal_group, parameters),
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
        default_value = (
            thermal.properties.nominal_capacity
            * thermal.properties.unit_count
            * thermal.get_prepro_modulation_matrix()[2]  # Capacity Modulation
            * (1 - thermal.get_prepro_data_matrix()[2])  # FORate
            * (1 - thermal.get_prepro_data_matrix()[3])  # PORate
        )

        logger.debug(f"Falling back to computed maximum power for {getattr(thermal, 'name', thermal)}")
        maximum_power_ts = Timeseries.from_values(
            start_date=parameters.start_date,
            frequency="1h",
            values=default_value,
        )

    if maximum_power_ts.abs().max() == 0.0:
        return None

    return maximum_power_ts


def _get_variable_cost(thermal: ThermalCluster, parameters: AntaresToAtlasParameters) -> Timeseries:
    """Get variable cost timeseries.

    Prefers MarketBidCost * MarketBidModulation if MarketBidCost > 0,
    otherwise falls back to MarginalCost * MarginalCostModulation.
    """

    if thermal.properties.market_bid_cost > 0:
        return Timeseries.from_values(
            parameters.start_date,
            frequency="1h",
            values=thermal.get_prepro_modulation_matrix()[1],  # MarketBidModulation
        )
    else:
        return Timeseries.from_values(
            parameters.start_date,
            frequency="1h",
            values=thermal.get_prepro_modulation_matrix()[0],  # MarginalCostModulation
        )


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

    co2_value = thermal.properties.co2

    if co2_value != 0.0:
        return co2_value

    for techno in _CO2_TECHNOLOGY_KEYWORDS:
        if techno in thermal_name or techno in thermal_group:
            return parameters.co2_emission_factors.get(techno)

    logger.warning(
        f"Thermal {thermal_name} did not match any known technology group. CO2EmissionFactor set to default."
    )
    return None
