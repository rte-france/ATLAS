"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Literal

from antares.craft import ClusterData, Frequency, MCIndAreasDataType
from antares.craft.model.area import Area
from antares.craft.model.study import Study
from antares.craft.model.thermal import ThermalCluster
from loguru import logger

from atlas.core.io_utils.atlas_dataset import AtlasDataset
from atlas.core.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def get_portfolio(
    atlas_dataset: AtlasDataset,
    parameters: AntaresToAtlasParameters,
    area_id: str,
    role: Literal["generator", "supplier"] = "generator",
):
    """Resolve the portfolio for an area, honoring the consumption/production split.

    With consumption_production_separation: returns "{role}_{area_id}".
    Without: returns the unified "portfolio_{area_id}".
    """
    if parameters.consumption_production_separation:
        name = f"{role}_{area_id}"
    else:
        name = f"portfolio_{area_id}"
    return atlas_dataset.get("portfolio", name)


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
                if (
                    isinstance(term.data, ClusterData)
                    and term.data.area == area_id
                    and term.data.cluster == cluster_name
                ):
                    return term.weight
    except Exception as e:
        logger.warning(f"Could not search weight for cluster {area_id}/{cluster_name}: {e}")
        return None

    logger.warning(f"No binding constraint term found for cluster {area_id}/{cluster_name}")
    return None


def get_maximum_power(
    area: Area,
    thermal: ThermalCluster,
    parameters: AntaresToAtlasParameters,
    study: Study,
) -> Timeseries | None:
    """Get maximum power timeseries for a thermal cluster.

    Tries to use the pre-computed Disponibility time series for the selected scenario.
    Falls back to computing from NominalCapacity * UnitCount * CapacityModulation * (1 - FORate) * (1 - PORate).
    Returns None if the resulting timeseries is all zeros.
    """
    try:
        scenario = (
            study.get_output(parameters.output_name)
            .get_thermal_ts_numbers(area.id, thermal.id)
            .get(parameters.scenario, None)
        )
        if scenario is None:
            raise ValueError(f"Scenario {parameters.scenario} not found for thermal {thermal.id} in area {area.id}")
        maximum_power_ts = Timeseries.from_values(
            start_date=parameters.start_date,
            frequency="1h",
            values=thermal.get_series_matrix()[scenario - 1],
        )

    except Exception:
        logger.debug(f"Falling back to computed maximum power for {getattr(thermal, 'name', thermal)}")
        capacity_mod = thermal.get_prepro_modulation_matrix()[2].reset_index(drop=True)  # 8760 hourly
        prepro = thermal.get_prepro_data_matrix()
        # FO/PO rates are daily (365 rows) — expand to hourly by repeating each day 24 times
        fo_rate = prepro[parameters.output.FORate].repeat(24).reset_index(drop=True)
        po_rate = prepro[parameters.output.PORate].repeat(24).reset_index(drop=True)
        # Align lengths to modulation series length
        n = len(capacity_mod)
        fo_rate = fo_rate.iloc[:n]
        po_rate = po_rate.iloc[:n]
        default_value = (
            thermal.properties.nominal_capacity
            * thermal.properties.unit_count
            * capacity_mod
            * (1 - fo_rate)
            * (1 - po_rate)
        )
        maximum_power_ts = Timeseries.from_values(
            start_date=parameters.start_date,
            frequency="1h",
            values=default_value.to_list(),
        )

    if maximum_power_ts.abs().max() == 0.0:
        return None

    return maximum_power_ts


def get_variable_cost(thermal: ThermalCluster, parameters: AntaresToAtlasParameters) -> Timeseries:
    """Get variable cost timeseries.

    Prefers MarketBidCost * MarketBidModulation if MarketBidCost > 0,
    otherwise falls back to MarginalCost * MarginalCostModulation.
    """
    if thermal.properties.market_bid_cost > 0:
        return Timeseries.from_values(
            parameters.start_date,
            frequency="1h",
            values=(thermal.get_prepro_modulation_matrix()[1] * thermal.properties.market_bid_cost),
        )
    else:
        return Timeseries.from_values(
            parameters.start_date,
            frequency="1h",
            values=(thermal.get_prepro_modulation_matrix()[0] * thermal.properties.marginal_cost),
        )


def get_marginal_price(
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

    series = study.get_output(parameters.output_name).get_mc_ind_area(
        mc_year=parameters.scenario, frequency=Frequency.HOURLY, data_type=MCIndAreasDataType.VALUES, area=node_name
    )[("MRG. PRICE", "Euro")]
    return Timeseries.from_values(start_date=parameters.start_date, frequency="1h", values=series.to_list())


def get_binding_constraint_for_phs(study: Study, area_id: str) -> tuple[float, float]:
    """Get charge and discharge efficiency from binding constraint for closed PHS.

    Returns:
        tuple: (charge_efficiency, discharge_efficiency)
    """
    weight = get_weight_for_cluster(study, area_id, "phs_closed_inj")
    if weight is not None:
        return weight, 1.0 / weight
    return 1.0, 1.0


def get_nuclear_modulation_factor(study: Study, thermal_name: str) -> float | None:
    """Get nuclear modulation factor from binding constraint 'nuc_modulation_daily'.

    Returns abs(weights[5]) of the binding constraint, or None if not found.
    """
    weights = get_cluster_weights_from_bc(study, "nuc_modulation_daily")
    if not weights:
        return None

    return weights.get(thermal_name, None)
