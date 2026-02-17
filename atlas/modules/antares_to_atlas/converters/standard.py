"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from antares.craft.model.study import Study

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.models.business_model import BusinessModel
from atlas.modules.antares_to_atlas.converters.base import Converter
from atlas.modules.antares_to_atlas.models.hydro.hydraulic import convert_hydro_units
from atlas.modules.antares_to_atlas.models.load.load import convert_load_units
from atlas.modules.antares_to_atlas.models.other.other_non_dispatchable import convert_other_non_dispatchable_units
from atlas.modules.antares_to_atlas.models.res.solar import convert_solar_units
from atlas.modules.antares_to_atlas.models.res.wind import convert_wind_units
from atlas.modules.antares_to_atlas.models.system_structure.link import convert_links
from atlas.modules.antares_to_atlas.models.system_structure.node import convert_system_structure
from atlas.modules.antares_to_atlas.models.thermal.thermal import convert_thermal_units
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


class HydroConverter(Converter):
    @property
    def name(self) -> str:
        return "hydro"

    @property
    def description(self) -> str:
        return "Hydraulic Conversion"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset
    ) -> list[BusinessModel]:
        return convert_hydro_units(study, parameters, atlas_dataset)


class LinkConverter(Converter):
    @property
    def name(self) -> str:
        return "link"

    @property
    def description(self) -> str:
        return "Link Conversion"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset
    ) -> list[BusinessModel]:
        return convert_links(study, parameters, atlas_dataset)


class LoadConverter(Converter):
    @property
    def name(self) -> str:
        return "load"

    @property
    def description(self) -> str:
        return "Load Conversion"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset
    ) -> list[BusinessModel]:
        return convert_load_units(study, parameters, atlas_dataset)


class NodeConverter(Converter):
    """Converter for Node, MarketArea, Portfolio and ControlBlock creation.

    This converter creates the basic system structure including:
    - Nodes (geographical locations)
    - Market Areas (economic zones)
    - Portfolios (producer/consumer/both)
    - Control Blocks (operational zones)

    The converter orchestrates the conversion by calling the business logic
    in the models.system_structure module.
    """

    @property
    def name(self) -> str:
        """Return converter name."""
        return "node"

    @property
    def description(self) -> str:
        """Return converter description."""
        return "Node, MarketArea, Portfolio and ControlBlock Conversion"

    def convert(
        self,
        study: Study,
        parameters: AntaresToAtlasParameters,
        atlas_dataset: AtlasDataset,
    ) -> AtlasDataset:
        """Convert node and related structures.

        :param study: Antares study object
        :type study: Study
        :param parameters: Conversion parameters
        :type parameters: AntaresToAtlasParameters
        :param atlas_dataset: Atlas dataset
        :type atlas_dataset: AtlasDataset
        :return: List of all created business models
        :rtype: list[BusinessModel]
        """

        return convert_system_structure(study, parameters, atlas_dataset)


class NonDispatchableConverter(Converter):
    @property
    def name(self) -> str:
        return "non_dispatchable"

    @property
    def description(self) -> str:
        return "Non-dispatchable Conversion"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset
    ) -> list[BusinessModel]:
        return convert_other_non_dispatchable_units(study, parameters, atlas_dataset)


class SolarConverter(Converter):
    @property
    def name(self) -> str:
        return "solar"

    @property
    def description(self) -> str:
        return "Solar Conversion"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset
    ) -> list[BusinessModel]:
        return convert_solar_units(study, parameters, atlas_dataset)


class ThermalConverter(Converter):
    """Converter for thermal generation units.

    This converter orchestrates the conversion by calling the business logic
    in the models.thermal module.
    """

    @property
    def name(self) -> str:
        return "thermal"

    @property
    def description(self) -> str:
        return "Thermic Conversion"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset
    ) -> list[BusinessModel]:
        """Convert thermal generation units.

        :param study: Antares study object
        :type study: Study
        :param parameters: Conversion parameters
        :type parameters: AntaresToAtlasParameters
        :param atlas_dataset: Atlas dataset
        :type atlas_dataset: AtlasDataset
        :return: List of created Thermal equipment
        :rtype: list[BusinessModel]
        """

        thermal_units = convert_thermal_units(study, parameters, atlas_dataset)
        return thermal_units


class WindConverter(Converter):
    @property
    def name(self) -> str:
        return "wind"

    @property
    def description(self) -> str:
        return "Wind Conversion"

    def convert(
        self, study: Study, parameters: AntaresToAtlasParameters, atlas_dataset: AtlasDataset
    ) -> list[BusinessModel]:
        return convert_wind_units(study, parameters, atlas_dataset)
