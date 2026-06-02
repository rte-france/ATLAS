"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Base converter classes for Antares to Atlas conversion.
"""

from abc import ABC, abstractmethod
from typing import ClassVar

from antares.craft.model.study import Study
from loguru import logger

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters, ConvertersTags


class Converter(ABC):
    """Base class for all converters.

    Each converter is responsible for converting a specific aspect of Antares data
    to Atlas format (e.g., load, thermal, hydro, etc.).

    Subclasses must declare class-level ``name`` (and optionally ``description``).

    Converters can be configured with:
    - supported_versions: List of supported Antares versions (empty means all)
    - required_market_areas: Market areas that must be present for this converter to run
    - tags: Category labels used for tag-based filtering (e.g. ``["renewable"]``, ``["hydro", "storage"]``)
    """

    name: ClassVar[str]
    description: ClassVar[str] = ""

    # Class-level configuration
    supported_versions: list[str] = []  # Empty means all versions
    required_market_areas: list[str] = []  # Empty means no requirement
    tags: list[ConvertersTags] = []  # Category labels for tag-based filtering

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not getattr(cls, "name", None):
            raise TypeError(f"Converter subclass {cls.__name__} must declare class attribute 'name'")
        if not cls.description:
            cls.description = f"{cls.name} converter"

    @abstractmethod
    def convert(
        self,
        study: Study,
        parameters: AntaresToAtlasParameters,
        atlas_dataset: AtlasDataset,
    ) -> AtlasDataset:
        """Execute the conversion.

        :param study: Antares study object from antares_craft
        :type study: Study
        :param parameters: Conversion parameters
        :type parameters: AntaresToAtlasParameters
        :param shared_state: Dictionary for sharing data between conversion steps
        :type atlas_dataset: AtlasDataset
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

        # Check tag filters (only_tags / skip_tags)
        if parameters.only_tags and not any(tag in parameters.only_tags for tag in self.tags):
            return False
        if parameters.skip_tags and any(tag in parameters.skip_tags for tag in self.tags):
            return False

        # Check required market areas
        # When market_areas="all", every area is implicitly present
        if self.required_market_areas and parameters.market_areas != "all":
            missing_areas = set(self.required_market_areas) - set(parameters.market_areas)
            if missing_areas:
                logger.debug(f"Skipping {self.name}: required market areas {missing_areas} not present")
                return False

        return True

    def run(
        self,
        study: Study,
        parameters: AntaresToAtlasParameters,
        atlas_dataset: AtlasDataset,
    ) -> AtlasDataset:
        """Run the converter, returning atlas_dataset unchanged if should_run() is False.

        :param study: Antares study object
        :type study: Study
        :param parameters: Conversion parameters
        :type parameters: AntaresToAtlasParameters
        :param atlas_dataset: Atlas dataset
        :type atlas_dataset: AtlasDataset
        :return: Updated (or unchanged) AtlasDataset
        :rtype: AtlasDataset
        """
        if not self.should_run(parameters):
            return atlas_dataset

        return self.convert(study, parameters, atlas_dataset)
