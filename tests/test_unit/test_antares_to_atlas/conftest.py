"""
Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Shared fixtures for antares_to_atlas unit tests.
"""

import pytest

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.antares_to_atlas.parameters import AntaresToAtlasParameters
from atlas.objects.market.market_area import MarketArea
from atlas.objects.market_operator.portfolio import Portfolio
from atlas.objects.network.node import Node
from atlas.objects.network_operator.control_block import ControlBlock

_START = "2025-01-01T00:00:00"
_EXEC = "2025-01-01T00:00:00"
_OUTPUT = "output_test"


def make_params(**overrides) -> AntaresToAtlasParameters:
    """Build a minimal AntaresToAtlasParameters, applying any field overrides."""
    base: dict = {
        "start_date": _START,
        "execution_date": _EXEC,
        "output_name": _OUTPUT,
        "market_areas": ["fr"],
        "scenario": 1,
    }
    base.update(overrides)
    return AntaresToAtlasParameters.model_validate(base)


def make_area_dataset(*area_names: str) -> AtlasDataset:
    """Build an AtlasDataset pre-populated with Node/Portfolio/MarketArea/ControlBlock for each area."""
    dataset = AtlasDataset()
    for name in area_names:
        ctrl = ControlBlock(name=name)
        ma = MarketArea(name=name, control_block=ctrl)
        node = Node(name=name, control_block=ctrl, market_area=ma)
        portfolio = Portfolio(name=f"portfolio_{name}", control_block=ctrl, market_area=ma)
        dataset.control_block.add(ctrl)
        dataset.market_area.add(ma)
        dataset.node.add(node)
        dataset.portfolio.add(portfolio)
    return dataset


@pytest.fixture
def minimal_params() -> AntaresToAtlasParameters:
    return make_params()


@pytest.fixture
def fr_dataset() -> AtlasDataset:
    return make_area_dataset("fr")


@pytest.fixture
def fr_de_dataset() -> AtlasDataset:
    return make_area_dataset("fr", "de")
