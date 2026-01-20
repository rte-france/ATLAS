"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

BP23 (Bilan Prévisionnel 2023) specific converters.
"""

from typing import Any

from atlas.models.business_model import BusinessModel
from atlas.modules.antares_to_atlas.converters.base import SpecificConverter
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters

# Import legacy conversion functions
try:
    from atlas.modules.antares_to_atlas.models.hydro import initial_level, water_value
    from atlas.modules.antares_to_atlas.models.load import dsr
    from atlas.modules.antares_to_atlas.models.p2g import multi_energy, p2g_main, particular_mid_peak
    from atlas.modules.antares_to_atlas.models.storage import (
        battery,
        electric_vehicle,
        phs_closed,
        phs_fusion,
        phs_open,
    )
    from atlas.modules.antares_to_atlas.models.thermal import mixed_fuel, nuclear_modulation

    HAS_LEGACY = True
except ImportError:
    HAS_LEGACY = False


class MixedFuelConverterBP23(SpecificConverter):
    """Converter for mixed fuel thermal units (BP23 specific)."""

    supported_hypotheses = ["BP23"]

    @property
    def name(self) -> str:
        return "mixed_fuel"

    @property
    def description(self) -> str:
        return "Mixed Fuel Conversion"

    def convert(
        self,
        antares_dataset: Any,
        parameters: AntaresToAtlasParameters,
        shared_state: dict[str, Any],
    ) -> dict[str, list[BusinessModel]]:
        if not HAS_LEGACY:
            raise NotImplementedError("Mixed fuel conversion not yet implemented")

        # Retrieve data from thermal converter
        thermal_data = shared_state.get("thermal", {})
        thermic_parameter = thermal_data.get("thermic_parameter", {})
        thermic_properties = thermal_data.get("thermic_properties", {})

        return mixed_fuel.add_mixed_fuel(
            antares_dataset,
            thermic_parameter,
            thermic_properties,
            parameters,
        )


class ElectricVehicleConverterBP23(SpecificConverter):
    """Converter for electric vehicle storage (BP23 specific)."""

    supported_hypotheses = ["BP23"]

    @property
    def name(self) -> str:
        return "electric_vehicle"

    @property
    def description(self) -> str:
        return "Electric Vehicle Conversion"

    def convert(
        self,
        antares_dataset: Any,
        parameters: AntaresToAtlasParameters,
        shared_state: dict[str, Any],
    ) -> dict[str, list[BusinessModel]]:
        if not HAS_LEGACY:
            raise NotImplementedError("EV conversion not yet implemented")

        return electric_vehicle.convert_electric_vehicle(antares_dataset, parameters)


class ParticularMidPeakConverterBP23(SpecificConverter):
    """Converter for particular mid/peak gas units (BP23 specific)."""

    supported_hypotheses = ["BP23"]

    @property
    def name(self) -> str:
        return "particular_mid_peak"

    @property
    def description(self) -> str:
        return "Specific Gas Units Conversion"

    def convert(
        self,
        antares_dataset: Any,
        parameters: AntaresToAtlasParameters,
        shared_state: dict[str, Any],
    ) -> tuple[dict[str, list[BusinessModel]]]:
        if not HAS_LEGACY:
            raise NotImplementedError("Particular mid/peak conversion not yet implemented")

        return particular_mid_peak.pcomp_mid(antares_dataset, parameters), particular_mid_peak.pcomp_peak(
            antares_dataset, parameters
        )


class P2GConverterBP23(SpecificConverter):
    """Converter for Power-to-Gas units (BP23 specific)."""

    supported_hypotheses = ["BP23"]

    @property
    def name(self) -> str:
        return "p2g"

    @property
    def description(self) -> str:
        return "Power To Gas Conversion"

    def convert(
        self,
        antares_dataset: Any,
        parameters: AntaresToAtlasParameters,
        shared_state: dict[str, Any],
    ) -> dict[str, list[BusinessModel]]:
        if not HAS_LEGACY:
            raise NotImplementedError("P2G conversion not yet implemented")

        return p2g_main.P2G(antares_dataset, parameters)


class MultiEnergyConverterBP23(SpecificConverter):
    """Converter for multi-energy modeling (BP23 specific).

    This should run after all thermic units are created.
    """

    supported_hypotheses = ["BP23"]

    @property
    def name(self) -> str:
        return "multi_energy"

    @property
    def description(self) -> str:
        return "Multi-Energy Variable Cost Update"

    def should_run(self, parameters: AntaresToAtlasParameters) -> bool:
        """Only run if multi-energy is enabled."""
        if not parameters.use_multi_energy:
            return False
        return super().should_run(parameters)

    def convert(
        self,
        antares_dataset: Any,
        parameters: AntaresToAtlasParameters,
        shared_state: dict[str, Any],
    ) -> dict[str, list[BusinessModel]]:
        if not HAS_LEGACY:
            raise NotImplementedError("Multi-energy conversion not yet implemented")

        return multi_energy.update_variable_cost_unit_using_gas(antares_dataset, parameters)


class BatteryConverterBP23(SpecificConverter):
    """Converter for battery storage (BP23 specific)."""

    supported_hypotheses = ["BP23"]

    @property
    def name(self) -> str:
        return "battery"

    @property
    def description(self) -> str:
        return "Battery Conversion"

    def convert(
        self,
        antares_dataset: Any,
        parameters: AntaresToAtlasParameters,
        shared_state: dict[str, Any],
    ) -> dict[str, list[BusinessModel]]:
        if not HAS_LEGACY:
            raise NotImplementedError("Battery conversion not yet implemented")

        return battery.creation_battery(antares_dataset, parameters)


class DSRConverterBP23(SpecificConverter):
    """Converter for Demand Side Response (BP23 specific)."""

    supported_hypotheses = ["BP23"]

    @property
    def name(self) -> str:
        return "dsr"

    @property
    def description(self) -> str:
        return "Demand Side Response Conversion"

    def convert(
        self,
        antares_dataset: Any,
        parameters: AntaresToAtlasParameters,
        shared_state: dict[str, Any],
    ) -> dict[str, Any]:
        if not HAS_LEGACY:
            raise NotImplementedError("DSR conversion not yet implemented")

        # France-specific DSR
        if "fr" in parameters.market_areas:
            return dsr.dsr_fr(antares_dataset, parameters)

        return dsr.dsr_other_countries(antares_dataset, parameters)


class PHSConverterBP23(SpecificConverter):
    """Converter for Pumped Hydro Storage (BP23 specific)."""

    supported_hypotheses = ["BP23"]

    @property
    def name(self) -> str:
        return "phs"

    @property
    def description(self) -> str:
        return "Pumped Hydraulic Storage Conversion"

    def convert(
        self,
        antares_dataset: Any,
        parameters: AntaresToAtlasParameters,
        shared_state: dict[str, Any],
    ) -> dict[str, Any]:
        if not HAS_LEGACY:
            raise NotImplementedError("PHS conversion not yet implemented")

        # Retrieve hydro data
        hydro_data = shared_state.get("hydro", {})
        hydro_reservoirs = hydro_data.get("hydro_reservoirs", {})
        inflows_dictionary = hydro_data.get("inflows_dictionary", {})

        # PHS closed
        closed_phs_list = phs_closed.creation_phs_closed(antares_dataset, hydro_reservoirs, parameters)

        # PHS open
        open_phs_list, inflows_dictionary = phs_open.creation_phs_open(
            antares_dataset,
            hydro_reservoirs,
            inflows_dictionary,
            parameters,
        )

        # France-specific open PHS
        if "fr" in parameters.market_areas:
            open_phs_list = phs_open.creation_phs_open_fr(
                antares_dataset,
                hydro_reservoirs,
                open_phs_list,
                parameters,
            )

        # PHS Fusion
        phs_fusion.fusion(closed_phs_list, open_phs_list, parameters)

        return {"inflows_dictionary": inflows_dictionary}


class WaterValueConverterBP23(SpecificConverter):
    """Converter for water value computation (BP23 specific).

    This should run after PHS conversion to account for new inflows and reservoir sizes.
    """

    supported_hypotheses = ["BP23"]

    @property
    def name(self) -> str:
        return "water_value"

    @property
    def description(self) -> str:
        return "Water Values Computation"

    def should_run(self, parameters: AntaresToAtlasParameters) -> bool:
        """Only run if water value is enabled."""
        if not parameters.use_water_value:
            return False
        return super().should_run(parameters)

    def convert(
        self,
        antares_dataset: Any,
        parameters: AntaresToAtlasParameters,
        shared_state: dict[str, Any],
    ) -> dict[str, Any]:
        if not HAS_LEGACY:
            raise NotImplementedError("Water value conversion not yet implemented")

        # Get updated inflows from PHS converter if available
        phs_data = shared_state.get("phs", {})
        inflows_dictionary = phs_data.get("inflows_dictionary")

        # Fallback to original hydro data if PHS didn't update it
        if inflows_dictionary is None:
            hydro_data = shared_state.get("hydro", {})
            inflows_dictionary = hydro_data.get("inflows_dictionary", {})

        return water_value.compute_water_value(antares_dataset, inflows_dictionary, parameters)


class InitialLevelConverterBP23(SpecificConverter):
    """Converter for initial level computation (BP23 specific)."""

    supported_hypotheses = ["BP23"]

    @property
    def name(self) -> str:
        return "initial_level"

    @property
    def description(self) -> str:
        return "InitialLevel Computation"

    def convert(
        self,
        antares_dataset: Any,
        parameters: AntaresToAtlasParameters,
        shared_state: dict[str, Any],
    ) -> dict[str, Any]:
        if not HAS_LEGACY:
            raise NotImplementedError("Initial level conversion not yet implemented")

        return initial_level.initial_level_computation(antares_dataset, parameters)


class NuclearModulationConverterBP23(SpecificConverter):
    """Converter for nuclear modulation (BP23 specific, France only)."""

    supported_hypotheses = ["BP23"]
    required_market_areas = ["fr"]

    @property
    def name(self) -> str:
        return "nuclear_modulation"

    @property
    def description(self) -> str:
        return "Nuclear Modulation Conversion"

    def convert(
        self,
        antares_dataset: Any,
        parameters: AntaresToAtlasParameters,
        shared_state: dict[str, Any],
    ) -> dict[str, Any]:
        if not HAS_LEGACY:
            raise NotImplementedError("Nuclear modulation conversion not yet implemented")

        return nuclear_modulation.add_nuclear_modulation(antares_dataset, parameters)
