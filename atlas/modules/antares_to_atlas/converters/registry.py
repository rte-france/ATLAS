"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Converter registry for managing and executing converters.
"""

from typing import Any

from loguru import logger

from atlas.modules.antares_to_atlas.converters.base import BaseConverter
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


class ConverterRegistry:
    """Registry for managing and executing converters in the correct order.

    This registry maintains separate lists for standard and specific converters,
    ensuring they are executed in the correct order with proper dependency handling.
    """

    def __init__(self) -> None:
        """Initialize the converter registry."""
        self._standard_converters: list[type[BaseConverter]] = []
        self._specific_converters: list[type[BaseConverter]] = []

    def register_standard(self, converter_class: type[BaseConverter]) -> None:
        """Register a standard converter.

        Standard converters are executed first, in the order they are registered.

        :param converter_class: Converter class to register
        :type converter_class: Type[BaseConverter]
        """
        self._standard_converters.append(converter_class)
        logger.debug(f"Registered standard converter: {converter_class.__name__}")

    def register_specific(self, converter_class: type[BaseConverter]) -> None:
        """Register a specific converter.

        Specific converters are executed after standard converters, in the order they are registered.

        :param converter_class: Converter class to register
        :type converter_class: Type[BaseConverter]
        """
        self._specific_converters.append(converter_class)
        logger.debug(f"Registered specific converter: {converter_class.__name__}")

    def execute_all(
        self,
        antares_dataset: Any,
        atlas_dataset: Any,
        parameters: AntaresToAtlasParameters,
        shared_state: dict[str, Any],
    ) -> dict[str, dict]:
        """Execute all registered converters in order.

        Standard converters are executed first, followed by specific converters.
        Results from each converter are stored in the shared_state dictionary.

        :param antares_dataset: Antares input data marker
        :type antares_dataset: Any
        :param atlas_dataset: Atlas output data marker
        :type atlas_dataset: Any
        :param parameters: Conversion parameters
        :type parameters: AntaresToAtlasParameters
        :param shared_state: Shared state dictionary
        :type shared_state: dict[str, Any]
        :return: Dictionary mapping converter names to their results
        :rtype: dict[str, dict]
        """
        results = {}

        logger.info("=" * 50)
        logger.info("Standard Conversions")
        logger.info("=" * 50)

        for converter_class in self._standard_converters:
            converter = converter_class()
            result = converter.run(antares_dataset, atlas_dataset, parameters, shared_state)
            if result:
                results[converter.name] = result

        logger.info("")
        logger.info("=" * 50)
        logger.info("Specific Conversions")
        logger.info("=" * 50)

        for converter_class in self._specific_converters:
            converter = converter_class()
            result = converter.run(antares_dataset, atlas_dataset, parameters, shared_state)
            if result:
                results[converter.name] = result

        logger.info("")
        logger.info("*** Conversion Complete ***")

        return results

    def get_converter_names(self) -> dict[str, list[str]]:
        """Get names of all registered converters.

        :return: Dictionary with 'standard' and 'specific' keys containing converter names
        :rtype: dict[str, list[str]]
        """
        return {
            "standard": [c().name for c in self._standard_converters],
            "specific": [c().name for c in self._specific_converters],
        }
