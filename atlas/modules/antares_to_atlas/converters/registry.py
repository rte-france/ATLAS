"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Converter registry for managing and executing converters.
"""

from antares.craft.model.study import Study
from loguru import logger

import atlas.config as cfg
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.antares_to_atlas.converters.base import Converter
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


def _count_by_type(dataset: AtlasDataset) -> dict[str, int]:
    return {str(t): len(getattr(dataset, t)) for t in cfg.MODEL_ORDER_INSTANTIATION}


def _format_added(before: dict[str, int], after: dict[str, int]) -> str:
    added = {t: after[t] - before[t] for t in before if after[t] > before[t]}
    if not added:
        return "no new objects"
    return ", ".join(f"+{n} {t}" for t, n in added.items())


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
        atlas_dataset: AtlasDataset,
    ) -> AtlasDataset:
        """Execute all registered converters in order.

        :param study: Antares study object from antares_craft
        :type study: Study
        :param parameters: Conversion parameters
        :type parameters: AntaresToAtlasParameters
        :return: Updated AtlasDataset after all converters have been executed
        :rtype: AtlasDataset
        """
        logger.info(f"Starting conversion — {len(self._converters)} converters registered")

        for converter_class in self._converters:
            converter = converter_class()

            if not converter.should_run(parameters):
                logger.info(f"Skipping '{converter.name}' ({converter.description})")
                continue

            logger.info(f"Running '{converter.name}' — {converter.description}")
            before = _count_by_type(atlas_dataset)
            atlas_dataset = converter.run(study, parameters, atlas_dataset)
            after = _count_by_type(atlas_dataset)
            logger.info(f"Done — {_format_added(before, after)}")

        logger.info(f"Conversion complete — {atlas_dataset}")

        return atlas_dataset

    def get_converter_names(self, parameters: AntaresToAtlasParameters | None = None) -> list[str]:
        """Get names of registered converters, optionally filtered by parameters.

        :param parameters: If provided, only converters that would run are returned.
        :return: List of converter names in registration order
        :rtype: list[str]
        """
        return [name for name, _ in self.get_converter_details(parameters)]

    def get_converter_details(
        self, parameters: AntaresToAtlasParameters | None = None
    ) -> list[tuple[str, str]]:
        """Get names and descriptions of registered converters.

        :param parameters: If provided, only converters that would run are returned
                           (respects conversion_steps and required_market_areas).
        :return: List of (name, description) pairs in registration order
        :rtype: list[tuple[str, str]]
        """
        return [
            (c.name, c.description)
            for c in self._converters
            if parameters is None or c().should_run(parameters)
        ]
