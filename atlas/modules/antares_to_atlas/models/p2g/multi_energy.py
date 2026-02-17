"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.study import Study
from loguru import logger

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


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

    Note: P2G unit variable costs are also updated here (TODO).
    """
    logger.info("Updating variable costs for gas-consuming thermal units")

    if not atlas_dataset.thermal:
        logger.debug("No thermal equipment found, skipping multi-energy variable cost update")
        return atlas_dataset

    # Get marginal prices from virtual nodes v_me_h2 and v_me_ch4
    marginal_price_h2 = _get_marginal_price(study, "v_me_h2", parameters)
    marginal_price_ch4 = _get_marginal_price(study, "v_me_ch4", parameters)

    # Get CH4 and H2 thermal cluster lists with their yield weights from binding constraints
    ch4_yields = _get_yields_from_binding_constraint(study, "me_prod_ch4")
    h2_yields = _get_yields_from_binding_constraint(study, "me_prod_h2")

    # Update CH4 thermal units
    if marginal_price_ch4 is not None:
        for thermal_name in ch4_yields:
            equipment = next((t for t in atlas_dataset.thermal if t.name == thermal_name), None)
            if equipment is None:
                # Unit not in selected market areas — skip silently
                continue

            logger.info(f"Adding CH4 variable cost to thermal: {thermal_name}")
            # TODO: Verify multiplication of Timeseries by scalar
            # In old code: marginal_price_ch4 * yield_ch4 (Timeseries * float)
            # equipment.variable_cost = marginal_price_ch4 * ch4_yields[thermal_name]

    # Update H2 thermal units
    if marginal_price_h2 is not None:
        for thermal_name in h2_yields:
            equipment = next((t for t in atlas_dataset.thermal if t.name == thermal_name), None)
            if equipment is None:
                continue

            logger.info(f"Adding H2 variable cost to thermal: {thermal_name}")
            # TODO: Verify multiplication of Timeseries by scalar
            # In old code: marginal_price_h2 * yield_h2 (Timeseries * float)
            # equipment.variable_cost = marginal_price_h2 * h2_yields[thermal_name]

    # TODO: Update variable cost for P2G units
    # For p2g_marg units:
    #   yield = get_yield_electrolysers(study, area_name)  (from p2g.py)
    #   p2g_marg.variable_cost = marginal_price_h2 * yield
    # For p2g_methanation units:
    #   yield = get_yield_methanation(study, area_name)    (from p2g.py)
    #   p2g_methanation.variable_cost = marginal_price_ch4 * yield
    # See old code comment lines 58-65 and p2g_main.py

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

    try:
        # TODO: Verify how to get CalculatedMarginalPrice from an area
        # In old code: antares_dataset.Node.GetInstanceByName(node_name).CalculatedMarginalPrice[str(p.scenario)]
        # May need: areas[node_name].get_calculated_marginal_price(str(parameters.scenario))
        logger.debug(f"TODO: Get CalculatedMarginalPrice for {node_name}, scenario {parameters.scenario}")
        return None  # TODO

    except Exception as e:
        logger.warning(f"Could not get marginal price for node {node_name}: {e}")
        return None


def _get_yields_from_binding_constraint(study: Study, bc_name: str) -> dict[str, float]:
    """Get thermal cluster names and their yield weights from a binding constraint.

    Returns dict[thermal_cluster_name, yield_weight].

    :param bc_name: Binding constraint name (e.g. "me_prod_ch4", "me_prod_h2")
    """
    binding_constraints = study.get_binding_constraints()

    # TODO: Verify if binding constraints are indexed by name or ID
    bc = None
    for bc_id, bc_obj in binding_constraints.items():
        if bc_name.lower() in bc_id.lower():
            bc = bc_obj
            break

    if bc is None:
        logger.warning(f"Binding constraint {bc_name} not found")
        return {}

    try:
        # TODO: Extract cluster names and weights from binding constraint terms
        # In old code:
        #   list_clusterlist = [cluster.Name for cluster in bc.ClusterList]
        #   yield = bc.Weights[list_clusterlist.index(thermal_name)]
        # May need to use bc.get_terms() and look for cluster-type terms
        # terms = bc.get_terms()
        logger.debug(f"TODO: Extract cluster list and weights from binding constraint {bc_name}")
        return {}  # TODO

    except Exception as e:
        logger.warning(f"Could not get yields from binding constraint {bc_name}: {e}")
        return {}
