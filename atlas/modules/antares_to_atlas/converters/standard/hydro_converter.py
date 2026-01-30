"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Any

from antares.craft.model.study import Study

from atlas.models.business_model import BusinessModel
from atlas.modules.antares_to_atlas.converters.base import Converter
from atlas.modules.antares_to_atlas.models.hydro import convert_hydro_units
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


class HydroConverter(Converter):
    @property
    def name(self) -> str:
        return "hydro"

    @property
    def description(self) -> str:
        return "Hydraulic Conversion"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, shared_state: dict[str, Any]
    ) -> list[BusinessModel]:
        return convert_hydro_units(study, parameters, shared_state)
