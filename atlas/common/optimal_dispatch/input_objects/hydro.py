"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.objects.equipment.hydro import Hydro
from atlas.validators import DurationField


class HydroDispatchInput(Hydro):
    """
    Physical contract for hydro dispatch — fields read by :class:`HydroDispatch`.

    Marginal-value and storage-marginal-value handling are objective-side concerns kept
    inside the calling module (``portfolio_optimisation.steps.HydroStep``).
    """

    maximum_energy: AbstractTimeseries
    minimum_energy: AbstractTimeseries
    maximum_power: AbstractTimeseries
    minimum_power: AbstractTimeseries
    initial_level: AbstractTimeseries
    additional_hours: DurationField
