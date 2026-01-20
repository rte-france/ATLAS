"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Any

from atlas.modules.antares_to_atlas.converters.base import Converter
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters

try:
    from atlas.modules.antares_to_atlas.models.res import wind as legacy_wind

    HAS_LEGACY = True
except ImportError:
    HAS_LEGACY = False


class WindConverter(Converter):
    """Converter for wind generation data."""

    @property
    def name(self) -> str:
        return "wind"

    @property
    def description(self) -> str:
        return "Wind Conversion"

    def convert(
        self,
        antares_dataset: Any,
        parameters: AntaresToAtlasParameters,
        shared_state: dict[str, Any],
    ) -> dict[str, Any]:
        if HAS_LEGACY:
            legacy_wind.conversion_wind(antares_dataset, parameters)
        else:
            raise NotImplementedError("Wind conversion not yet implemented")
