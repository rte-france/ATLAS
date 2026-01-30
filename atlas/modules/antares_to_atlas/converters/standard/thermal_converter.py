"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Thermal generation units converter.
"""

from typing import Any

from antares.craft.model.study import Study

from atlas.models.business_model import BusinessModel
from atlas.modules.antares_to_atlas.converters.base import Converter
from atlas.modules.antares_to_atlas.models.thermal import convert_thermal_units
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


class ThermalConverter(Converter):
    """Converter for thermal generation units.

    This converter orchestrates the conversion by calling the business logic
    in the models.thermal module.
    """

    @property
    def name(self) -> str:
        return "thermal"

    @property
    def description(self) -> str:
        return "Thermic Conversion"

    def convert(
        self,
        study: Study,
        parameters: AntaresToAtlasParameters,
        shared_state: dict[str, Any],
    ) -> list[BusinessModel]:
        """Convert thermal generation units.

        :param study: Antares study object
        :type study: Study
        :param parameters: Conversion parameters
        :type parameters: AntaresToAtlasParameters
        :param shared_state: Shared state dictionary
        :type shared_state: dict[str, Any]
        :return: List of created Thermal equipment
        :rtype: list[BusinessModel]
        """
        # Call the business logic in the models module
        thermal_units = convert_thermal_units(study, parameters, shared_state)
        return thermal_units
