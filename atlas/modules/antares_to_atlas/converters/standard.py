"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.study import Study

from atlas.core.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.antares_to_atlas.converters.base import Converter
from atlas.modules.antares_to_atlas.models.hydro.hydro import convert_hydro_units
from atlas.modules.antares_to_atlas.models.load.load import convert_load_units
from atlas.modules.antares_to_atlas.models.other.other_non_dispatchable import convert_other_non_dispatchable_units
from atlas.modules.antares_to_atlas.models.res.solar import convert_solar_units
from atlas.modules.antares_to_atlas.models.res.wind import convert_wind_units
from atlas.modules.antares_to_atlas.models.storage.battery import convert_battery_units
from atlas.modules.antares_to_atlas.models.storage.phs_closed import convert_phs_closed_units
from atlas.modules.antares_to_atlas.models.system_structure.link import convert_links
from atlas.modules.antares_to_atlas.models.system_structure.node import convert_system_structure
from atlas.modules.antares_to_atlas.models.thermal.thermal import convert_thermal_units
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters, ConvertersTags


class HydroConverter(Converter):
    name = "hydro"
    description = "Hydraulic Conversion"
    tags = [ConvertersTags.HYDRO]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_hydro_units(study, parameters, atlas_dataset)


class LinkConverter(Converter):
    name = "link"
    description = "Link Conversion"
    tags = [ConvertersTags.SYSTEM]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_links(study, parameters, atlas_dataset)


class LoadConverter(Converter):
    name = "load"
    description = "Load Conversion"
    tags = [ConvertersTags.LOAD]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_load_units(study, parameters, atlas_dataset)


class SystemStructureConverter(Converter):
    """Converter for Node, MarketArea, Portfolio and ControlBlock creation."""

    name = "node"
    description = "Node, MarketArea, Portfolio and ControlBlock Conversion"
    tags = [ConvertersTags.SYSTEM]
    always_run = True  # All other converters depend on the nodes/portfolios it creates

    def convert(
        self,
        study: Study,
        parameters: AntaresToAtlasParameters,
        atlas_dataset: AtlasDataset,
    ) -> AtlasDataset:
        return convert_system_structure(study, parameters, atlas_dataset)


class NonDispatchableConverter(Converter):
    name = "non_dispatchable"
    description = "Non-dispatchable Conversion"
    tags = [ConvertersTags.RENEWABLE]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_other_non_dispatchable_units(study, parameters, atlas_dataset)


class SolarConverter(Converter):
    name = "solar"
    description = "Solar Conversion"
    tags = [ConvertersTags.RENEWABLE]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_solar_units(study, parameters, atlas_dataset)


class ThermalConverter(Converter):
    """Converter for thermal generation units."""

    name = "thermal"
    description = "Thermal Conversion"
    tags = [ConvertersTags.THERMAL]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_thermal_units(study, parameters, atlas_dataset)


class WindConverter(Converter):
    name = "wind"
    description = "Wind Conversion"
    tags = [ConvertersTags.RENEWABLE]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_wind_units(study, parameters, atlas_dataset)


class BatteryConverter(Converter):
    name = "battery"
    description = "Battery Storage Conversion"
    tags = [ConvertersTags.BATTERY]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_battery_units(study, parameters, atlas_dataset)


class PHSClosedConverter(Converter):
    name = "phs_closed"
    description = "Closed-loop Pumped Hydro Storage Conversion"
    tags = [ConvertersTags.STORAGE, ConvertersTags.HYDRO]

    def convert(self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset) -> AtlasDataset:
        return convert_phs_closed_units(study, parameters, atlas_dataset)
