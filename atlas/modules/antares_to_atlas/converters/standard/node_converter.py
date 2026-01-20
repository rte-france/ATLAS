"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Node, MarketArea, Portfolio and ControlBlock converter.
"""

from typing import Any

from atlas.models.business_model import BusinessModel
from atlas.modules.antares_to_atlas.converters.base import Converter
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters

# Import legacy conversion function
# This allows gradual migration from legacy code
try:
    from atlas.modules.antares_to_atlas.models.system_structure import node as legacy_node

    HAS_LEGACY = True
except ImportError:
    HAS_LEGACY = False


class NodeConverter(Converter):
    """Converter for Node, MarketArea, Portfolio and ControlBlock creation.

    This converter creates the basic system structure including:
    - Nodes (geographical locations)
    - Market Areas
    - Portfolios (producer/consumer/both)
    - Control Blocks
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
        antares_dataset: Any,
        parameters: AntaresToAtlasParameters,
        shared_state: dict[str, Any],
    ) -> dict[str, list[BusinessModel]]:
        """Convert node and related structures.

        :param antares_dataset: Antares input data marker
        :type antares_dataset: Any
        :param atlas_dataset: Atlas output data marker
        :type atlas_dataset: Any
        :param parameters: Conversion parameters
        :type parameters: AntaresToAtlasParameters
        :param shared_state: Shared state dictionary
        :type shared_state: dict[str, Any]
        :return: Empty dict (no data to share)
        :rtype: dict[str, Any]
        """
        if HAS_LEGACY:
            # Use legacy conversion for now
            legacy_node.conversion_node(antares_dataset, parameters)
        else:
            # TODO: Implement new conversion logic here
            raise NotImplementedError("Node conversion not yet implemented without legacy code")

        return {}
