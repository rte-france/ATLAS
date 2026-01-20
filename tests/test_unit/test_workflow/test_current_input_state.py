"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pytest
from atlas import Equipment
from atlas.workflow.change_set import AddObject, UpdateObject, DeleteObject
from atlas.workflow.current_input_state import CurrentInputState


# ======================
# Fixtures
# ======================


@pytest.fixture
def empty_bmo():
    return {"equipment": {}}


@pytest.fixture
def one_equipment():
    eq = Equipment(name="equipment_1", coe2_emission_factor=1.0)
    return {"equipment": {"equipment_1": eq}}


# -------------------------
# Test single apply
# -------------------------
def test_apply_single_add(empty_bmo):
    state = CurrentInputState(empty_bmo)
    eq = Equipment(name="equipment_1", coe2_emission_factor=1.5)
    change = AddObject.from_obj(eq)

    state.apply(change)

    assert "equipment_1" in state.data["equipment"]
    assert state.data["equipment"]["equipment_1"].coe2_emission_factor == 1.5


# -------------------------
# Test apply_all atomic success
# -------------------------
def test_apply_all_success(empty_bmo):
    state = CurrentInputState(empty_bmo)

    changes = [
        AddObject("equipment", {"name": "eq1", "coe2_emission_factor": 1.0}),
        AddObject("equipment", {"name": "eq2", "coe2_emission_factor": 2.0}),
    ]

    state.apply_all(changes)

    assert "eq1" in state.data["equipment"]
    assert "eq2" in state.data["equipment"]


# -------------------------
# Test apply_all with rollback on failure
# -------------------------
def test_apply_all_rollback_on_failure(empty_bmo):
    state = CurrentInputState(empty_bmo)

    changes = [
        AddObject("equipment", {"name": "eq1", "coe2_emission_factor": 1.0}),
        AddObject("equipment", {"name": "eq1", "coe2_emission_factor": 2.0}),  # duplicate
    ]

    with pytest.raises(ValueError, match="Error when applying change set"):
        state.apply_all(changes)

    # Ensure rollback: eq1 should NOT be in the state
    assert state.data["equipment"] == {}


# -------------------------
# Test apply_all with UpdateObject
# -------------------------
def test_apply_all_update(one_equipment):
    state = CurrentInputState(one_equipment)

    changes = [
        UpdateObject("equipment", "equipment_1", {"coe2_emission_factor": 3.0}),
    ]

    state.apply_all(changes)

    assert state.data["equipment"]["equipment_1"].coe2_emission_factor == 3.0


# -------------------------
# Test apply_all with DeleteObject and rollback
# -------------------------
def test_apply_all_delete_rollback(one_equipment):
    state = CurrentInputState(one_equipment)

    changes = [
        DeleteObject("equipment", "equipment_1"),
        DeleteObject("equipment", "nonexistent"),  # this will fail
    ]

    with pytest.raises(ValueError, match="Error when applying change set"):
        state.apply_all(changes)

    # rollback: original equipment should still be present
    assert "equipment_1" in state.data["equipment"]
