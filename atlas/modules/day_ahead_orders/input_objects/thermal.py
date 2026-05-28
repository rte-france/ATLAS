"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import Duration

from atlas.common.optimal_dispatch.input_objects.thermal import ThermalDispatchInput
from atlas.math.abstract_timeseries import AbstractTimeseries


class ThermalDAO(ThermalDispatchInput):
    variable_cost: AbstractTimeseries
    startup_cost: AbstractTimeseries
    additional_hours: Duration
