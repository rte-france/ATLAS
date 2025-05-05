"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Test AbstractParameters
"""

from typing import Any

import pytest
import datetime

from atlas.abstract_class.abstract_parameters import AbstractParameters


class ParametersTest(AbstractParameters):
    valid_result: bool | None = None


@pytest.fixture()
def raw_params() -> dict[str, Any]:
    return {
        "start_date": datetime.datetime(2025, 1, 1),
        "end_date": datetime.datetime(2025, 1, 2),
        "execution_date": datetime.datetime(2025, 1, 1, 12),
        "valid_result": True,
    }


@pytest.fixture()
def parameters(raw_params: dict[str, Any]) -> ParametersTest:
    return ParametersTest(**raw_params)


def test_parameters_raise_error_if_start_date_inferior_to_end_date():
    params = {
        "start_date": datetime.datetime(2025, 1, 2),
        "end_date": datetime.datetime(2025, 1, 1),
    }
    with pytest.raises(ValueError, match=".*inferior*"):
        ParametersTest(**params)


def test_parameters_raise_error_if_execution_date_is_inferior_to_start_date():
    params = {
        "start_date": datetime.datetime(2025, 1, 2),
        "end_date": datetime.datetime(2025, 1, 4),
        "execution_date": datetime.datetime(2025, 1, 1),
    }
    with pytest.raises(ValueError, match=".*between*"):
        ParametersTest(**params)


def test_parameters_raise_error_if_execution_date_is_superior_to_date():
    params = {
        "start_date": datetime.datetime(2025, 1, 1),
        "end_date": datetime.datetime(2025, 1, 4),
        "execution_date": datetime.datetime(2025, 1, 5),
    }
    with pytest.raises(ValueError, match=".*between*"):
        ParametersTest(**params)
