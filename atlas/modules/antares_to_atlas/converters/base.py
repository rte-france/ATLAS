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


class BaseConverter(ABC):
    """Base class for all converters.

    Each converter is responsible for converting a specific aspect of Antares data
    to Atlas format (e.g., load, thermal, hydro, etc.).
    """

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
            return self.name in parameters.conversion_steps
        return True

    def run(
        self,
        antares_dataset: Any,
        parameters: AntaresToAtlasParameters,
        shared_state: dict[str, Any],
    ) -> dict[str, list[BusinessModel]]:
        """Run the converter with logging.

        :param antares_dataset: Antares input data marker
        :type antares_dataset: Any
        :param parameters: Conversion parameters
        :type parameters: AntaresToAtlasParameters
        :param shared_state: Shared state dictionary
        :type shared_state: dict[str, Any]
        :return: Conversion results
        :rtype: dict[str, Any]
        """
        if not self.should_run(parameters):
            logger.info(f"Skipping {self.name} (not in requested conversion_steps)")
            return {}

        result = self.convert(antares_dataset, parameters, shared_state)

        # Store result in shared state if converter returns data
        if result:
            shared_state[self.name] = result

        return result


class StandardConverter(BaseConverter):
    """Base class for standard conversions that apply to all Antares versions and hypotheses."""

    def should_run(self, parameters: AntaresToAtlasParameters) -> bool:
        """Standard converters run when standard conversions are enabled."""
        if not parameters.enable_standard_conversions:
            return False
        return super().should_run(parameters)


class SpecificConverter(BaseConverter):
    """Base class for hypothesis-specific or version-specific conversions.

    :param supported_versions: List of Antares versions this converter supports (empty = all)
    :type supported_versions: list[str]
    :param supported_hypotheses: List of hypotheses this converter supports (empty = all)
    :type supported_hypotheses: list[str]
    :param required_market_areas: Market areas that must be present for this converter to run
    :type required_market_areas: list[str]
    """

    supported_versions: list[str] = []  # Empty means all versions
    supported_hypotheses: list[str] = []  # Empty means all hypotheses
    required_market_areas: list[str] = []  # Empty means no requirement

    def should_run(self, parameters: AntaresToAtlasParameters) -> bool:
        """Check if this specific converter should run based on version, hypothesis, and market areas."""
        if not parameters.enable_specific_conversions:
            return False

        # Check if specific steps are requested
        if not super().should_run(parameters):
            return False

        # Check version compatibility
        if self.supported_versions and parameters.antares_version not in self.supported_versions:
            logger.debug(f"Skipping {self.name}: version {parameters.antares_version} not in {self.supported_versions}")
            return False

        # Check hypothesis compatibility
        if self.supported_hypotheses and parameters.hypothesis not in self.supported_hypotheses:
            logger.debug(f"Skipping {self.name}: hypothesis {parameters.hypothesis} not in {self.supported_hypotheses}")
            return False

        # Check required market areas
        if self.required_market_areas:
            missing_areas = set(self.required_market_areas) - set(parameters.market_areas)
            if missing_areas:
                logger.debug(f"Skipping {self.name}: required market areas {missing_areas} not present")
                return False

        return True
