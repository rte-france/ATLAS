"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Node, MarketArea, Portfolio and ControlBlock converter.
"""

from typing import Any

from antares.craft.model.study import Study

from atlas.models.business_model import BusinessModel
from atlas.modules.antares_to_atlas.converters.base import Converter
from atlas.modules.antares_to_atlas.models.system_structure import convert_nodes
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
        shared_state: dict[str, Any],
    ) -> list[BusinessModel]:
        """Convert node and related structures.

        :param study: Antares study object
        :type study: Study
        :param parameters: Conversion parameters
        :type parameters: AntaresToAtlasParameters
        :param shared_state: Shared state dictionary
        :type shared_state: dict[str, Any]
        :return: List of all created business models
        :rtype: list[BusinessModel]
        """
        # Call the business logic in the models module
        nodes, market_areas, portfolios, control_blocks = convert_nodes(study, parameters, shared_state)

        # Return all created objects
        return nodes + market_areas + portfolios + control_blocks
