"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Any

from atlas.models.business_model import BusinessModel
from atlas.modules.antares_to_atlas.converters.base import Converter
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters

try:
    from atlas.modules.antares_to_atlas.models.other import other_non_dispatchable as legacy_other

    HAS_LEGACY = True
except ImportError:
    HAS_LEGACY = False


class NonDispatchableConverter(Converter):
    """Converter for other non-dispatchable generation."""

    @property
    def name(self) -> str:
        return "non_dispatchable"

    @property
    def description(self) -> str:
        return "Non-dispatchable Conversion"

    def convert(
        self,
        antares_dataset: Any,
        parameters: AntaresToAtlasParameters,
        shared_state: dict[str, Any],
    ) -> dict[str, list[BusinessModel]]:
        if HAS_LEGACY:
            return legacy_other.conversion_non_dispatchable(antares_dataset, parameters)
        else:
            raise NotImplementedError("Non-dispatchable conversion not yet implemented")
