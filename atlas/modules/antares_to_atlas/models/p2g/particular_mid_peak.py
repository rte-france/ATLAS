"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.study import Study
from antares.craft.model.thermal import ThermalCluster
from loguru import logger
from pendulum import duration

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.models.thermal.thermal import _get_variable_cost
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters, ThermalTechnologyConfig
from atlas.objects.equipment.thermal import Thermal


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
        properties=parameters.thermal.pcomp_mid,
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
        properties=parameters.thermal.pcomp_peak,
    )

    atlas_dataset.thermal.add(new_units)
    logger.info(f"Converted {len(new_units)} pcomp_peak units")
    return atlas_dataset


def _convert_pcomp_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    suffix: str,
    properties: ThermalTechnologyConfig,
) -> list[Thermal]:
    """Generic helper to convert pcomp_mid or pcomp_peak clusters."""
    areas = study.get_areas()
    new_units: list[Thermal] = []

    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]
        thermals = area.get_thermals()
        thermal_name = f"{area.id}_{suffix}"

        thermal = thermals.get(thermal_name, None)

        if thermal is None:
            continue

        enabled = thermal.properties.enabled
        if not enabled:
            continue

        installed_capacity = thermal.properties.nominal_capacity * thermal.properties.unit_count
        if installed_capacity == 0.0:
            continue

        logger.info(f"Creating pcomp thermal unit: {thermal_name}")

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
    thermal: ThermalCluster,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    installed_capacity: float,
    properties: ThermalTechnologyConfig,
    study: Study,
) -> Thermal | None:
    """Create a new Thermal equipment for a pcomp cluster."""

    scenario = study.get_output(parameters.output_name).get_thermal_ts_numbers(thermal.name).get(parameters.scenario)
    maximum_power_ts = Timeseries.from_values(
        start_date=parameters.start_date, frequency="1h", values=thermal.get_series_matrix()[scenario - 1]
    )
    minimum_power_ts = Timeseries.from_index(
        start_date=parameters.start_date,
        frequency="1h",
        end_date=parameters.start_date + duration(years=1),
        default_value=thermal.properties.min_stable_power,
    )

    variable_cost_ts = Timeseries.from_index(
        start_date=parameters.start_date,
        frequency="1h",
        end_date=parameters.start_date + duration(years=1),
        default_value=_get_variable_cost(thermal, parameters),
    )

    startup_cost_ts = Timeseries.from_index(
        start_date=parameters.start_date,
        frequency="1h",
        end_date=parameters.start_date + duration(years=1),
        default_value=thermal.properties.startup_cost * thermal.properties.unit_count,
    )

    equipment = Thermal(
        name=thermal.name,
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
        co2_emission_factor=thermal.properties.co2,
        minimum_stable_power_duration=thermal.properties.min_stable_power,  # TODO a recupérer dans csv et pas via antares
        startup_delay_probability=properties.startup_delay_probability,
        startup_duration=properties.startup_duration,
        shutdown_duration=properties.shutdown_duration,
        maximum_gradient=properties.maximum_gradient,
        strategy=properties.strategy,
        setup_delay=properties.setup_delay,
        unit_count=thermal.properties.unit_count,
    )

    logger.debug(f"Created pcomp thermal unit: {thermal.name}")
    return equipment
