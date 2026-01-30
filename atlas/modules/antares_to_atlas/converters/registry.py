"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Converter registry for managing and executing converters.
"""

from typing import Any

from antares.craft.model.study import Study
from loguru import logger

from atlas.modules.antares_to_atlas.converters.base import Converter
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


class ConverterRegistry:
    """Registry for managing and executing converters in the correct order.

    This registry maintains a list of converters and executes them in registration order,
    with proper dependency handling.
    """

    def __init__(self) -> None:
        """Initialize the converter registry."""
        self._converters: list[type[Converter]] = []

    def register(self, converter_class: type[Converter]) -> None:
        """Register a converter.

        Converters are executed in the order they are registered.

        :param converter_class: Converter class to register
        :type converter_class: Type[Converter]
        """
        self._converters.append(converter_class)
        logger.debug(f"Registered converter: {converter_class.__name__}")

    def execute_all(
        self,
        study: Study,
        parameters: AntaresToAtlasParameters,
        shared_state: dict[str, Any],
    ) -> dict[str, dict]:
        """Execute all registered converters in order.

        Results from each converter are stored in the shared_state dictionary.

        :param study: Antares study object
        :type study: Study
        :param parameters: Conversion parameters
        :type parameters: AntaresToAtlasParameters
        :param shared_state: dict[str, Any]
        :type shared_state: dict[str, Any]
        :return: Dictionary mapping converter names to their results
        :rtype: dict[str, dict]
        """
        results = {}

        logger.info("=" * 70)
        logger.info("Executing Converters")
        logger.info("=" * 70)

        for converter_class in self._converters:
            converter = converter_class()
            result = converter.run(study, parameters, shared_state)
            if result:
                results[converter.name] = result

        logger.info("")
        logger.info("=" * 70)
        logger.info("Conversion Complete")
        logger.info("=" * 70)

        return results

    def get_converter_names(self) -> list[str]:
        """Get names of all registered converters.

        :return: List of converter names in registration order
        :rtype: list[str]
        """
        return [c().name for c in self._converters]
