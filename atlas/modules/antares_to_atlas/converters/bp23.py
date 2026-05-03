"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

BP23 (Bilan Prévisionnel 2023) specific converters.
"""

from antares.craft.model.study import Study

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.antares_to_atlas.converters.base import Converter
from atlas.modules.antares_to_atlas.models.hydro import compute_initial_levels, compute_water_values
from atlas.modules.antares_to_atlas.models.load.dsr import convert_dsr_units
from atlas.modules.antares_to_atlas.models.p2g.multi_energy import update_variable_cost_for_gas_units
from atlas.modules.antares_to_atlas.models.p2g.p2g import convert_p2g_units
from atlas.modules.antares_to_atlas.models.p2g.particular_mid_peak import (
    convert_pcomp_mid_units,
    convert_pcomp_peak_units,
)
from atlas.modules.antares_to_atlas.models.storage import (
    convert_battery_units,
    convert_electric_vehicle_units,
    convert_phs_closed_units,
)
from atlas.modules.antares_to_atlas.models.thermal import add_nuclear_modulation, convert_mixed_fuel_units
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


class BatteryConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "battery"

    @property
    def description(self) -> str:
        return "Battery Storage Conversion"

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_battery_units(study, parameters, atlas_dataset)


class ElectricVehicleConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "electric_vehicle"

    @property
    def description(self) -> str:
        return "Electric Vehicle Conversion"

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_electric_vehicle_units(study, parameters, atlas_dataset)


class PHSClosedConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "phs"

    @property
    def description(self) -> str:
        return "Pumped Hydro Storage Conversion"

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_phs_closed_units(study, parameters, atlas_dataset)


class MixedFuelConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "mixed_fuel"

    @property
    def description(self) -> str:
        return "Mixed Fuel Conversion"

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_mixed_fuel_units(study, parameters, atlas_dataset)


class ParticularMidConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "particular_mid_units"

    @property
    def description(self) -> str:
        return "Specific Gas Units Conversion"

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_pcomp_mid_units(study, parameters, atlas_dataset)


class ParticularPeakConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "particular_peak_units"

    @property
    def description(self) -> str:
        return "Specific Gas Units Conversion"

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_pcomp_peak_units(study, parameters, atlas_dataset)


class P2GConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "p2g"

    @property
    def description(self) -> str:
        return "Power To Gas Conversion"

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_p2g_units(study, parameters, atlas_dataset)


class MultiEnergyConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "multi_energy"

    @property
    def description(self) -> str:
        return "Multi-Energy Variable Cost Update"

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return update_variable_cost_for_gas_units(study, parameters, atlas_dataset)


class DSRConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "dsr"

    @property
    def description(self) -> str:
        return "Demand-Side Response Conversion"

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_dsr_units(study, parameters, atlas_dataset)


class WaterValueConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "water_value"

    @property
    def description(self) -> str:
        return "Water Value Computation"

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return compute_water_values(study, parameters, atlas_dataset)


class InitialLevelConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "initial_level"

    @property
    def description(self) -> str:
        return "Initial Storage Level Configuration"

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return compute_initial_levels(study, parameters, atlas_dataset)


class NuclearModulationConverterBP23(Converter):
    @property
    def name(self) -> str:
        return "nuclear_modulation"

    @property
    def description(self) -> str:
        return "Nuclear Modulation (France)"

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return add_nuclear_modulation(study, parameters, atlas_dataset)
