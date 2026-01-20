"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Main Antares to Atlas converter orchestrator.
"""

from typing import Any

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
    def from_file(cls, parameters_file: str) -> "AntaresToAtlas":
        """Create converter from a parameters file.

        :param parameters_file: Path to YAML or JSON parameters file
        :type parameters_file: str
        :return: Configured AntaresToAtlas converter
        :rtype: AntaresToAtlas
        """
        parameters = AntaresToAtlasParameters.from_file(parameters_file)
        return cls(parameters)

    @classmethod
    def from_dict(cls, parameters_dict: dict[str, Any]) -> "AntaresToAtlas":
        """Create converter from a parameters dictionary.

        :param parameters_dict: Parameters as dictionary
        :type parameters_dict: dict[str, Any]
        :return: Configured AntaresToAtlas converter
        :rtype: AntaresToAtlas
        """
        parameters = AntaresToAtlasParameters.model_validate(parameters_dict)
        return cls(parameters)

    def _build_registry(self) -> ConverterRegistry:
        """Build the converter registry with standard and specific converters.

        The order of registration determines the execution order.
        Standard converters are registered first, followed by specific converters.

        :return: Configured converter registry
        :rtype: ConverterRegistry
        """
        registry = ConverterRegistry()

        registry.register_standard(NodeConverter)
        registry.register_standard(LoadConverter)
        registry.register_standard(WindConverter)
        registry.register_standard(PVConverter)
        registry.register_standard(HydroConverter)
        registry.register_standard(LinkConverter)
        registry.register_standard(ThermalConverter)
        registry.register_standard(NonDispatchableConverter)

        if self.parameters.hypothesis == "BP23":
            self._register_bp23_converters(registry)

        return registry

    def _register_bp23_converters(self, registry: ConverterRegistry) -> None:
        """Register BP23-specific converters.

        :param registry: Converter registry
        :type registry: ConverterRegistry
        """
        # Mixed fuel depends on thermal converter
        registry.register_specific(MixedFuelConverterBP23)

        # Independent storage converters
        registry.register_specific(ElectricVehicleConverterBP23)
        registry.register_specific(BatteryConverterBP23)

        # Gas-related converters
        registry.register_specific(ParticularMidPeakConverterBP23)
        registry.register_specific(P2GConverterBP23)

        # Multi-energy must run after all thermic units
        registry.register_specific(MultiEnergyConverterBP23)

        # DSR converter
        registry.register_specific(DSRConverterBP23)

        # PHS depends on hydro converter
        registry.register_specific(PHSConverterBP23)

        # Water value depends on PHS (must run after to account for new inflows)
        registry.register_specific(WaterValueConverterBP23)

        # Initial level computation
        registry.register_specific(InitialLevelConverterBP23)

        # Nuclear modulation (France-specific)
        registry.register_specific(NuclearModulationConverterBP23)

    def convert(self, antares_dataset: Any, atlas_dataset: Any) -> dict[str, dict]:
        """Execute the conversion process.

        :param antares_dataset: Antares input data marker (API object)
        :type antares_dataset: Any
        :param atlas_dataset: Atlas output data marker (API object)
        :type atlas_dataset: Any
        :return: Dictionary of conversion results from each converter
        :rtype: dict[str, dict]
        """
        logger.info("=" * 70)
        logger.info("Starting Antares to Atlas Conversion")
        logger.info(f"Antares Version: {self.parameters.antares_version}")
        logger.info(f"Hypothesis: {self.parameters.hypothesis}")
        logger.info(f"Market Areas: {', '.join(self.parameters.market_areas)}")
        logger.info(f"Scenario: {self.parameters.scenario}")
        logger.info("=" * 70)

        # Log parameters if verbose
        if self.parameters.verbose:
            logger.info("Conversion Parameters:")
            logger.info(self.parameters.model_dump_json(indent=2))

        # Create shared state for data sharing between converters
        shared_state: dict[str, Any] = {}

        # Execute all converters
        results = self.registry.execute_all(antares_dataset, atlas_dataset, self.parameters, shared_state)

        logger.info("=" * 70)
        logger.info("Conversion completed successfully")
        logger.info("=" * 70)

        return results

    def list_converters(self) -> dict[str, list[str]]:
        """List all registered converters.

        :return: Dictionary with 'standard' and 'specific' keys containing converter names
        :rtype: dict[str, list[str]]
        """
        return self.registry.get_converter_names()
