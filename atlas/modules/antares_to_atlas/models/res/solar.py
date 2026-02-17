"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.study import Study
from loguru import logger
from pendulum import duration

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.solar import Solar
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def convert_solar_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Convert Solar generation data from Antares to Atlas."""

    logger.info("Converting Solar generation data")
    areas = study.get_areas()
    solars: list[Solar] = []

    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue
        if study.get_settings().advanced_parameters.renewable_generation_modelling.value == "clusters":
            renewables = areas[area_name].get_renewables()
            for res_name in renewables:
                if renewables[res_name].properties.group == "solar pv" and renewables[res_name].properties.enabled:
                    if parameters.scenario - 1 >= len(instance.RenewablesSelectedScenario):  # TODO
                        continue

                    sc_solar = instance.RenewablesSelectedScenario[parameters.scenario - 1]

                    if str(sc_solar) in instance.Disponibility.Index:
                        if instance.Disponibility[sc_solar].Abs().Max() > 0:
                            solars.append(
                                Solar(
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
                                    curtailment_cost=Timeseries.from_index(
                                        start_date=parameters.start_date,
                                        frequency="1h",
                                        end_date=parameters.start_date + duration(years=1),
                                        default_value=parameters.pv_curtailment_cost,
                                    ),
                                    installed_capacity=renewables[res_name].properties.nominal_capacity,
                                )
                            )

                            if antares_dataset.Renewables.CheckInstanceExists(instance.Node.Name + "_solar_thermo"):
                                thermo_instance = antares_dataset.Renewables.GetInstanceByName(
                                    instance.Node.Name + "_solar_thermo"
                                )

                                if thermo_instance.Enabled:
                                    pv.InstalledCapacity += thermo_instance.NominalCapacity

        else:
            if parameters.scenario - 1 >= len(antares_node.SolarSelectedScenario):
                continue

            sc_solar = antares_node.SolarSelectedScenario[parameters.scenario - 1]  # TODO

            if str(sc_solar) in antares_node.SolarProduction.Index:
                if antares_node.SolarProduction.Abs().Max() > 0:
                    solars.append(
                        Solar(
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

    atlas_dataset.solar.add(solars)

    return atlas_dataset
