"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.area import Area
from antares.craft.model.binding_constraint import BindingConstraint
from antares.craft.model.study import Study
from loguru import logger
from pendulum import duration

from atlas.enums import ThermalStrategy
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.thermal import Thermal
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


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
        )

        if dsr_unit:
            dsr_units.append(dsr_unit)

    atlas_dataset.thermal.add(dsr_units)

    return atlas_dataset


def _convert_dsr_fr(
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    area: Area,
    binding_constraints: dict[str, BindingConstraint],
) -> list[Thermal]:
    """Convert France-specific DSR units (industrie, tertiaire, implicite)."""
    dsr_units = []
    thermals = area.get_thermals()

    dsr_types = [
        {
            "name": "fr_dsr_indus",
            "bc_name": "fr_dsr_industrie_stock",
            "thermal_name": "fr_FR_DSR_industrie",
            "has_daily_constraint": True,
        },
        {
            "name": "fr_dsr_tert",
            "bc_name": "fr_dsr_tertiaire_stock",
            "thermal_name": "fr_FR_DSR_tertiaire",
            "has_daily_constraint": True,
        },
        {
            "name": "fr_dsr_implicite",
            "bc_name": None,  # No binding constraint for implicite
            "thermal_name": "fr_FR_DSR_implicite",
            "has_daily_constraint": False,
        },
    ]

    for dsr_config in dsr_types:
        maximum_daily_energy = None
        bc_name = dsr_config.get("bc_name", None)
        if bc_name:
            bc = binding_constraints.get(bc_name, None)
            if bc is not None:
                maximum_daily_energy = Timeseries(bc.get_less_term_matrix())  # TODO

        thermal_name = dsr_config["thermal_name"]
        if thermal_name not in thermals:
            logger.warning(f"DSR cluster name {thermal_name} not found in thermals clusters, skipping")
            continue

        cluster = thermals[thermal_name]

        disponibility = cluster.get_series_matrix()[parameters.scenario - 1]  # TODO

        # Create variable cost timeseries
        variable_cost = Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=cluster.properties.marginal_cost,
        )

        # Create DSR equipment
        dsr_unit = Thermal(
            name=dsr_config["name"],
            node=atlas_dataset.get("node", "fr"),
            portfolio=atlas_dataset.get(
                "portfolio", "generator_fr" if parameters.consumption_production_separation else "portfolio_fr"
            ),
            has_daily_energy_constraint=dsr_config["has_daily_constraint"],
            maximum_daily_energy=maximum_daily_energy,
            maximum_power=disponibility,
            variable_cost=variable_cost,
            strategy=ThermalStrategy.PEAK,
        )

        dsr_units.append(dsr_unit)
        logger.debug(f"Created DSR unit: {dsr_config['name']}")

    return dsr_units


def _convert_dsr_other_country(
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    area: Area,
    binding_constraints: dict[str, BindingConstraint],
) -> Thermal | None:
    """Convert DSR unit for a non-France country."""

    # Look for binding constraint matching pattern: "dsr_{area_name}_stock"
    bc_name = f"dsr_{area.id}_stock"

    bc = binding_constraints.get(bc_name, None)

    if bc is not None:
        maximum_daily_energy = Timeseries(bc.get_less_term_matrix())

    thermal_name = f"{area.id}_{area.upper()}_DSR_0"

    thermals = area.get_thermals()

    if thermal_name not in thermals:
        logger.warning(f"Thermal cluster {thermal_name} not found for area {area.id}, skipping DSR")
        return None

    cluster = thermals[thermal_name]

    try:
        maximum_power_df = cluster.get_series_matrix()[parameters.scenario - 1]  # TODO
        if maximum_power_df.abs().max() == 0:
            return None
        maximum_power = Timeseries(maximum_power_df)
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
