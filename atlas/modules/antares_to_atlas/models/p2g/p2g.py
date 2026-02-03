"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.area import Area
from antares.craft.model.link import Link
from antares.craft.model.study import Study
from loguru import logger
from pendulum import duration

from atlas.enum import LoadType
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.load import Load
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def convert_p2g_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Convert Power-to-Gas (P2G) technologies from Antares to Atlas Load equipment.

    P2G units are modeled as Load equipment with three types:
    - base: OtherNonDispatchableLoad (100% fatal)
    - marg: PowerToGas (dispatchable with variable cost)
    - methanation: PowerToGas (dispatchable with variable cost)
    """
    logger.info("Converting P2G units")

    areas = study.get_areas()
    links = study.get_links()
    p2g_units: list[Load] = []

    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        area = areas[area_name]
        logger.debug(f"Processing P2G units for area {area.id}")

        # Process P2G base
        p2g_base = _convert_p2g_base(
            area=area,
            study=study,
            parameters=parameters,
            atlas_dataset=atlas_dataset,
            links=links,
        )
        if p2g_base:
            p2g_units.append(p2g_base)

        # Process P2G marginal
        p2g_marg = _convert_p2g_marg(
            area=area,
            study=study,
            parameters=parameters,
            atlas_dataset=atlas_dataset,
            areas=areas,
            links=links,
        )
        if p2g_marg:
            p2g_units.append(p2g_marg)

        # Process P2G methanation
        p2g_methanation = _convert_p2g_methanation(
            area=area,
            study=study,
            parameters=parameters,
            atlas_dataset=atlas_dataset,
            areas=areas,
            links=links,
        )
        if p2g_methanation:
            p2g_units.append(p2g_methanation)

    atlas_dataset.load = getattr(atlas_dataset, "load", []) + p2g_units

    return atlas_dataset


def _convert_p2g_base(
    area: Area,
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    links: dict[str, Link],
) -> Load | None:
    """Convert P2G base unit (fatal load)."""
    link_name = f"{area.id}_z_p2g_base"

    # TODO: Verify if links are indexed by name or by ID
    # May need to search through links to find matching area_from and area_to
    link = None
    for link_id, link_obj in links.items():
        # Check if this link connects area.id to z_p2g_base
        # TODO: Verify the correct way to check link endpoints
        if link_name.lower() in link_id.lower():
            link = link_obj
            break

    if not link:
        return None

    # Get direct transfer capacity
    # TODO: Verify the correct method to get capacity time series
    # In old code: link.DirectTransferCapacity.GetTimeSeriesByName("1")
    try:
        capacity_df = link.get_capacity_direct()
        # TODO: Check if capacity is non-zero
        # In old code: .Abs().Max() != 0
        if capacity_df.abs().max().max() == 0:
            return None

        # Convert to Timeseries and invert sign (load is negative)
        # TODO: Verify correct conversion from DataFrame to Timeseries
        capacity_ts = Timeseries(capacity_df * -1.0)
    except Exception as e:
        logger.warning(f"Could not get capacity for link {link_name}: {e}")
        return None

    p2g_base = Load(
        name=f"{area.id}_p2g_base",
        node=atlas_dataset.get("node", area.id),
        portfolio=atlas_dataset.get(
            "portfolio",
            f"supplier_{area.id}" if parameters.consumption_production_separation else f"portfolio_{area.id}",
        ),
        load_type=LoadType.OTHER_NON_DISPATCHABLE_LOAD,
        maximum_power_forecast=ForecastingMatrix().add(parameters.execution_date, capacity_ts),
    )

    logger.debug(f"Created P2G base unit for area: {area.id}")
    return p2g_base


def _convert_p2g_marg(
    area: Area,
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    areas: dict[str, Area],
    links: dict[str, Link],
) -> Load | None:
    """Convert P2G marginal unit (dispatchable load)."""
    link_name = f"{area.id}_z_p2g_marg"

    # TODO: Verify if links are indexed by name or by ID
    link = None
    for link_id, link_obj in links.items():
        if link_name.lower() in link_id.lower():
            link = link_obj
            break

    if not link:
        return None

    # Get direct transfer capacity
    try:
        capacity_df = link.get_capacity_direct()
        if capacity_df.abs().max().max() == 0:
            return None

        # Convert to Timeseries and invert sign (load is negative)
        capacity_ts = Timeseries(capacity_df * -1.0)
    except Exception as e:
        logger.warning(f"Could not get capacity for link {link_name}: {e}")
        return None

    # Get variable cost from thermal technology
    # TODO: Verify how to access thermal clusters from z_p2g_marg area
    # In old code: antares_dataset.ThermalTechnology.GetInstanceByName("z_p2g_marg_z_P2G_marg_marg")
    thermal_name = "z_p2g_marg_z_P2G_marg_marg"
    variable_cost_value = 0.0

    # TODO: Need to access thermal cluster from the z_p2g_marg area
    # This might require accessing areas["z_p2g_marg"].get_thermals() if that area exists
    if "z_p2g_marg" in areas:
        thermals = areas["z_p2g_marg"].get_thermals()
        # TODO: The thermal name might need different formatting
        for thermal_key, thermal_obj in thermals.items():
            if "p2g_marg" in thermal_key.lower():
                # TODO: Verify how to access MarketBidCost
                variable_cost_value = thermal_obj.properties.market_bid_cost
                break

    # Create variable cost timeseries
    variable_cost = Timeseries.from_index(
        start_date=parameters.start_date,
        frequency="1h",
        end_date=parameters.start_date + duration(years=1),
        default_value=variable_cost_value,
    )

    # Determine portfolio

    # Create P2G marginal equipment
    p2g_marg = Load(
        name=f"{area.id}_p2g_marg",
        node=atlas_dataset.get("node", area.id),
        portfolio=atlas_dataset.get(
            "portfolio",
            f"supplier_{area.id}" if parameters.consumption_production_separation else f"portfolio_{area.id}",
        ),
        load_type=LoadType.POWER_TO_GAS,
        maximum_power_forecast=ForecastingMatrix().add(parameters.execution_date, capacity_ts),
        variable_cost=variable_cost,
    )

    logger.debug(f"Created P2G marginal unit for area: {area.id}")
    return p2g_marg


def _convert_p2g_methanation(
    area: Area,
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    areas: dict[str, Area],
    links: dict[str, Link],
) -> Load | None:
    """Convert P2G methanation unit (dispatchable load)."""
    link_name = f"{area.id}_z_p2g_methanation"

    # TODO: Verify if links are indexed by name or by ID
    link = None
    for link_id, link_obj in links.items():
        if link_name.lower() in link_id.lower():
            link = link_obj
            break

    if not link:
        return None

    # Get direct transfer capacity
    try:
        capacity_df = link.get_capacity_direct()
        if capacity_df.abs().max().max() == 0:
            return None

        # Convert to Timeseries and invert sign (load is negative)
        capacity_ts = Timeseries(capacity_df * -1.0)
    except Exception as e:
        logger.warning(f"Could not get capacity for link {link_name}: {e}")
        return None

    # Get variable cost from thermal technology
    thermal_name = "z_p2g_methanation_z_P2G_methanation_methanation"
    variable_cost_value = 0.0

    # TODO: Need to access thermal cluster from the z_p2g_methanation area
    if "z_p2g_methanation" in areas:
        thermals = areas["z_p2g_methanation"].get_thermals()
        for thermal_key, thermal_obj in thermals.items():
            if "p2g_methanation" in thermal_key.lower() or "methanation" in thermal_key.lower():
                # TODO: Verify how to access MarketBidCost
                variable_cost_value = getattr(thermal_obj.properties, "market_bid_cost", 0.0)
                break

    # Create variable cost timeseries
    variable_cost = Timeseries.from_index(
        start_date=parameters.start_date,
        frequency="1h",
        end_date=parameters.start_date + duration(years=1),
        default_value=variable_cost_value,
    )

    # Create P2G methanation equipment
    p2g_methanation = Load(
        name=f"{area.id}_p2g_methanation",
        node=atlas_dataset.get("node", area.id),
        portfolio=atlas_dataset.get(
            "portfolio",
            f"supplier_{area.id}" if parameters.consumption_production_separation else f"portfolio_{area.id}",
        ),
        load_type=LoadType.POWER_TO_GAS,
        maximum_power_forecast=ForecastingMatrix().add(parameters.execution_date, capacity_ts),
        variable_cost=variable_cost,
    )

    logger.debug(f"Created P2G methanation unit for area: {area.id}")
    return p2g_methanation


def get_yield_electrolysers(
    study: Study,
    area_name: str,
) -> float:
    """Get yield of electrolysers from binding constraint.

    TODO: This function needs verification. In the original code, it searches for
    the yield in the binding constraint weights. Need to verify:
    - How to access binding constraint terms and weights in new API
    - The correct binding constraint name and structure
    """
    binding_constraints = study.get_binding_constraints()

    # TODO: Verify binding constraint name access (by name vs ID)
    bc_name = "me_p2g_base"
    if bc_name not in binding_constraints:
        logger.warning(f"Binding constraint {bc_name} not found")
        return 1.0

    bc = binding_constraints[bc_name]

    # TODO: Verify how to access constraint terms and weights
    # In old code: bc.LinkList and bc.Weights
    # Need to find the link corresponding to {area_name}_z_p2g_base and get its weight
    try:
        terms = bc.get_terms()
        link_id = f"{area_name}_z_p2g_base"
        # TODO: The term ID format might be different
        # May need to search through terms to find the matching one
        for term_id, term in terms.items():
            if link_id.lower() in term_id.lower():
                return term.weight
    except Exception as e:
        logger.warning(f"Could not get yield for electrolysers in area {area_name}: {e}")

    return 1.0


def get_yield_methanation(
    study: Study,
    area_name: str,
) -> float:
    """Get yield of methanation from binding constraint.

    TODO: This function needs verification. Similar to get_yield_electrolysers.
    """
    binding_constraints = study.get_binding_constraints()

    # TODO: Verify binding constraint name access (by name vs ID)
    bc_name = "me_p2g_methanation"
    if bc_name not in binding_constraints:
        logger.warning(f"Binding constraint {bc_name} not found")
        return 1.0

    bc = binding_constraints[bc_name]

    # TODO: Verify how to access constraint terms and weights
    try:
        terms = bc.get_terms()
        link_id = f"{area_name}_z_p2g_methanation"
        for term_id, term in terms.items():
            if link_id.lower() in term_id.lower():
                return term.weight
    except Exception as e:
        logger.warning(f"Could not get yield for methanation in area {area_name}: {e}")

    return 1.0
