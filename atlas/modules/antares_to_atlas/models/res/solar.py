"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.study import Study
from loguru import logger
from pendulum import duration

from atlas.core.io_utils.atlas_dataset import AtlasDataset
from atlas.core.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.modules.antares_to_atlas.utils import get_portfolio
from atlas.objects.equipment.solar import Solar


def _build_solar(area_name: str, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset, **kwargs) -> Solar:
    end_date = parameters.start_date + duration(years=1)
    days_in_year = (end_date - parameters.start_date).days
    return Solar(
        name=f"{area_name}_pv",
        node=atlas_dataset.get("node", area_name),
        portfolio=get_portfolio(atlas_dataset, parameters, area_name),
        maximum_curtailment_ratio=Timeseries.from_index(
            start_date=parameters.start_date,
            frequency=f"{days_in_year}d",
            end_date=end_date,
            default_value=parameters.renewables.pv_max_curtailment_ratio,
        ),
        co2_emission_factor=0.0,
        has_daily_energy_constraint=False,
        maximum_afrr=0.0,
        maximum_fcr=0.0,
        maximum_gradient=0.0,
        setup_delay=0.0,
        unit_count=0,
        additional_hours=duration(),
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
            scenario = (
                study.get_output(parameters.output_name).get_solar_ts_numbers(area_name).get(parameters.scenario, None)
            )
            renewables = area.get_renewables()
            for cluster_res in renewables.values():
                if cluster_res.properties.group != "solar pv":
                    continue
                if not cluster_res.properties.enabled:
                    continue
                if cluster_res.get_timeseries().abs().max().max() == 0:
                    continue

                _end = parameters.start_date + duration(years=1)
                _days = (_end - parameters.start_date).days
                new_solar = _build_solar(
                    area_name,
                    parameters,
                    atlas_dataset,
                    curtailment_cost=Timeseries.from_index(
                        start_date=parameters.start_date,
                        frequency=f"{_days}d",
                        end_date=_end,
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
