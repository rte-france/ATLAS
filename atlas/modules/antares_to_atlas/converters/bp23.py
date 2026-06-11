"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

BP23 (Bilan Prévisionnel 2023) specific converters.
"""

from antares.craft.model.study import Study

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.antares_to_atlas.converters.base import Converter
from atlas.modules.antares_to_atlas.models.hydro import compute_initial_levels, compute_water_values
from atlas.modules.antares_to_atlas.models.load.dsr import convert_dsr_fr_units, convert_dsr_other_units
from atlas.modules.antares_to_atlas.models.p2g.multi_energy import update_variable_cost_for_gas_units
from atlas.modules.antares_to_atlas.models.p2g.p2g import convert_p2g_units
from atlas.modules.antares_to_atlas.models.p2g.particular_mid_peak import (
    convert_pcomp_mid_units,
    convert_pcomp_peak_units,
)
from atlas.modules.antares_to_atlas.models.storage import (
    convert_battery_units,
    convert_electric_vehicle_fr_units,
    convert_electric_vehicle_units,
    convert_phs_closed_units,
    convert_phs_open_fr,
    convert_phs_open_units,
    merge_open_and_closed_phs,
)
from atlas.modules.antares_to_atlas.models.thermal import add_nuclear_modulation, convert_mixed_fuel_units
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters, ConvertersTags


class BatteryConverterBP23(Converter):
    name = "battery"
    description = "Battery Storage Conversion"
    tags = [ConvertersTags.BATTERY]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_battery_units(study, parameters, atlas_dataset)


class ElectricVehicleConverterBP23(Converter):
    name = "electric_vehicle"
    description = "Electric Vehicle Conversion (standard)"
    tags = [ConvertersTags.STORAGE]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_electric_vehicle_units(study, parameters, atlas_dataset)


class ElectricVehicleFRConverterBP23(Converter):
    name = "electric_vehicle_fr"
    description = "Electric Vehicle Conversion (France)"
    required_market_areas = ["fr"]
    tags = [ConvertersTags.STORAGE]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_electric_vehicle_fr_units(study, parameters, atlas_dataset)


class PHSClosedConverterBP23(Converter):
    name = "phs_closed"
    description = "Closed-loop Pumped Hydro Storage Conversion"
    tags = [ConvertersTags.STORAGE, ConvertersTags.HYDRO]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_phs_closed_units(study, parameters, atlas_dataset)


class PHSOpenConverterBP23(Converter):
    name = "phs_open"
    description = "Open-loop Pumped Hydro Storage Conversion (non-FR)"
    tags = [ConvertersTags.STORAGE, ConvertersTags.HYDRO]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_phs_open_units(study, parameters, atlas_dataset)


class PHSOpenFRConverterBP23(Converter):
    name = "phs_open_fr"
    description = "Open-loop Pumped Hydro Storage Conversion (France)"
    required_market_areas = ["fr"]
    tags = [ConvertersTags.STORAGE, ConvertersTags.HYDRO]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_phs_open_fr(study, parameters, atlas_dataset)


class PHSFusionConverterBP23(Converter):
    name = "phs_fusion"
    description = "Merge open and closed PHS equipment by node"
    tags = [ConvertersTags.STORAGE, ConvertersTags.HYDRO]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        closed_list: list[str] = []
        open_list: list[str] = []
        for storage in atlas_dataset.storage:
            if storage.name.endswith("_step_open"):
                open_list.append(storage.name.removesuffix("_step_open"))
            elif storage.name.endswith("_step_closed"):
                closed_list.append(storage.name.removesuffix("_step_closed"))
        return merge_open_and_closed_phs(atlas_dataset, closed_list, open_list, parameters)


class MixedFuelConverterBP23(Converter):
    name = "mixed_fuel"
    description = "Mixed Fuel Conversion"
    tags = [ConvertersTags.THERMAL]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_mixed_fuel_units(study, parameters, atlas_dataset)


class ParticularMidConverterBP23(Converter):
    name = "particular_mid_units"
    description = "Specific Gas Units Conversion (mid)"
    tags = [ConvertersTags.THERMAL]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_pcomp_mid_units(study, parameters, atlas_dataset)


class ParticularPeakConverterBP23(Converter):
    name = "particular_peak_units"
    description = "Specific Gas Units Conversion (peak)"
    tags = [ConvertersTags.THERMAL]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_pcomp_peak_units(study, parameters, atlas_dataset)


class P2GConverterBP23(Converter):
    name = "p2g"
    description = "Power To Gas Conversion"
    tags = [ConvertersTags.P2G]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_p2g_units(study, parameters, atlas_dataset)


class MultiEnergyConverterBP23(Converter):
    name = "multi_energy"
    description = "Multi-Energy Variable Cost Update"
    tags = [ConvertersTags.MULTI_ENERGY]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return update_variable_cost_for_gas_units(study, parameters, atlas_dataset)


class DSRConverterBP23(Converter):
    name = "dsr"
    description = "Demand-Side Response Conversion (other countries)"
    tags = [ConvertersTags.DEMAND]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_dsr_other_units(study, parameters, atlas_dataset)


class DSRFRConverterBP23(Converter):
    name = "dsr_fr"
    description = "Demand-Side Response Conversion (France)"
    required_market_areas = ["fr"]
    tags = [ConvertersTags.DEMAND]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_dsr_fr_units(study, parameters, atlas_dataset)


class WaterValueConverterBP23(Converter):
    name = "water_value"
    description = "Water Value Computation"
    tags = [ConvertersTags.HYDRO]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return compute_water_values(study, parameters, atlas_dataset)


class InitialLevelConverterBP23(Converter):
    name = "initial_level"
    description = "Initial Storage Level Configuration"
    tags = [ConvertersTags.STORAGE, ConvertersTags.HYDRO]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return compute_initial_levels(study, parameters, atlas_dataset)


class NuclearModulationConverterBP23(Converter):
    name = "nuclear_modulation"
    description = "Nuclear Modulation (France)"
    required_market_areas = ["fr"]
    tags = [ConvertersTags.THERMAL]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return add_nuclear_modulation(study, parameters, atlas_dataset)
