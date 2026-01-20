"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Any

from atlas.modules.antares_to_atlas.converters.base import StandardConverter
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters

try:
    from atlas.modules.antares_to_atlas.models.thermal import thermal as legacy_thermal

    HAS_LEGACY = True
except ImportError:
    HAS_LEGACY = False


class ThermalConverter(StandardConverter):
    """Converter for thermal generation units."""

    @property
    def name(self) -> str:
        return "thermal"

    @property
    def description(self) -> str:
        return "Thermic Conversion"

    def convert(
        self,
        antares_dataset: Any,
        parameters: AntaresToAtlasParameters,
        shared_state: dict[str, Any],
    ) -> dict[str, Any]:
        if HAS_LEGACY:
            thermic_param, thermic_props = legacy_thermal.conversion_thermal(antares_dataset, parameters)
            return {"thermic_parameter": thermic_param, "thermic_properties": thermic_props}
        else:
            raise NotImplementedError("Thermal conversion not yet implemented")
