"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pytest

from atlas.solver.solver_helper import SolverHelper
from tests.test_unit.test_data_helper import TestDataHelper


@pytest.fixture
def lp_ortools():
    return TestDataHelper.get_test_file("storage_es_battery.lp")


@pytest.fixture
def lp_legacy():
    return TestDataHelper.get_test_file("es_battery_lp.lp")


@pytest.fixture
def lp_legacy_match_file():
    return TestDataHelper.get_test_file("es_battery_lp.lp_correspondance.csv")


@pytest.fixture
def new_lp():
    return TestDataHelper.get_test_file("es_battery_lp_new.lp")


def test_read_lp_ortools(lp_ortools):
    result = SolverHelper.read_lp_ortools(lp_ortools)
    assert len(result["objectives"]) == 1
    assert len(result["constraints"]) == 3
    assert len(result["variables"]) == 4
    assert len(result["binaries"]) == 1


def test_read_lp_legacy(lp_legacy):
    result = SolverHelper.read_lp_legacy(lp_legacy)
    assert len(result["objectives"]) == 2
    assert len(result["constraints"]) == 3
    assert len(result["variables"]) == 1  # Binary variables are now included in variables
    assert len(result["binaries"]) == 1


def test_rebuild_lp(lp_legacy, lp_legacy_match_file, new_lp):
    # rebuild lp with matching file, restoring complete variable names, instead of shortened ones.
    SolverHelper.rebuild_lp_with_real_names(lp_legacy, lp_legacy_match_file, new_lp)
    # Check that both lp are the same
    result_original = SolverHelper.read_lp_legacy(lp_legacy)
    result_new = SolverHelper.read_lp_legacy(new_lp)

    assert len(result_original["objectives"]) == len(result_new["objectives"])
    assert len(result_original["constraints"]) == len(result_new["constraints"])
    assert len(result_original["variables"]) == len(result_new["variables"])
    assert len(result_original["binaries"]) == len(result_new["binaries"])
