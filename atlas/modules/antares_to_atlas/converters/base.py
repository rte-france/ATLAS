"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Base converter classes for Antares to Atlas conversion.
"""

from abc import ABC, abstractmethod
from typing import Any

from loguru import logger

from atlas.models.business_model import BusinessModel
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


class Converter(ABC):
    """Base class for all converters.

    Each converter is responsible for converting a specific aspect of Antares data
    to Atlas format (e.g., load, thermal, hydro, etc.).

    Converters can be configured with:
    - supported_versions: List of supported Antares versions (empty means all)
    - required_market_areas: Market areas that must be present for this converter to run
    """

    # Class-level configuration
    supported_versions: list[str] = []  # Empty means all versions
    required_market_areas: list[str] = []  # Empty means no requirement

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name identifying this converter.

        :return: Converter name
        :rtype: str
        """

    @property
    def description(self) -> str:
        """Human-readable description of what this converter does.

        :return: Converter description
        :rtype: str
        """
        return f"{self.name} converter"

    @abstractmethod
    def convert(
        self,
        antares_dataset: Any,
        parameters: AntaresToAtlasParameters,
        shared_state: dict[str, Any],
    ) -> list[BusinessModel]:
        """Execute the conversion.

        :param antares_dataset: Antares input data marker (API object)
        :type antares_dataset: Any
        :param parameters: Conversion parameters
        :type parameters: AntaresToAtlasParameters
        :param shared_state: Dictionary for sharing data between conversion steps
        :type shared_state: dict[str, Any]
        :return: list of BusinessModel objects created during conversion
        """

    def should_run(self, parameters: AntaresToAtlasParameters) -> bool:
        """Determine if this converter should run based on parameters.

        Override this method to add conditional execution logic.

        :param parameters: Conversion parameters
        :type parameters: AntaresToAtlasParameters
        :return: True if converter should run, False otherwise
        :rtype: bool
        """
        # Check if specific steps are requested
        if parameters.conversion_steps:
            if self.name not in parameters.conversion_steps:
                return False

        # Check required market areas
        if self.required_market_areas:
            missing_areas = set(self.required_market_areas) - set(parameters.market_areas)
            if missing_areas:
                logger.debug(f"Skipping {self.name}: required market areas {missing_areas} not present")
                return False

        return True

    def run(
        self,
        antares_dataset: Any,
        parameters: AntaresToAtlasParameters,
        shared_state: dict[str, Any],
    ) -> list[BusinessModel]:
        """Run the converter with logging.

        :param antares_dataset: Antares input data marker
        :type antares_dataset: Any
        :param parameters: Conversion parameters
        :type parameters: AntaresToAtlasParameters
        :param shared_state: Shared state dictionary
        :type shared_state: dict[str, Any]
        :return: Conversion results
        :rtype: list[BusinessModel]
        """
        if not self.should_run(parameters):
            logger.info(f"Skipping {self.name} (not in requested conversion_steps)")
            return []

        result = self.convert(antares_dataset, parameters, shared_state)

        # Store result in shared state if converter returns data
        if result:
            shared_state[self.name] = result

        return result
