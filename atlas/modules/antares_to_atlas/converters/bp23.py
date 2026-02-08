"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

BP23 (Bilan Prévisionnel 2023) specific converters.
"""

from antares.craft.model.study import Study

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.models.business_model import BusinessModel
from atlas.modules.antares_to_atlas.converters.base import Converter
from atlas.modules.antares_to_atlas.models.hydro import compute_water_values, set_initial_levels
from atlas.modules.antares_to_atlas.models.load.dsr import convert_dsr_units
from atlas.modules.antares_to_atlas.models.p2g.p2g import convert_p2g_units
from atlas.modules.antares_to_atlas.models.storage.battery import convert_battery_units
from atlas.modules.antares_to_atlas.models.storage.electric_vehicle import convert_electric_vehicle_units
from atlas.modules.antares_to_atlas.models.storage.phs_closed import convert_phs_closed_units
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
        self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset
    ) -> list[BusinessModel]:
        return convert_battery_units(study, parameters, atlas_dataset)


class ElectricVehicleConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "electric_vehicle"

    @property
    def description(self) -> str:
        return "Electric Vehicle Conversion"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset
    ) -> list[BusinessModel]:
        return convert_electric_vehicle_units(study, parameters, atlas_dataset)


class PHSClosedConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "phs"

    @property
    def description(self) -> str:
        return "Pumped Hydro Storage Conversion"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset
    ) -> list[BusinessModel]:
        return convert_phs_closed_units(study, parameters, atlas_dataset)


class MixedFuelConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "mixed_fuel"

    @property
    def description(self) -> str:
        return "Mixed Fuel Conversion"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset
    ) -> list[BusinessModel]:
        return convert_mixed_fuel(study, parameters, atlas_dataset)


class ParticularMidPeakConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "particular_mid_peak"

    @property
    def description(self) -> str:
        return "Specific Gas Units Conversion"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset
    ) -> list[BusinessModel]:
        return convert_particular_mid_peak(study, parameters, atlas_dataset)


class P2GConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "p2g"

    @property
    def description(self) -> str:
        return "Power To Gas Conversion"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset
    ) -> list[BusinessModel]:
        return convert_p2g_units(study, parameters, atlas_dataset)


class MultiEnergyConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "multi_energy"

    @property
    def description(self) -> str:
        return "Multi-Energy Variable Cost Update"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset
    ) -> list[BusinessModel]:
        return apply_multi_energy_costs(study, parameters, atlas_dataset)


class DSRConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "dsr"

    @property
    def description(self) -> str:
        return "Demand-Side Response Conversion"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset
    ) -> list[BusinessModel]:
        return convert_dsr_units(study, parameters, atlas_dataset)


class WaterValueConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "water_value"

    @property
    def description(self) -> str:
        return "Water Value Computation"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset
    ) -> list[BusinessModel]:
        return compute_water_values(study, parameters, atlas_dataset)


class InitialLevelConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "initial_level"

    @property
    def description(self) -> str:
        return "Initial Storage Level Configuration"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset
    ) -> list[BusinessModel]:
        return set_initial_levels(study, parameters, atlas_dataset)


class NuclearModulationConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "nuclear_modulation"

    @property
    def description(self) -> str:
        return "Nuclear Modulation (France)"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset
    ) -> list[BusinessModel]:
        return apply_nuclear_modulation(study, parameters, atlas_dataset)
