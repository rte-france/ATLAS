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
    objectives, constraints, variables, binaries = SolverHelper.read_lp_ortools(lp_ortools)
    assert len(objectives) == 1
    assert len(constraints) == 3
    assert len(variables) == 4
    assert len(binaries) == 1


def test_read_lp_legacy(lp_legacy):
    objectives, constraints, variables, binaries = SolverHelper.read_lp_legacy(lp_legacy)
    assert len(objectives) == 2
    assert len(constraints) == 3
    assert len(variables) == 0
    assert len(binaries) == 1


def test_rebuild_lp(lp_legacy, lp_legacy_match_file, new_lp):
    # rebuild lp with matching file, restoring complete variable names, instead of shortened ones.
    SolverHelper.rebuild_lp_with_real_names(lp_legacy, lp_legacy_match_file, new_lp)
    # Check that both lp are the same
    objectives_original, constraints_original, variables_original, binaries_original = SolverHelper.read_lp_legacy(
        lp_legacy
    )
    objectives_new, constraints_new, variables_new, binaries_new = SolverHelper.read_lp_legacy(new_lp)

    assert len(objectives_original) == len(objectives_new)
    assert len(constraints_original) == len(constraints_new)
    assert len(variables_original) == len(variables_new)
    assert len(binaries_original) == len(binaries_new)
