"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.study import Study
from loguru import logger
from pendulum import duration

from atlas.core.io_utils.atlas_dataset import AtlasDataset
from atlas.core.math.timeseries import Timeseries
from atlas.enums import ThermalStrategy
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.modules.antares_to_atlas.utils import get_portfolio
from atlas.objects.equipment.thermal import Thermal


def convert_dsr_fr_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Convert France-specific DSR units (industrie, tertiaire, implicite)."""
    logger.info("Converting DSR units (France)")

    areas = study.get_areas()
    if "fr" not in areas:
        return atlas_dataset

    area = areas["fr"]
    binding_constraints = study.get_binding_constraints()
    dsr_units = []
    thermals = area.get_thermals()

    for dsr_config in parameters.dsr.fr_types:
        maximum_daily_energy = None
        if dsr_config.bc_name:
            bc = binding_constraints.get(dsr_config.bc_name, None)
            if bc is not None:
                maximum_daily_energy = Timeseries(bc.get_less_term_matrix())

        if dsr_config.thermal_name not in thermals:
            logger.warning(f"DSR cluster name {dsr_config.thermal_name} not found in thermals clusters, skipping")
            continue

        cluster = thermals[dsr_config.thermal_name]

        scenario = (
            study.get_output(parameters.output_name)
            .get_thermal_ts_numbers(area.id, cluster.id)
            .get(parameters.scenario, None)
        )
        if scenario is None:
            continue

        disponibility = Timeseries.from_values(
            start_date=parameters.start_date,
            values=cluster.get_series_matrix()[scenario - 1],
            frequency="1h",
        )

        variable_cost = Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=cluster.properties.marginal_cost,
        )

        dsr_unit = Thermal(
            name=dsr_config.name,
            node=atlas_dataset.get("node", "fr"),
            portfolio=get_portfolio(atlas_dataset, parameters, "fr"),
            has_daily_energy_constraint=dsr_config.has_daily_constraint,
            maximum_daily_energy=maximum_daily_energy,
            maximum_power=disponibility,
            variable_cost=variable_cost,
            strategy=ThermalStrategy.PEAK,
        )

        dsr_units.append(dsr_unit)
        logger.debug(f"Created DSR unit: {dsr_config.name}")

    atlas_dataset.thermal.add(dsr_units)
    return atlas_dataset


def convert_dsr_other_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Convert DSR units for non-France countries."""
    logger.info("Converting DSR units (other countries)")

    areas = study.get_areas()
    binding_constraints = study.get_binding_constraints()
    dsr_units: list[Thermal] = []

    for area_name in parameters.market_areas:
        if area_name.lower() == "fr":
            continue
        if area_name not in areas:
            continue

        area = areas[area_name]
        bc_name = parameters.dsr.other_bc_pattern.format(area_id=area.id)
        bc = binding_constraints.get(bc_name, None)

        maximum_daily_energy = None
        if bc is not None:
            maximum_daily_energy = Timeseries(bc.get_less_term_matrix())

        thermal_name = parameters.dsr.other_thermal_pattern.format(area_id=area.id, area_upper=area.id.upper())
        thermals = area.get_thermals()

        if thermal_name not in thermals:
            logger.warning(f"Thermal cluster {thermal_name} not found for area {area.id}, skipping DSR")
            continue

        cluster = thermals[thermal_name]

        scenario = (
            study.get_output(parameters.output_name)
            .get_thermal_ts_numbers(area.id, thermal_name)
            .get(parameters.scenario, None)
        )
        if scenario is None:
            logger.warning(f"No scenario found for {thermal_name} in area {area.id}, skipping DSR")
            continue

        try:
            maximum_power_df = cluster.get_series_matrix()[scenario - 1]
            if maximum_power_df.abs().max() == 0:
                continue
            maximum_power = Timeseries.from_values(parameters.start_date, frequency="1h", values=maximum_power_df)
        except Exception as e:
            logger.warning(f"Could not get availability for {thermal_name}: {e}")
            continue

        variable_cost = Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=cluster.properties.marginal_cost,
        )

        dsr_units.append(
            Thermal(
                name=f"{area.id}_dsr",
                node=atlas_dataset.get("node", area.id),
                portfolio=get_portfolio(atlas_dataset, parameters, area.id),
                has_daily_energy_constraint=True,
                maximum_daily_energy=maximum_daily_energy,
                maximum_power=maximum_power,
                variable_cost=variable_cost,
                strategy=ThermalStrategy.PEAK,
            )
        )
        logger.debug(f"Created DSR unit for area: {area.id}")

    atlas_dataset.thermal.add(dsr_units)
    return atlas_dataset
