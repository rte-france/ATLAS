"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.study import Study
from loguru import logger
from pendulum import duration

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.wind import Wind
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def convert_wind_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Convert Solar generation data from Antares to Atlas."""

    logger.info("Converting Winds generation data")
    areas = study.get_areas()
    winds: list[Wind] = []

    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue
        if study.get_settings().advanced_parameters.renewable_generation_modelling.value == "clusters":
            renewables = areas[area_name].get_renewables()
            for res_name in renewables:
                cluster_res = renewables[res_name]
                if cluster_res.properties.group == "wind onshore" and cluster_res.properties.enabled:
                    if parameters.scenario - 1 >= len(cluster_res.RenewablesSelectedScenario):  # TODO
                        continue

                    sc_wind = cluster_res.RenewablesSelectedScenario[parameters.scenario - 1]

                    if str(sc_wind) in cluster_res.Disponibility.Index:
                        if cluster_res.Disponibility[sc_wind].Abs().Max() > 0:
                            new_wind = Wind(
                                name=f"{area_name}_wind",
                                node=atlas_dataset.get("node", area_name),
                                portfolio=atlas_dataset.get(
                                    "portfolio",
                                    f"generator_{area_name}"
                                    if parameters.consumption_production_separation
                                    else f"portfolio_{area_name}",
                                ),
                                maximum_curtailment_ratio=Timeseries.from_index(
                                    start_date=parameters.start_date,
                                    frequency="1h",
                                    end_date=parameters.start_date + duration(years=1),
                                    default_value=parameters.wind_max_curtailment_ratio,
                                ),
                                curtailment_cost=Timeseries.from_index(
                                    start_date=parameters.start_date,
                                    frequency="1h",
                                    end_date=parameters.start_date + duration(years=1),
                                    default_value=parameters.wind_curtailment_cost,
                                ),
                                installed_capacity=cluster_res.properties.nominal_capacity,
                            )
                            offshore_instance = renewables.get(area_name + "_wind_offshore", None)

                            if offshore_instance is not None and area_name not in ["dekf", "dkkf"]:
                                if offshore_instance.properties.enabled:
                                    new_wind.installed_capacity += offshore_instance.properties.nominal_capacity

                winds.append(new_wind)
        else:
            if parameters.scenario - 1 >= len(antares_node.WindSelectedScenario):
                continue

            sc_wind = antares_node.WindSelectedScenario[parameters.scenario - 1]  # TODO

            if str(sc_wind) in areas[area_name].get_wind_matrix().index:
                if area_name.SolarProduction.Abs().Max() > 0:
                    winds.append(
                        Wind(
                            name=f"{area_name}_wind",
                            node=atlas_dataset.get("node", area_name),
                            portfolio=atlas_dataset.get(
                                "portfolio",
                                f"generator_{area_name}"
                                if parameters.consumption_production_separation
                                else f"portfolio_{area_name}",
                            ),
                            maximum_curtailment_ratio=Timeseries.from_index(
                                start_date=parameters.start_date,
                                frequency="1h",
                                end_date=parameters.start_date + duration(years=1),
                                default_value=parameters.pv_max_curtailment_ratio,
                            ),
                        )
                    )

    atlas_dataset.wind.add(winds)

    return atlas_dataset
