"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from collections.abc import Iterator

from atlas.modules.market_clearing.data_classes import PriceGroup


def count_saturated(saturated_critical_branch: dict[tuple[str, int], float], time_index: int, tolerance: float) -> int:
    """Count critical branches saturated (shadow price below tolerance) at a given time step."""
    return len(
        [
            1
            for (_, cb_time_index), value in saturated_critical_branch.items()
            if abs(value) <= tolerance and cb_time_index == time_index
        ]
    )


def iter_group_pairs(price_groups: list[PriceGroup]) -> Iterator[tuple[PriceGroup, PriceGroup]]:
    """Iterate over every unordered pair of distinct price groups."""
    for i in range(len(price_groups) - 1):
        for j in range(i + 1, len(price_groups)):
            yield price_groups[i], price_groups[j]
