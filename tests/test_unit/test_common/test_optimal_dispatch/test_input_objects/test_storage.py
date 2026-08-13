"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
import pytest
from pydantic import ValidationError

from atlas.common.optimal_dispatch.input_objects.storage import StorageDispatchInput
from atlas.enums import StorageType


@pytest.fixture
def valid_storage_dict(node, portfolio, timeseries):
    return {
        "name": "battery_unit",
        "node": node,
        "portfolio": portfolio,
        "storage_type": StorageType.BATTERY,
        "maximum_energy": timeseries,
        "minimum_power": timeseries,
        "maximum_power": timeseries,
        "minimum_state_of_charge": timeseries,
        "charge_efficiency": 0.9,
        "discharge_efficiency": 0.9,
        "storage_initial_level": 0.5,
        "additional_hours": pendulum.duration(hours=2),
    }


class TestStorageDispatchInput:
    def test_instantiation_with_required_fields(self, valid_storage_dict):
        obj = StorageDispatchInput(**valid_storage_dict)
        assert obj.name == "battery_unit"
        assert obj.charge_efficiency == 0.9

    @pytest.mark.parametrize(
        "field",
        [
            "maximum_energy",
            "minimum_power",
            "maximum_power",
            "minimum_state_of_charge",
            "charge_efficiency",
            "discharge_efficiency",
            "storage_initial_level",
            "additional_hours",
        ],
    )
    def test_missing_required_field_raises(self, valid_storage_dict, field):
        del valid_storage_dict[field]
        with pytest.raises(ValidationError):
            StorageDispatchInput(**valid_storage_dict)

    def test_additional_hours_coercion_from_iso8601_string(self, valid_storage_dict):
        valid_storage_dict["additional_hours"] = "PT2H"
        obj = StorageDispatchInput(**valid_storage_dict)
        assert obj.additional_hours.total_hours() == 2.0

    @pytest.mark.parametrize("field", ["charge_efficiency", "discharge_efficiency"])
    @pytest.mark.parametrize("value", [0.0, -0.1])
    def test_non_positive_efficiency_rejected(self, valid_storage_dict, field, value):
        """The dispatch formulation divides by both efficiencies — zero is not a valid input."""
        valid_storage_dict[field] = value
        with pytest.raises(ValidationError):
            StorageDispatchInput(**valid_storage_dict)
