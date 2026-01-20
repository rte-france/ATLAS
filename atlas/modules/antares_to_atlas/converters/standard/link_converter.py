"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Any

from atlas.models.business_model import BusinessModel
from atlas.modules.antares_to_atlas.converters.base import Converter
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters

try:
    from atlas.modules.antares_to_atlas.models.system_structure import link as legacy_link

    HAS_LEGACY = True
except ImportError:
    HAS_LEGACY = False


class LinkConverter(Converter):
    """Converter for inter-area links."""

    @property
    def name(self) -> str:
        return "link"

    @property
    def description(self) -> str:
        return "Link Conversion"

    def convert(
        self,
        antares_dataset: Any,
        parameters: AntaresToAtlasParameters,
        shared_state: dict[str, Any],
    ) -> dict[str, list[BusinessModel]]:
        if HAS_LEGACY:
            return legacy_link.conversion_link(antares_dataset, parameters)
        else:
            raise NotImplementedError("Link conversion not yet implemented")
