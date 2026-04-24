"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.study import Study
from loguru import logger
from pendulum import duration

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.objects.equipment.solar import Solar


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
        area = areas[area_name]
        if area_name not in areas:
            continue
        if study.get_settings().advanced_parameters.renewable_generation_modelling.value == "clusters":
            renewables = area.get_renewables()
            for res_name in renewables:
                cluster_res = renewables[res_name]
                if (
                    cluster_res.properties.group == parameters.renewables.solar_pv_group
                    and cluster_res.properties.enabled
                ):
                    scenario = (
                        study.get_output(parameters.output_name)
                        .get_solar_ts_numbers(area_name)
                        .get(parameters.scenario, None)
                    )
                    if scenario:
                        if area.get_solar_matrix()[scenario - 1].abs().max().item() > 0:
                            new_solar = Solar(
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
                                    default_value=parameters.renewables.pv_max_curtailment_ratio,
                                ),
                                curtailment_cost=Timeseries.from_index(
                                    start_date=parameters.start_date,
                                    frequency="1h",
                                    end_date=parameters.start_date + duration(years=1),
                                    default_value=parameters.renewables.pv_curtailment_cost,
                                ),
                                installed_capacity=cluster_res.properties.nominal_capacity,
                            )

                            solar_thermal = renewables.get(area_name + parameters.renewables.solar_thermo_suffix, None)
                            if solar_thermal is not None and solar_thermal.properties.enabled:
                                new_solar.installed_capacity += solar_thermal.properties.nominal_capacity

                            solars.append(new_solar)
        else:
            scenario = (
                study.get_output(parameters.output_name).get_solar_ts_numbers(area_name).get(parameters.scenario, None)
            )

            if scenario:
                if area.get_solar_matrix()[scenario - 1].abs().max().item() > 0:
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
                                default_value=parameters.renewables.pv_max_curtailment_ratio,
                            ),
                        )
                    )

    atlas_dataset.solar.add(solars)
    logger.info(f"Converted {len(solars)} solar units")

    return atlas_dataset
