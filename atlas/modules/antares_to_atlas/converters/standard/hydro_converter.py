"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Any

from atlas.modules.antares_to_atlas.converters.base import StandardConverter
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters

try:
    from atlas.modules.antares_to_atlas.models.hydro import hydraulic as legacy_hydraulic

    HAS_LEGACY = True
except ImportError:
    HAS_LEGACY = False


class HydroConverter(StandardConverter):
    """Converter for hydraulic generation data."""

    @property
    def name(self) -> str:
        return "hydro"

    @property
    def description(self) -> str:
        return "Hydro Conversion"

    def convert(
        self,
        antares_dataset: Any,
        parameters: AntaresToAtlasParameters,
        shared_state: dict[str, Any],
    ) -> dict[str, Any]:
        if HAS_LEGACY:
            inflows_dict, hydro_reservoirs = legacy_hydraulic.conversion_hydraulic(antares_dataset, parameters)
            return {"inflows_dictionary": inflows_dict, "hydro_reservoirs": hydro_reservoirs}
        else:
            raise NotImplementedError("Hydro conversion not yet implemented")
