"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from collections import defaultdict
from collections.abc import Iterator

import pendulum

from atlas.modules.market_clearing.data_classes import PriceGroup

type GroupPair = tuple[int, int]


def count_saturated(
    saturated_critical_branch: dict[tuple[str, pendulum.DateTime], float],
    time: pendulum.DateTime,
    tolerance: float,
) -> int:
    """Count critical branches saturated (shadow price below tolerance) at a given time step."""
    return len(
        [1 for (_, cb_time), value in saturated_critical_branch.items() if abs(value) <= tolerance and cb_time == time]
    )


def iter_group_pairs(price_groups: list[PriceGroup]) -> Iterator[tuple[PriceGroup, PriceGroup]]:
    """Iterate over every unordered pair of distinct price groups."""
    for i in range(len(price_groups) - 1):
        for j in range(i + 1, len(price_groups)):
            yield price_groups[i], price_groups[j]


def times_by_group(price_groups: dict[pendulum.DateTime, list[PriceGroup]]) -> dict[int, list[pendulum.DateTime]]:
    """Index the time steps at which each price group id exists.

    Price groups are rebuilt at every time step, so a group id only exists at some of them: these
    are the times of the temporal variables declared for the group.

    **Example**

        price_groups = {t0: [PriceGroup(id=0, time=t0)], t1: [PriceGroup(id=0, time=t1), PriceGroup(id=1, time=t1)]}
        times_by_group(price_groups)  # {0: [t0, t1], 1: [t1]}

    :param price_groups: Price groups of each time step
    :type price_groups: dict[pendulum.DateTime, list[PriceGroup]]
    :return: Sorted time steps of each group id
    :rtype: dict[int, list[pendulum.DateTime]]
    """
    group_times: defaultdict[int, list[pendulum.DateTime]] = defaultdict(list)
    for time in sorted(price_groups):
        for price_group in price_groups[time]:
            group_times[price_group.id].append(time)
    return dict(group_times)


def times_by_group_pair(
    price_groups: dict[pendulum.DateTime, list[PriceGroup]],
) -> dict[GroupPair, list[pendulum.DateTime]]:
    """Index the time steps at which each pair of price groups exists, as given by :func:`iter_group_pairs`.

    :param price_groups: Price groups of each time step
    :type price_groups: dict[pendulum.DateTime, list[PriceGroup]]
    :return: Sorted time steps of each ``(group id, other group id)`` pair
    :rtype: dict[tuple[int, int], list[pendulum.DateTime]]
    """
    pair_times: defaultdict[GroupPair, list[pendulum.DateTime]] = defaultdict(list)
    for time in sorted(price_groups):
        for price_group, other_price_group in iter_group_pairs(price_groups[time]):
            pair_times[price_group.id, other_price_group.id].append(time)
    return dict(pair_times)
