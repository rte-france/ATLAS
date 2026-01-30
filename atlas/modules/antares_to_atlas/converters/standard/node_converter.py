"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Node, MarketArea, Portfolio and ControlBlock converter.
"""

from antares.craft.model.study import Study

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.antares_to_atlas.converters.base import Converter
from atlas.modules.antares_to_atlas.models.system_structure.node import convert_system_structure
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters


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
