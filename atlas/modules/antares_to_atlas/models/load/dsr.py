"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from collections.abc import Mapping

from antares.craft.model.area import Area
from antares.craft.model.binding_constraint import BindingConstraint
from antares.craft.model.study import Study
from loguru import logger
from pendulum import duration

from atlas.enums import ThermalStrategy
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.objects.equipment.thermal import Thermal


def convert_dsr_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Convert DSR (Demand Side Response) units from Antares to Atlas.

    DSR units are modeled as thermal equipment with daily energy constraints.
    For France, there are specific units (industrie, tertiaire, implicite).
    For other countries, DSR units follow a more generic pattern.
    """
    logger.info("Converting DSR units")

    areas = study.get_areas()
    binding_constraints = study.get_binding_constraints()
    dsr_units: list[Thermal] = []

    # Process France-specific DSR units
    if "fr" in parameters.market_areas and "fr" in areas:
        logger.debug("Processing France-specific DSR units")
        dsr_units.extend(
            _convert_dsr_fr(
                study=study,
                parameters=parameters,
                atlas_dataset=atlas_dataset,
                area=areas["fr"],
                binding_constraints=binding_constraints,
            )
        )

    # Process DSR units for other countries
    for area_name in parameters.market_areas:
        if area_name.lower() == "fr":
            continue

        if area_name not in areas:
            continue

        dsr_unit = _convert_dsr_other_country(
            parameters=parameters,
            atlas_dataset=atlas_dataset,
            area=areas[area_name],
            binding_constraints=binding_constraints,
            study=study,
        )

        if dsr_unit:
            dsr_units.append(dsr_unit)

    atlas_dataset.thermal.add(dsr_units)

    return atlas_dataset


def _convert_dsr_fr(
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    area: Area,
    binding_constraints: Mapping[str, BindingConstraint],
    study: Study,
) -> list[Thermal]:
    """Convert France-specific DSR units (industrie, tertiaire, implicite)."""
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
            .get_thermal_ts_numbers(area.name, cluster.name)
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
            portfolio=atlas_dataset.get(
                "portfolio", "generator_fr" if parameters.consumption_production_separation else "portfolio_fr"
            ),
            has_daily_energy_constraint=dsr_config.has_daily_constraint,
            maximum_daily_energy=maximum_daily_energy,
            maximum_power=disponibility,
            variable_cost=variable_cost,
            strategy=ThermalStrategy.PEAK,
        )

        dsr_units.append(dsr_unit)
        logger.debug(f"Created DSR unit: {dsr_config.name}")

    return dsr_units


def _convert_dsr_other_country(
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    area: Area,
    binding_constraints: Mapping[str, BindingConstraint],
    study: Study,
) -> Thermal | None:
    """Convert DSR unit for a non-France country."""

    bc_name = parameters.dsr.other_bc_pattern.format(area_id=area.id)

    bc = binding_constraints.get(bc_name, None)

    if bc is not None:
        maximum_daily_energy = Timeseries(bc.get_less_term_matrix())

    thermal_name = parameters.dsr.other_thermal_pattern.format(area_id=area.id, area_upper=area.id.upper())

    thermals = area.get_thermals()

    if thermal_name not in thermals:
        logger.warning(f"Thermal cluster {thermal_name} not found for area {area.id}, skipping DSR")
        return None

    cluster = thermals[thermal_name]

    try:
        scenario = (
            study.get_output(parameters.output_name)
            .get_thermal_ts_numbers(area.id, thermal_name)
            .get(parameters.scenario, None)
        )
        maximum_power_df = cluster.get_series_matrix()[scenario - 1]

        if maximum_power_df.abs().max() == 0:
            return None
        maximum_power = Timeseries.from_values(parameters.start_date, frequency="1h", values=maximum_power_df)
    except Exception as e:
        logger.warning(f"Could not get availability for {thermal_name}: {e}")
        return None

    variable_cost = Timeseries.from_index(
        start_date=parameters.start_date,
        frequency="1h",
        end_date=parameters.start_date + duration(years=1),
        default_value=cluster.properties.marginal_cost,
    )

    # Create DSR equipment
    dsr_unit = Thermal(
        name=f"{area.id}_dsr",
        node=atlas_dataset.get("node", area.id),
        portfolio=atlas_dataset.get(
            "portfolio",
            f"generator_{area.id}" if parameters.consumption_production_separation else f"portfolio_{area.id}",
        ),
        has_daily_energy_constraint=True,
        maximum_daily_energy=maximum_daily_energy,
        maximum_power=maximum_power,
        variable_cost=variable_cost,
        strategy=ThermalStrategy.PEAK,
    )

    logger.debug(f"Created DSR unit for area: {area.id}")
    return dsr_unit
