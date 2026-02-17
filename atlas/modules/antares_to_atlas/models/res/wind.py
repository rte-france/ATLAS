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
                if renewables[res_name].properties.group == "wind onshore" and renewables[res_name].properties.enabled:
                    if parameters.scenario - 1 >= len(instance.RenewablesSelectedScenario):  # TODO
                        continue

                    sc_wind = instance.RenewablesSelectedScenario[parameters.scenario - 1]

                    if str(sc_wind) in instance.Disponibility.Index:
                        if instance.Disponibility[sc_wind].Abs().Max() > 0:
                            solars.append(
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
                                    curtailment_cost=Timeseries.from_index(
                                        start_date=parameters.start_date,
                                        frequency="1h",
                                        end_date=parameters.start_date + duration(years=1),
                                        default_value=parameters.pv_curtailment_cost,
                                    ),
                                    installed_capacity=renewables[res_name].properties.nominal_capacity,
                                )
                            )

                            if antares_dataset.Renewables.CheckInstanceExists(
                                instance.Node.Name + "_wind_offshore"
                            ) and instance.Node.Name.lower() not in ["dekf", "dkkf"]:
                                offshore_instance = antares_dataset.Renewables.GetInstanceByName(
                                    instance.Node.Name + "_wind_offshore"
                                )

                                if offshore_instance.Enabled:
                                    wind.InstalledCapacity += offshore_instance.NominalCapacity
        else:
            if parameters.scenario - 1 >= len(antares_node.WindSelectedScenario):
                continue

            sc_wind = antares_node.WindSelectedScenario[parameters.scenario - 1]  # TODO

            if str(sc_wind) in antares_node.SolarProduction.Index:
                if antares_node.SolarProduction.Abs().Max() > 0:
                    solars.append(
                        Wind(
                            name=f"{area_name}_pv",
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
