"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Main Antares to Atlas converter orchestrator.
"""

from __future__ import annotations

from typing import Any

from antares.craft import read_study_local
from loguru import logger

from atlas.modules.antares_to_atlas.converters.registry import ConverterRegistry
from atlas.modules.antares_to_atlas.converters.specific import (
    BatteryConverterBP23,
    DSRConverterBP23,
    ElectricVehicleConverterBP23,
    InitialLevelConverterBP23,
    MixedFuelConverterBP23,
    MultiEnergyConverterBP23,
    NuclearModulationConverterBP23,
    P2GConverterBP23,
    ParticularMidPeakConverterBP23,
    PHSConverterBP23,
    WaterValueConverterBP23,
)
from atlas.modules.antares_to_atlas.converters.standard import (
    HydroConverter,
    LinkConverter,
    LoadConverter,
    NodeConverter,
    NonDispatchableConverter,
    PVConverter,
    ThermalConverter,
    WindConverter,
)
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


class AntaresToAtlas:
    """Main orchestrator for Antares to Atlas data conversion.

    This class manages the conversion process from Antares simulation data to Atlas format,
    coordinating standard and hypothesis-specific conversion steps based on the provided parameters.

    Example usage:
        ```python
        # Create converter with parameters
        converter = AntaresToAtlas.from_file("parameters.yaml")

        # Execute conversion
        converter.convert(antares_dataset, altas_dataset)
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
    def from_file(cls, parameters_file: str) -> AntaresToAtlas:
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

        # Register standard converters
        standard_converters = [
            NodeConverter,
            LoadConverter,
            WindConverter,
            PVConverter,
            HydroConverter,
            LinkConverter,
            ThermalConverter,
            NonDispatchableConverter,
        ]
        for converter in standard_converters:
            registry.register(converter)

        # Register hypothesis-specific converters
        if self.parameters.hypothesis == "BP23":
            self._register_bp23_converters(registry)
        # Add more hypotheses here as needed
        # elif self.parameters.hypothesis == "BP24":
        #     self._register_bp24_converters(registry)

        return registry

    def _register_bp23_converters(self, registry: ConverterRegistry) -> None:
        """Register BP23-specific converters in execution order.

        :param registry: Converter registry
        :type registry: ConverterRegistry
        """
        bp23_converters = [
            MixedFuelConverterBP23,  # Depends on thermal converter
            ElectricVehicleConverterBP23,
            BatteryConverterBP23,
            ParticularMidPeakConverterBP23,
            P2GConverterBP23,
            MultiEnergyConverterBP23,  # Must run after all thermic units
            DSRConverterBP23,
            PHSConverterBP23,  # Depends on hydro converter
            WaterValueConverterBP23,  # Depends on PHS (for updated inflows)
            InitialLevelConverterBP23,
            NuclearModulationConverterBP23,  # France-specific
        ]
        for converter in bp23_converters:
            registry.register(converter)

    def convert(self) -> dict[str, dict]:
        """Execute the conversion process.

        Loads the Antares study from the configured path and converts it to Atlas format.

        :return: Dictionary of conversion results from each converter
        :rtype: dict[str, dict]
        """
        logger.info("=" * 70)
        logger.info("Starting Antares to Atlas conversion")
        logger.info("=" * 70)
        logger.info(f"Study Path: {self.parameters.study_path}")
        logger.info(f"Antares Version: {self.parameters.antares_version}")
        logger.info(f"Hypothesis: {self.parameters.hypothesis}")
        logger.info(f"Market Areas: {', '.join(self.parameters.market_areas)}")
        logger.info(f"Scenario: {self.parameters.scenario}")

        # Load Antares study using antares_craft
        logger.info("Loading Antares study...")
        study = read_study_local(self.parameters.study_path)
        logger.info(f"Study loaded: {study.name}")

        # Create shared state for data sharing between converters
        shared_state: dict[str, Any] = {}

        # Execute all converters
        results = self.registry.execute_all(study, self.parameters, shared_state)

        logger.info("=" * 70)
        logger.info("Conversion completed successfully")
        logger.info("=" * 70)

        return results

    def list_converters(self) -> list[str]:
        """List all registered converters.

        :return: List of converter names in registration order
        :rtype: list[str]
        """
        return self.registry.get_converter_names()
