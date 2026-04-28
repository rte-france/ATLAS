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


def _build_solar(area_name: str, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset, **kwargs) -> Solar:
    return Solar(
        name=f"{area_name}_pv",
        node=atlas_dataset.get("node", area_name),
        portfolio=atlas_dataset.get(
            "portfolio",
            f"generator_{area_name}" if parameters.consumption_production_separation else f"portfolio_{area_name}",
        ),
        maximum_curtailment_ratio=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency="1h",
            end_date=parameters.start_date + duration(years=1),
            default_value=parameters.renewables.pv_max_curtailment_ratio,
        ),
        **kwargs,
    )


def convert_solar_units(
    study: Study,
    parameters: AntaresToAtlasParameters,
    atlas_dataset: AtlasDataset,
) -> AtlasDataset:
    """Convert Solar generation data from Antares to Atlas."""

    logger.info("Converting Solar generation data")
    areas = study.get_areas()
    solars: list[Solar] = []
    use_clusters = study.get_settings().advanced_parameters.renewable_generation_modelling.value == "clusters"

    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue
        area = areas[area_name]

        if use_clusters:
            renewables = area.get_renewables()
            for cluster_res in renewables.values():
                if cluster_res.properties.group != parameters.renewables.solar_pv_group:
                    continue
                if not cluster_res.properties.enabled:
                    continue
                scenario = (
                    study.get_output(parameters.output_name)
                    .get_solar_ts_numbers(area_name)
                    .get(parameters.scenario, None)
                )
                if not scenario or area.get_solar_matrix()[scenario - 1].abs().max().item() == 0:
                    continue

                new_solar = _build_solar(
                    area_name,
                    parameters,
                    atlas_dataset,
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

                logger.debug(f"Added solar unit : {new_solar.name}")
                solars.append(new_solar)

        else:
            scenario = (
                study.get_output(parameters.output_name).get_solar_ts_numbers(area_name).get(parameters.scenario, None)
            )
            if not scenario or area.get_solar_matrix()[scenario - 1].abs().max().item() == 0:
                continue

            new_solar = _build_solar(area_name, parameters, atlas_dataset)
            logger.debug(f"Added solar unit : {new_solar.name}")
            solars.append(new_solar)

    atlas_dataset.solar.add(solars)
    logger.info(f"Converted {len(solars)} solar units")

    return atlas_dataset
