"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from atlas.math.abstract_timeseries import AbstractTimeseries
    from atlas.math.timeseries import Timeseries


@runtime_checkable
class RenewableDispatchInput(Protocol):
    """
    Structural contract for renewable (wind / solar) dispatch.

    Wind and Solar do not share a common equipment base class, so the contract is
    defined as a :class:`typing.Protocol`. Any equipment exposing these attributes
    satisfies the protocol without explicit inheritance — wind/solar PO and DAO
    input objects qualify naturally.

    :param name: Equipment identifier, used as the prefix for solver-variable names.
    :param maximum_curtailment_ratio: Per-timestep ratio of forecast production that may be
        curtailed. ``min_power = (1 - curtailment) × forecast``.
    :param _cached_forecast: Pre-fetched maximum-power forecast over the optimisation window.
        The step is expected to populate this (via the equipment's ``prefetch_forecasts``)
        before any dispatch method is called.
    """

    name: str
    maximum_curtailment_ratio: AbstractTimeseries
    _cached_forecast: Timeseries | None
