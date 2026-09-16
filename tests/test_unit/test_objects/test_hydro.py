"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.objects.equipment.hydro import Hydro
from atlas.objects.market.market_area import MarketArea
from atlas.objects.market_operator.portfolio import Portfolio
from atlas.objects.network.node import Node
from atlas.objects.network_operator.control_block import ControlBlock

CONTROL_BLOCK = ControlBlock(name="cb")
MARKET_AREA = MarketArea(name="ma", control_block=CONTROL_BLOCK)
NODE = Node(name="node", control_block=CONTROL_BLOCK, market_area=MARKET_AREA)
PORTFOLIO = Portfolio(name="portfolio", control_block=CONTROL_BLOCK, market_area=MARKET_AREA)


def _unit(volumes: list[float] | None = None) -> Hydro:
    return Hydro(
        name="unit",
        node=NODE,
        portfolio=PORTFOLIO,
        fragment_volumes=volumes,
        fragment_prices=[float(i) for i in range(len(volumes))] if volumes else None,
    )


def test_fragments_take_their_share_of_capacity():
    assert _unit([0.25, 0.75]).bid_volumes(capacity=100, minimal_fragment_size=10) == {0: 25.0, 1: 75.0}


def test_fragments_below_the_minimal_size_are_redistributed():
    # the 5 MW fragment is dropped, its volume spread over the two kept ones
    volumes = _unit([0.05, 0.25, 0.7]).bid_volumes(capacity=100, minimal_fragment_size=10)
    assert sorted(volumes) == [1, 2]
    assert sum(volumes.values()) == 100.0


def test_full_capacity_goes_to_the_middle_fragment_when_all_are_too_small():
    assert _unit([0.5, 0.5]).bid_volumes(capacity=100, minimal_fragment_size=60) == {1: 100}


def test_zero_capacity_keeps_every_fragment_empty():
    # no volume to redistribute, so the minimal size must not trigger the middle-fragment fallback
    assert _unit([0.5, 0.5]).bid_volumes(capacity=0, minimal_fragment_size=10) == {0: 0.0, 1: 0.0}


def test_unit_without_fragments_bids_nothing():
    assert _unit().bid_volumes(capacity=100, minimal_fragment_size=10) == {}
