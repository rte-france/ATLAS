"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

BP23 (Bilan Prévisionnel 2023) specific converters.
"""

from typing import Any

from antares.craft.model.study import Study

from atlas.models.business_model import BusinessModel
from atlas.modules.antares_to_atlas.converters.base import Converter
from atlas.modules.antares_to_atlas.models.hydro import compute_water_values, set_initial_levels
from atlas.modules.antares_to_atlas.models.load import convert_dsr
from atlas.modules.antares_to_atlas.models.p2g import convert_p2g
from atlas.modules.antares_to_atlas.models.storage import convert_batteries, convert_electric_vehicles, convert_phs
from atlas.modules.antares_to_atlas.models.thermal import (
    apply_multi_energy_costs,
    apply_nuclear_modulation,
    convert_mixed_fuel,
    convert_particular_mid_peak,
)
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


class BatteryConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "battery"

    @property
    def description(self) -> str:
        return "Battery Storage Conversion"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, shared_state: dict[str, Any]
    ) -> list[BusinessModel]:
        return convert_batteries(study, parameters, shared_state)


class ElectricVehicleConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "electric_vehicle"

    @property
    def description(self) -> str:
        return "Electric Vehicle Conversion"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, shared_state: dict[str, Any]
    ) -> list[BusinessModel]:
        return convert_electric_vehicles(study, parameters, shared_state)


class PHSConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "phs"

    @property
    def description(self) -> str:
        return "Pumped Hydro Storage Conversion"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, shared_state: dict[str, Any]
    ) -> list[BusinessModel]:
        return convert_phs(study, parameters, shared_state)


class MixedFuelConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "mixed_fuel"

    @property
    def description(self) -> str:
        return "Mixed Fuel Conversion"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, shared_state: dict[str, Any]
    ) -> list[BusinessModel]:
        return convert_mixed_fuel(study, parameters, shared_state)


class ParticularMidPeakConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "particular_mid_peak"

    @property
    def description(self) -> str:
        return "Specific Gas Units Conversion"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, shared_state: dict[str, Any]
    ) -> list[BusinessModel]:
        return convert_particular_mid_peak(study, parameters, shared_state)


class P2GConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "p2g"

    @property
    def description(self) -> str:
        return "Power To Gas Conversion"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, shared_state: dict[str, Any]
    ) -> list[BusinessModel]:
        return convert_p2g(study, parameters, shared_state)


class MultiEnergyConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "multi_energy"

    @property
    def description(self) -> str:
        return "Multi-Energy Variable Cost Update"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, shared_state: dict[str, Any]
    ) -> list[BusinessModel]:
        return apply_multi_energy_costs(study, parameters, shared_state)


class DSRConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "dsr"

    @property
    def description(self) -> str:
        return "Demand-Side Response Conversion"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, shared_state: dict[str, Any]
    ) -> list[BusinessModel]:
        return convert_dsr(study, parameters, shared_state)


class WaterValueConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "water_value"

    @property
    def description(self) -> str:
        return "Water Value Computation"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, shared_state: dict[str, Any]
    ) -> list[BusinessModel]:
        return compute_water_values(study, parameters, shared_state)


class InitialLevelConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "initial_level"

    @property
    def description(self) -> str:
        return "Initial Storage Level Configuration"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, shared_state: dict[str, Any]
    ) -> list[BusinessModel]:
        return set_initial_levels(study, parameters, shared_state)


class NuclearModulationConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "nuclear_modulation"

    @property
    def description(self) -> str:
        return "Nuclear Modulation (France)"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, shared_state: dict[str, Any]
    ) -> list[BusinessModel]:
        return apply_nuclear_modulation(study, parameters, shared_state)
