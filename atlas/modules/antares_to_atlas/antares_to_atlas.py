"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Main Antares to Atlas converter orchestrator.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from antares.craft import read_study_local
from antares.craft.model.study import Study
from loguru import logger

from atlas.core.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.antares_to_atlas.converters.base import Converter
from atlas.modules.antares_to_atlas.converters.bp23 import (
    DSRConverterBP23,
    DSRFRConverterBP23,
    ElectricVehicleConverterBP23,
    ElectricVehicleFRConverterBP23,
    InitialLevelConverterBP23,
    MixedFuelConverterBP23,
    MultiEnergyConverterBP23,
    NuclearModulationConverterBP23,
    P2GConverterBP23,
    ParticularMidConverterBP23,
    ParticularPeakConverterBP23,
    PHSFusionConverterBP23,
    PHSOpenConverterBP23,
    PHSOpenFRConverterBP23,
    WaterValueConverterBP23,
)
from atlas.modules.antares_to_atlas.converters.registry import ConverterRegistry
from atlas.modules.antares_to_atlas.converters.standard import (
    BatteryConverter,
    HydroConverter,
    LinkConverter,
    LoadConverter,
    NonDispatchableConverter,
    PHSClosedConverter,
    SolarConverter,
    SystemStructureConverter,
    ThermalConverter,
    WindConverter,
)
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters, HypothesisEnum


class AntaresToAtlas:
    """Main orchestrator for Antares to Atlas data conversion.

    This class manages the conversion process from Antares simulation data to Atlas format,
    coordinating standard and hypothesis-specific conversion steps based on the provided parameters.

    Example usage:
        ```python
        # Create converter with parameters
        converter = AntaresToAtlas.from_file("parameters.yaml")

        # Execute conversion
        converter.convert(study_path="data/antares")
        ```

    :param parameters: Conversion parameters
    :type parameters: AntaresToAtlasParameters
    """

    def __init__(self, parameters: AntaresToAtlasParameters) -> None:
        """Initialize the converter with parameters.

        :param parameters: Conversion parameters
        :type parameters: AntaresToAtlasParameters
        """
        self.parameters = parameters
        self.registry = self._build_registry()

    @classmethod
    def from_file(cls, parameters_file: str | Path) -> AntaresToAtlas:
        """Create converter from a parameters file.

        :param parameters_file: Path to YAML or JSON parameters file
        :type parameters_file: str
        :return: Configured AntaresToAtlas converter
        :rtype: AntaresToAtlas
        """
        parameters = AntaresToAtlasParameters.from_file(parameters_file)
        return cls(parameters)

    @classmethod
    def from_dict(cls, parameters_dict: dict[str, Any]) -> AntaresToAtlas:
        """Create converter from a parameters dictionary.

        :param parameters_dict: Parameters as dictionary
        :type parameters_dict: dict[str, Any]
        :return: Configured AntaresToAtlas converter
        :rtype: AntaresToAtlas
        """
        parameters = AntaresToAtlasParameters.model_validate(parameters_dict)
        return cls(parameters)

    def _build_registry(self) -> ConverterRegistry:
        """Build the converter registry with all converters.

        The order of registration determines the execution order.
        Standard converters are registered first, followed by hypothesis-specific converters.

        :return: Configured converter registry
        :rtype: ConverterRegistry
        """
        registry = ConverterRegistry()

        standard_converters: list[type[Converter]] = [
            SystemStructureConverter,
            LoadConverter,
            WindConverter,
            SolarConverter,
            HydroConverter,
            LinkConverter,
            ThermalConverter,
            NonDispatchableConverter,
            BatteryConverter,
            PHSClosedConverter,
        ]
        for converter in standard_converters:
            registry.register(converter)

        if self.parameters.hypothesis == HypothesisEnum.BP23:
            self._register_bp23_converters(registry)

        return registry

    def _register_bp23_converters(self, registry: ConverterRegistry) -> None:
        """Register BP23-specific converters in execution order.

        :param registry: Converter registry
        :type registry: ConverterRegistry
        """
        bp23_converters: list[type[Converter]] = [
            MixedFuelConverterBP23,  # Depends on thermal converter
            ElectricVehicleConverterBP23,
            ElectricVehicleFRConverterBP23,  # France-specific EVs + heavy vehicles
            ParticularMidConverterBP23,
            ParticularPeakConverterBP23,
            P2GConverterBP23,
            MultiEnergyConverterBP23,  # Must run after all thermic units
            DSRConverterBP23,
            DSRFRConverterBP23,  # France-specific DSR
            PHSOpenConverterBP23,  # Open-loop PHS (non-FR), updates hydro equipment
            PHSOpenFRConverterBP23,  # Open-loop PHS (FR-specific)
            PHSFusionConverterBP23,  # Merge open + closed PHS by node
            WaterValueConverterBP23,  # Depends on PHS (for updated inflows)
            InitialLevelConverterBP23,
            NuclearModulationConverterBP23,  # France-specific
        ]
        for converter in bp23_converters:
            registry.register(converter)

    def _resolve_parameters(self, study: Study) -> AntaresToAtlasParameters:
        """Resolve dynamic parameter values that require the loaded study.

        Expands ``market_areas='all'`` to the full list of areas from the study,
        minus any areas listed in ``excluded_market_areas``.

        :param study: Loaded Antares study
        :type study: Study
        :return: Parameters with concrete market_areas list
        :rtype: AntaresToAtlasParameters
        """
        if self.parameters.market_areas != "all":
            return self.parameters

        excluded = set(self.parameters.excluded_market_areas)
        resolved = [area for area in study.get_areas() if area not in excluded]
        logger.info(f"Resolved market_areas='all' to {len(resolved)} areas: {resolved}")
        return self.parameters.model_copy(update={"market_areas": resolved})

    def convert(self, study_path: str | Path) -> AtlasDataset:
        """Execute the conversion process.

        Loads the Antares study from the configured path and converts it to Atlas format.

        :return: Converted AtlasDataset containing all business models
        :rtype: AtlasDataset
        """
        logger.info("Starting Antares to Atlas conversion")
        logger.info(f"Hypothesis: {self.parameters.hypothesis}")
        logger.info(f"Scenario: {self.parameters.scenario}")

        study = read_study_local(study_path)
        logger.info(f"Study loaded: {study.name}")

        parameters = self._resolve_parameters(study)
        results = self.registry.execute_all(study, parameters, AtlasDataset())

        logger.info("Conversion completed successfully")

        return results

    def list_converters(self) -> list[str]:
        """List converters that would run with the current parameters.

        :return: List of converter names in registration order
        :rtype: list[str]
        """
        return self.registry.get_converter_names(self.parameters)

    def list_converter_details(self) -> list[tuple[str, str]]:
        """List converters that would run with the current parameters, with descriptions.

        :return: List of (name, description) pairs in registration order
        :rtype: list[tuple[str, str]]
        """
        return self.registry.get_converter_details(self.parameters)
