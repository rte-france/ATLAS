"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.area import Area
from antares.craft.model.binding_constraint import BindingConstraint
from antares.craft.model.study import Study
from loguru import logger
from pendulum import duration

from atlas.enum import ThermalStrategy
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
            study=study,
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
    study: Study,
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
        # Get maximum daily energy from binding constraint (if applicable)
        maximum_daily_energy = None
        if dsr_config["bc_name"]:
            bc_name = dsr_config["bc_name"]
            # TODO: Verify the correct way to access binding constraint by name
            # The binding_constraints dict might use IDs instead of names
            if bc_name in binding_constraints:
                bc = binding_constraints[bc_name]
                # TODO: Verify that get_less_term_matrix() is the correct method
                # to get the MaximumDailyEnergy time series
                maximum_daily_energy_df = bc.get_less_term_matrix()
                # TODO: Convert DataFrame to Timeseries - need to verify the correct approach
                maximum_daily_energy = Timeseries(maximum_daily_energy_df)

        # Get thermal cluster data
        thermal_name = dsr_config["thermal_name"]
        if thermal_name not in thermals:
            logger.warning(f"DSR cluster name {thermal_name} not found in thermals clusters, skipping")
            continue

        cluster = thermals[thermal_name]

        # TODO: Verify how to get availability time series for a specific scenario
        # In the old code: dsr_instance_antares.Disponibility[str(p.scenario)]
        # Need to find equivalent in new API
        try:
            # TODO: This is a placeholder - need to verify correct way to get scenario-specific availability
            maximum_power_df = cluster.get_prepro_modulation_matrix()
            # TODO: Extract the specific scenario column
            # maximum_power = Timeseries(maximum_power_df[parameters.scenario - 1])
            maximum_power = None  # Placeholder until TODO is resolved
        except Exception as e:
            logger.warning(f"Could not get availability for {thermal_name}: {e}")
            maximum_power = None

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
            maximum_power=maximum_power,
            variable_cost=variable_cost,
            strategy=ThermalStrategy.PEAK,
        )

        dsr_units.append(dsr_unit)
        logger.debug(f"Created DSR unit: {dsr_config['name']}")

    return dsr_units


def _convert_dsr_other_country(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    area: Area,
    binding_constraints: dict[str, BindingConstraint],
) -> Thermal | None:
    """Convert DSR unit for a non-France country."""

    # Look for binding constraint matching pattern: "dsr_{area_name}_stock"
    bc_name = f"dsr_{area.id}_stock"

    # TODO: Verify if binding constraints are indexed by name or by ID
    # May need to use transform_name_to_id(bc_name) to get the ID
    if bc_name not in binding_constraints:
        # No DSR binding constraint for this area
        return None

    bc = binding_constraints[bc_name]

    # Get maximum daily energy from binding constraint
    # TODO: Verify that get_less_term_matrix() returns the correct time series
    maximum_daily_energy_df = bc.get_less_term_matrix()
    # TODO: Convert DataFrame to Timeseries
    maximum_daily_energy = Timeseries(maximum_daily_energy_df)

    # Get thermal cluster name - uses special formatting
    # TODO: Verify the node_special_format function is available or needed
    # In old code: f"{node.Name}_{functions.node_special_format(node.Name)}_DSR_0"
    # For now, trying simplified pattern
    thermal_name = f"{area.id}_{area.upper()}_DSR_0"

    thermals = area.get_thermals()

    if thermal_name not in thermals:
        logger.warning(f"Thermal cluster {thermal_name} not found for area {area.id}, skipping DSR")
        return None

    cluster = thermals[thermal_name]

    # TODO: Verify how to get availability time series for specific scenario
    try:
        # TODO: This is a placeholder - need to verify correct way to get scenario-specific availability
        maximum_power_df = cluster.get_prepro_modulation_matrix()
        # TODO: Extract the specific scenario and check if it's non-zero
        # In old code, we skip if Abs().Max() == 0.0
        # maximum_power = Timeseries(maximum_power_df[parameters.scenario - 1])
        maximum_power = None  # Placeholder until TODO is resolved

        # TODO: Check if maximum power is zero before creating equipment
        # if maximum_power.abs().max() == 0.0:
        #     return None
    except Exception as e:
        logger.warning(f"Could not get availability for {thermal_name}: {e}")
        return None

    # Get marginal cost
    # TODO: Verify how to access marginal_cost from thermal cluster properties
    marginal_cost = cluster.properties.marginal_cost if hasattr(cluster.properties, "marginal_cost") else 0.0

    # Create variable cost timeseries
    variable_cost = Timeseries.from_index(
        start_date=parameters.start_date,
        frequency="1h",
        end_date=parameters.start_date + duration(years=1),
        default_value=marginal_cost,
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
