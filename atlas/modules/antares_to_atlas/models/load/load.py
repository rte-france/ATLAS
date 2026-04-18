"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.study import Study
from loguru import logger

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.objects.equipment.load import Load


def convert_load_units(study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
    """Convert load data from Antares to Atlas."""

    logger.info("Converting load data")
    areas = study.get_areas()
    loads = []

    for area_name in parameters.market_areas:
        if area_name not in areas:
            continue

        logger.debug(f"Processing load for area {area_name}")
        scenario = study.get_output(parameters.output_name).get_load_ts_numbers().get(parameters.scenario, None)

        if scenario:
            load = Load(
                name=f"{area_name}_load",
                node=atlas_dataset.get("node", area_name),
                portfolio=atlas_dataset.get(
                    "portfolio",
                    f"supplier_{area_name}"
                    if parameters.consumption_production_separation
                    else f"portfolio_{area_name}",
                ),
            )

        loads.append(load)

    atlas_dataset.load.add(loads)

    return atlas_dataset
