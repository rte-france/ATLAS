"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
from antares.craft.model.study import Study
from loguru import logger

from atlas.core.io_utils.atlas_dataset import AtlasDataset
from atlas.enums import LoadType
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.modules.antares_to_atlas.utils import get_portfolio
from atlas.objects.equipment.load import Load


def convert_load_units(study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
    """Convert load data from Antares to Atlas."""

    areas = study.get_areas()
    loads = []

    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        logger.debug(f"Processing load for area {area_name}")
        scenario = (
            study.get_output(parameters.output_name).get_load_ts_numbers(area_name).get(parameters.scenario, None)
        )

        if scenario:
            load = Load(
                name=f"{area_name}_l",
                node=atlas_dataset.get("node", area_name),
                portfolio=get_portfolio(atlas_dataset, parameters, area_name, role="supplier"),
                load_type=LoadType.BASE_LOAD,
                co2_emission_factor=0.0,
                has_daily_energy_constraint=False,
                maximum_afrr=0.0,
                maximum_fcr=0.0,
                maximum_gradient=0.0,
                setup_delay=0.0,
                unit_count=0,
                additional_hours=pendulum.duration(),
            )
            logger.debug(f"Created load unit : {load.name}")
            loads.append(load)
        else:
            logger.warning(f"No scenario found for area {area_name}, skipping load conversion")

    atlas_dataset.load.add(loads)

    logger.info(f"Converted {len(loads)} load units")

    return atlas_dataset
