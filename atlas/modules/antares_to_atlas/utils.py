"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft import ClusterData
from antares.craft.model.study import Study
from loguru import logger


def get_cluster_weights_from_bc(study: Study, bc_name: str) -> dict[str, float]:
    """Get thermal cluster names and their weights from a binding constraint.

    Returns dict[cluster_name, weight].
    """
    binding_constraints = study.get_binding_constraints()
    bc = binding_constraints.get(bc_name, None)
    if bc is None:
        logger.warning(f"Binding constraint {bc_name} not found")
        return {}

    try:
        weights: dict[str, float] = {}
        for term in bc.get_terms().values():
            if isinstance(term.data, ClusterData):
                weights[term.data.cluster] = term.weight
        return weights
    except Exception as e:
        logger.warning(f"Could not get weights from binding constraint {bc_name}: {e}")
        return {}


def get_weight_for_cluster(study: Study, area_id: str, cluster_name: str) -> float | None:
    """Search all binding constraints for a term matching the given area and cluster, and return its weight.

    Returns None if no matching term is found.
    """
    try:
        for bc in study.get_binding_constraints().values():
            for term in bc.get_terms().values():
                if isinstance(term.data, ClusterData) and term.data.area == area_id and term.data.cluster == cluster_name:
                    return term.weight
    except Exception as e:
        logger.warning(f"Could not search weight for cluster {area_id}/{cluster_name}: {e}")
        return None

    logger.warning(f"No binding constraint term found for cluster {area_id}/{cluster_name}")
    return None
