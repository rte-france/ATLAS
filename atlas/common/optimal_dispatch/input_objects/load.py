"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from atlas.math.timeseries import Timeseries


@runtime_checkable
class LoadDispatchInput(Protocol):
    """
    Structural contract for load dispatch.

    Load is a consumption-only unit — no reserves, no minimum power floor. The dispatch
    needs only the equipment name and the cached maximum-power forecast (which is the
    *negative-valued* lower bound on the load's power-level variable).

    :param name: Equipment identifier.
    :param _cached_forecast: Pre-fetched maximum-power forecast (signed: negative for consumption).
    """

    name: str
    _cached_forecast: Timeseries | None
