"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Load converter.
"""

from typing import Any

from atlas.models.business_model import BusinessModel
from atlas.modules.antares_to_atlas.converters.base import Converter
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters

try:
    from atlas.modules.antares_to_atlas.models.load import load as legacy_load

    HAS_LEGACY = True
except ImportError:
    HAS_LEGACY = False


class LoadConverter(Converter):
    """Converter for electrical load data."""

    @property
    def name(self) -> str:
        """Return converter name."""
        return "load"

    @property
    def description(self) -> str:
        """Return converter description."""
        return "Load Conversion"

    def convert(
        self,
        antares_dataset: Any,
        parameters: AntaresToAtlasParameters,
        shared_state: dict[str, Any],
    ) -> dict[str, list[BusinessModel]]:
        """Convert load data."""
        if HAS_LEGACY:
            return legacy_load.conversion_load(antares_dataset, parameters)
        else:
            raise NotImplementedError("Load conversion not yet implemented without legacy code")
