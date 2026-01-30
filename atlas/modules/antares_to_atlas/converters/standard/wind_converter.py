"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.study import Study

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.models.business_model import BusinessModel
from atlas.modules.antares_to_atlas.converters.base import Converter
from atlas.modules.antares_to_atlas.models.res.wind import convert_wind_units
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


class WindConverter(Converter):
    @property
    def name(self) -> str:
        return "wind"

    @property
    def description(self) -> str:
        return "Wind Conversion"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset
    ) -> list[BusinessModel]:
        return convert_wind_units(study, parameters, atlas_dataset)
