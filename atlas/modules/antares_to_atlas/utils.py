"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft import ClusterData, Frequency, MCIndAreasDataType
from antares.craft.model.area import Area
from antares.craft.model.study import Study
from antares.craft.model.thermal import ThermalCluster
from loguru import logger

from atlas.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


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
) -> Timeseries | None:
    """Get maximum power timeseries for a thermal cluster.

    Tries to use the pre-computed Disponibility time series for the selected scenario.
    Falls back to computing from NominalCapacity * UnitCount * CapacityModulation * (1 - FORate) * (1 - PORate).
    Returns None if the resulting timeseries is all zeros.
    """
    try:
        # TODO: Verify how to get ThermalSelectedScenario and Disponibility
        # In old code:
        #   sc = antares_thermal.ThermalSelectedScenario[p.scenario - 1]
        #   maximum_power_ts = antares_thermal.Disponibility[sc - 1]
        maximum_power_ts = None  # TODO

        if maximum_power_ts is None:
            raise ValueError("Disponibility not available")

    except Exception:
        default_value = (
            thermal.properties.nominal_capacity
            * thermal.properties.unit_count
            * thermal.get_prepro_modulation_matrix()[2]  # Capacity Modulation
            * (1 - thermal.get_prepro_data_matrix()[2])  # FORate
            * (1 - thermal.get_prepro_data_matrix()[3])  # PORate
        )

        logger.debug(f"Falling back to computed maximum power for {getattr(thermal, 'name', thermal)}")
        maximum_power_ts = Timeseries.from_values(
            start_date=parameters.start_date,
            frequency="1h",
            values=default_value,
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
            values=thermal.get_prepro_modulation_matrix()[1],  # MarketBidModulation
        )
    else:
        return Timeseries.from_values(
            parameters.start_date,
            frequency="1h",
            values=thermal.get_prepro_modulation_matrix()[0],  # MarginalCostModulation
        )


def get_co2_factor(
    thermal: ThermalCluster,
    thermal_group: str,
    parameters: AntaresToAtlasParameters,
) -> float | None:
    """Get CO2 emission factor.

    Uses antares CO2 field if non-zero, otherwise looks up by group from
    parameters.co2_emission_factors.
    """
    co2_value = thermal.properties.co2
    if co2_value != 0.0:
        return co2_value

    factor = parameters.co2_emission_factors.get(thermal_group)
    if factor is None:
        logger.warning(f"Thermal {thermal.name}: group '{thermal_group}' has no CO2 factor configured.")
    return factor


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

    return study.get_output(parameters.output_name).get_mc_ind_area(
        mc_year=parameters.scenario, frequency=Frequency.HOURLY, data_type=MCIndAreasDataType.VALUES, area=node_name
    )[("MRG. PRICE", "Euro")]


def get_binding_constraint_for_phs(study: Study, area_id: str) -> tuple[float, float]:
    """Get charge and discharge efficiency from binding constraint for closed PHS.

    Returns:
        tuple: (charge_efficiency, discharge_efficiency)
    """
    weight = get_weight_for_cluster(study, area_id, "phs_closed_inj")
    if weight is not None:
        return weight, 1.0 / weight
    return 1.0, 1.0


def get_nuclear_modulation_factor(study: Study) -> float | None:
    """Get nuclear modulation factor from binding constraint 'nuc_modulation_daily'.

    Returns abs(weights[5]) of the binding constraint, or None if not found.
    """
    weights = get_cluster_weights_from_bc(study, "nuc_modulation_daily")
    if not weights:
        return None

    values = list(weights.values())
    if len(values) <= 5:
        logger.warning(f"nuc_modulation_daily has only {len(values)} terms, expected at least 6")
        return None

    return abs(values[5])
