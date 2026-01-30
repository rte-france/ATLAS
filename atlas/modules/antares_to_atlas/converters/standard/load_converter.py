"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.study import Study

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.models.business_model import BusinessModel
from atlas.modules.antares_to_atlas.converters.base import Converter
from atlas.modules.antares_to_atlas.models.load.load import convert_load_units
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


class LoadConverter(Converter):
    @property
    def name(self) -> str:
        return "load"

    @property
    def description(self) -> str:
        return "Load Conversion"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset
    ) -> list[BusinessModel]:
        return convert_load_units(study, parameters, atlas_dataset)
