"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.area import Area
from antares.craft.model.link import Link
from antares.craft.model.study import Study
from loguru import logger
from pendulum import duration

from atlas.enums import LoadType
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.objects.equipment.load import Load


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
            parameters=parameters,
            atlas_dataset=atlas_dataset,
            links=links,
        )
        if p2g_base:
            p2g_units.append(p2g_base)

        # Process P2G marginal
        p2g_marg = _convert_p2g_marg(
            area=area,
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
            parameters=parameters,
            atlas_dataset=atlas_dataset,
            areas=areas,
            links=links,
        )
        if p2g_methanation:
            p2g_units.append(p2g_methanation)

    atlas_dataset.load.add(p2g_units)

    return atlas_dataset


def _convert_p2g_base(
    area: Area,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    links: dict[str, Link],
) -> Load | None:
    """Convert P2G base unit (fatal load)."""
    link_name = f"{area.id}_z_p2g_base"

    link = links.get(link_name, None)

    if not link:
        return None

    try:
        capacity_df = link.get_capacity_direct()  # TODO link.DirectTransferCapacity.GetTimeSeriesByName("1")
        # refaire le truc de choper l'index du scenario basé sur SelectedScenario
        if capacity_df.abs().max().max() == 0:
            return None

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
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    areas: dict[str, Area],
    links: dict[str, Link],
) -> Load | None:
    """Convert P2G marginal unit (dispatchable load)."""
    link_name = f"{area.id}_z_p2g_marg"

    link = links.get(link_name, None)

    if not link:
        return None

    try:
        capacity_df = link.get_capacity_direct()  # TODO
        if capacity_df.abs().max().max() == 0:
            return None

        capacity_ts = Timeseries(capacity_df * -1.0)
    except Exception as e:
        logger.warning(f"Could not get capacity for link {link_name}: {e}")
        return None

    thermal_name = "z_p2g_marg_z_P2G_marg_marg"
    variable_cost_value = (
        areas["z_p2g_marg"].get_thermals().get(thermal_name, None).properties.market_bid_cost
        if "z_p2g_marg" in areas
        else 0.0
    )

    variable_cost = Timeseries.from_index(
        start_date=parameters.start_date,
        frequency="1h",
        end_date=parameters.start_date + duration(years=1),
        default_value=variable_cost_value,
    )

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
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    areas: dict[str, Area],
    links: dict[str, Link],
) -> Load | None:
    """Convert P2G methanation unit (dispatchable load)."""
    link_name = f"{area.id}_z_p2g_methanation"

    link = links.get(link_name, None)

    if not link:
        return None

    try:
        capacity_df = link.get_capacity_direct()  # TODO
        if capacity_df.abs().max().max() == 0:
            return None

        capacity_ts = Timeseries(capacity_df * -1.0)
    except Exception as e:
        logger.warning(f"Could not get capacity for link {link_name}: {e}")
        return None

    thermal_name = "z_p2g_methanation_z_P2G_methanation_methanation"
    variable_cost_value = (
        areas["z_p2g_methanation"].get_thermals().get(thermal_name, None).properties.market_bid_cost
        if "z_p2g_methanation" in areas
        else 0.0
    )

    variable_cost = Timeseries.from_index(
        start_date=parameters.start_date,
        frequency="1h",
        end_date=parameters.start_date + duration(years=1),
        default_value=variable_cost_value,
    )

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
