"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft import Frequency, MCIndAreasDataType
from antares.craft.model.study import Study
from loguru import logger

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.modules.antares_to_atlas.utils import get_cluster_weights_from_bc


def update_variable_cost_for_gas_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Update variable costs for thermal units that use H2 or CH4 as fuel.

    In a multi-energy system, some thermal units consume H2 or CH4 whose price
    is computed endogenously by Antares (via virtual nodes v_me_h2 and v_me_ch4).
    Their variable cost must be overridden with:
        variable_cost = marginal_price_of_gas * yield_factor

    The yield factor (already inversed, i.e. > 1) comes from binding constraints:
    - "me_prod_ch4": lists CH4-consuming thermals and their yield weights
    - "me_prod_h2":  lists H2-consuming thermals and their yield weights
    """
    logger.info("Updating variable costs for gas-consuming thermal units")

    if not atlas_dataset.thermal:
        logger.debug("No thermal equipment found, skipping multi-energy variable cost update")
        return atlas_dataset

    marginal_price_h2 = _get_marginal_price(study, "v_me_h2", parameters)
    marginal_price_ch4 = _get_marginal_price(study, "v_me_ch4", parameters)

    ch4_yields = get_cluster_weights_from_bc(study, "me_prod_ch4")
    h2_yields = get_cluster_weights_from_bc(study, "me_prod_h2")

    if marginal_price_ch4 is not None:
        for thermal_name in ch4_yields:
            equipment = next((t for t in atlas_dataset.thermal if t.name == thermal_name), None)
            if equipment is None:
                continue

            logger.info(f"Adding CH4 variable cost to thermal: {thermal_name}")

            equipment.variable_cost = Timeseries.from_values(
                start_date=parameters.start_date, frequency="1h", values=marginal_price_ch4 * ch4_yields[thermal_name]
            )

    # Update H2 thermal units
    if marginal_price_h2 is not None:
        for thermal_name in h2_yields:
            equipment = next((t for t in atlas_dataset.thermal if t.name == thermal_name), None)
            if equipment is None:
                continue

            logger.info(f"Adding H2 variable cost to thermal: {thermal_name}")
            equipment.variable_cost = Timeseries.from_values(
                start_date=parameters.start_date, frequency="1h", values=marginal_price_h2 * h2_yields[thermal_name]
            )

    logger.info("Variable cost update for gas units done")
    return atlas_dataset


def _get_marginal_price(
    study: Study,
    node_name: str,
    parameters: AntaresToAtlasParameters,
) -> Timeseries | None:
    """Get the calculated marginal price time series for a virtual node.

    :param node_name: Virtual node name (e.g. "v_me_h2", "v_me_ch4")
    :param parameters: Conversion parameters (used to select the scenario)
    :return: Marginal price Timeseries, or None if not found
    """
    areas = study.get_areas()

    if node_name not in areas:
        logger.warning(f"Virtual node {node_name} not found in study")
        return None

    return study.get_output(parameters.output_name).get_mc_ind_area(
        mc_year=parameters.scenario, frequency=Frequency.HOURLY, data_type=MCIndAreasDataType.VALUES, area=node_name
    )[("MRG. PRICE", "Euro")]
