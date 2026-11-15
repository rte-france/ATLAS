"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
import pytest
from pydantic import ValidationError

from atlas.common.optimal_dispatch.input_objects.thermal import ThermalDispatchInput


@pytest.fixture
def valid_thermal_dict(node, portfolio, timeseries):
    return {
        "name": "thermal_unit",
        "node": node,
        "portfolio": portfolio,
        "maximum_power": timeseries,
        "minimum_power": timeseries,
        "minimum_time_on": pendulum.duration(hours=4),
        "minimum_time_off": pendulum.duration(hours=2),
        "minimum_stable_power_duration": pendulum.duration(hours=1),
    }


class TestThermalDispatchInput:
    def test_instantiation_with_required_fields(self, valid_thermal_dict):
        obj = ThermalDispatchInput(**valid_thermal_dict)
        assert obj.name == "thermal_unit"

    @pytest.mark.parametrize(
        "field",
        [
            "maximum_power",
            "minimum_power",
            "minimum_time_on",
            "minimum_time_off",
            "minimum_stable_power_duration",
        ],
    )
    def test_missing_required_field_raises(self, valid_thermal_dict, field):
        del valid_thermal_dict[field]
        with pytest.raises(ValidationError):
            ThermalDispatchInput(**valid_thermal_dict)

    def test_duration_coercion_from_iso8601_string(self, valid_thermal_dict):
        valid_thermal_dict["minimum_time_on"] = "PT4H"
        obj = ThermalDispatchInput(**valid_thermal_dict)
        assert obj.minimum_time_on.total_hours() == 4.0
