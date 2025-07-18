"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from datetime import datetime

from atlas.abstract_class.abstract_parameters import AbstractParameters


def test_valid_dates():
    params = AbstractParameters(
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31),
        execution_date=datetime(2024, 6, 1),
    )
    assert params.start_date < params.end_date


def test_invalid_end_before_start():
    try:
        AbstractParameters(
            start_date=datetime(2024, 12, 31), end_date=datetime(2024, 1, 1), execution_date=datetime(2024, 12, 31)
        )
        assert False, "Expected ValueError for end_date before start_date"
    except ValueError as e:
        assert "Start date" in str(e)
