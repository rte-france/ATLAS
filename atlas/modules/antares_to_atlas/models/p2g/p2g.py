"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from collections.abc import Mapping

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
from atlas.modules.antares_to_atlas.utils import get_portfolio
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

        p2g_base = _convert_p2g_base(
            area=area, parameters=parameters, atlas_dataset=atlas_dataset, links=links, study=study
        )
        if p2g_base:
            p2g_units.append(p2g_base)

        p2g_marg = _convert_p2g_marg(
            area=area, parameters=parameters, atlas_dataset=atlas_dataset, areas=areas, links=links, study=study
        )
        if p2g_marg:
            p2g_units.append(p2g_marg)

        # Process P2G methanation
        p2g_methanation = _convert_p2g_methanation(
            area=area, parameters=parameters, atlas_dataset=atlas_dataset, areas=areas, links=links, study=study
        )
        if p2g_methanation:
            p2g_units.append(p2g_methanation)

    atlas_dataset.load.add(p2g_units)

    return atlas_dataset


def _convert_p2g_base(
    area: Area,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    links: Mapping[str, Link],
    study: Study,
) -> Load | None:
    """Convert P2G base unit (fatal load)."""
    link_name = f"{area.id}_z_p2g_base"

    link = links.get(link_name, None)

    if not link:
        return None

    scenario = (
        study.get_output(parameters.output_name)
        .get_link_ts_numbers(link.area_from_id, link.area_to_id)
        .get(parameters.scenario, None)
    )
    if not scenario:
        logger.warning(f"No scenario found for P2G base link {link_name}, skipping")
        return None

    capacity_df = link.get_capacity_direct()[scenario - 1]
    if capacity_df.abs().max().max() == 0:
        return None

    capacity_ts = Timeseries.from_values(start_date=parameters.start_date, frequency="1h", values=capacity_df * -1.0)

    p2g_base = Load(
        name=f"{area.id}_p2g_base",
        node=atlas_dataset.get("node", area.id),
        portfolio=get_portfolio(atlas_dataset, parameters, area.id, role="supplier"),
        load_type=LoadType.OTHER_NON_DISPATCHABLE_LOAD,
        maximum_power_forecast=ForecastingMatrix().add(capacity_ts, parameters.execution_date, inplace=False),
    )

    logger.debug(f"Created P2G base unit for area: {area.id}")
    return p2g_base


def _convert_p2g_marg(
    area: Area,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    areas: Mapping[str, Area],
    links: Mapping[str, Link],
    study: Study,
) -> Load | None:
    """Convert P2G marginal unit (dispatchable load)."""
    link_name = f"{area.id}_z_p2g_marg"

    link = links.get(link_name, None)

    if not link:
        return None

    scenario = (
        study.get_output(parameters.output_name)
        .get_link_ts_numbers(link.area_from_id, link.area_to_id)
        .get(parameters.scenario, None)
    )

    if not scenario:
        logger.warning(f"No scenario found for P2G marg link {link_name}, skipping")
        return None

    capacity_df = link.get_capacity_direct()[scenario - 1]
    if capacity_df.abs().max().max() == 0:
        return None
    capacity_ts = Timeseries.from_values(start_date=parameters.start_date, frequency="1h", values=capacity_df * -1.0)

    thermal_name = "z_p2g_marg_z_P2G_marg_marg"
    _p2g_marg_tc = areas["z_p2g_marg"].get_thermals().get(thermal_name, None) if "z_p2g_marg" in areas else None
    variable_cost_value = _p2g_marg_tc.properties.market_bid_cost if _p2g_marg_tc is not None else 0.0

    variable_cost = Timeseries.from_index(
        start_date=parameters.start_date,
        frequency="1h",
        end_date=parameters.start_date + duration(years=1),
        default_value=variable_cost_value,
    )

    p2g_marg = Load(
        name=f"{area.id}_p2g_marg",
        node=atlas_dataset.get("node", area.id),
        portfolio=get_portfolio(atlas_dataset, parameters, area.id, role="supplier"),
        load_type=LoadType.POWER_TO_GAS,
        maximum_power_forecast=ForecastingMatrix().add(capacity_ts, parameters.execution_date, inplace=False),
        variable_cost=variable_cost,
    )

    logger.debug(f"Created P2G marginal unit for area: {area.id}")
    return p2g_marg


def _convert_p2g_methanation(
    area: Area,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
    areas: Mapping[str, Area],
    links: Mapping[str, Link],
    study: Study,
) -> Load | None:
    """Convert P2G methanation unit (dispatchable load)."""
    link_name = f"{area.id}_z_p2g_methanation"

    link = links.get(link_name, None)

    if not link:
        return None

    scenario = (
        study.get_output(parameters.output_name)
        .get_link_ts_numbers(link.area_from_id, link.area_to_id)
        .get(parameters.scenario, None)
    )

    if not scenario:
        logger.warning(f"No scenario found for P2G methanation link {link_name}, skipping")
        return None

    capacity_df = link.get_capacity_direct()[scenario - 1]
    if capacity_df.abs().max().max() == 0:
        return None

    capacity_ts = Timeseries.from_values(start_date=parameters.start_date, frequency="1h", values=capacity_df * -1.0)

    thermal_name = "z_p2g_methanation_z_P2G_methanation_methanation"
    _p2g_meth_tc = (
        areas["z_p2g_methanation"].get_thermals().get(thermal_name, None) if "z_p2g_methanation" in areas else None
    )
    variable_cost_value = _p2g_meth_tc.properties.market_bid_cost if _p2g_meth_tc is not None else 0.0

    variable_cost = Timeseries.from_index(
        start_date=parameters.start_date,
        frequency="1h",
        end_date=parameters.start_date + duration(years=1),
        default_value=variable_cost_value,
    )

    p2g_methanation = Load(
        name=f"{area.id}_p2g_methanation",
        node=atlas_dataset.get("node", area.id),
        portfolio=get_portfolio(atlas_dataset, parameters, area.id, role="supplier"),
        load_type=LoadType.POWER_TO_GAS,
        maximum_power_forecast=ForecastingMatrix().add(capacity_ts, parameters.execution_date, inplace=False),
        variable_cost=variable_cost,
    )

    logger.debug(f"Created P2G methanation unit for area: {area.id}")
    return p2g_methanation
