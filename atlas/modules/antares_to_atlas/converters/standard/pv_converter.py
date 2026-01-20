"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Any

from atlas.modules.antares_to_atlas.converters.base import Converter
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters

try:
    from atlas.modules.antares_to_atlas.models.res import pv as legacy_pv

    HAS_LEGACY = True
except ImportError:
    HAS_LEGACY = False


class PVConverter(Converter):
    """Converter for photovoltaic generation data."""

    @property
    def name(self) -> str:
        return "pv"

    @property
    def description(self) -> str:
        return "PV Conversion"

    def convert(
        self,
        antares_dataset: Any,
        parameters: AntaresToAtlasParameters,
        shared_state: dict[str, Any],
    ) -> dict[str, Any]:
        if HAS_LEGACY:
            return legacy_pv.conversion_pv(antares_dataset, parameters)
        else:
            raise NotImplementedError("PV conversion not yet implemented")
