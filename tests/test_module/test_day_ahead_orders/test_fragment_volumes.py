"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from types import SimpleNamespace

from atlas.modules.day_ahead_orders.steps.hydro import HydraulicBidding
from atlas.objects.equipment.hydro import FragmentData


def _bidding(minimal_size: float) -> HydraulicBidding:
    """HydraulicBidding stub exposing only the threshold ``_fragment_volumes`` needs."""
    bidding = object.__new__(HydraulicBidding)
    bidding.parameters = SimpleNamespace(hydraulic_minimal_fragment_size=minimal_size)
    return bidding


def _fragments(shares: list[float]) -> dict[int, FragmentData]:
    return {i: FragmentData(volume=share, price=0.0) for i, share in enumerate(shares)}


def test_volumes_are_capacity_shares_when_all_above_threshold():
    volumes = _bidding(minimal_size=10)._fragment_volumes(_fragments([0.5, 0.5]), capacity=100)
    assert volumes == {0: 50.0, 1: 50.0}


def test_sub_threshold_fragment_is_dropped_and_its_volume_redistributed():
    # fragment 1 -> 5 MW < 10, dropped; full capacity redistributed onto fragment 0
    volumes = _bidding(minimal_size=10)._fragment_volumes(_fragments([0.95, 0.05]), capacity=100)
    assert volumes == {0: 100.0}


def test_all_below_threshold_falls_back_to_median_fragment():
    # 3 fragments, all sub-threshold -> whole capacity on the median fragment (index 2)
    volumes = _bidding(minimal_size=10)._fragment_volumes(_fragments([0.3, 0.3, 0.4]), capacity=10)
    assert volumes == {2: 10.0}
