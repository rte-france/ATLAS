"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pytest

from atlas import Equipment
from atlas.workflow.change_set import AddObject, UpdateObject, DeleteObject


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


# ======================
# AddObject tests
# ======================


class TestAddObject:
    def test_add_object_success(self, empty_bmo):
        eq = Equipment(name="equipment_1", coe2_emission_factor=1.5)

        change = AddObject.from_obj(eq)
        change.apply(empty_bmo)

        assert "equipment_1" in empty_bmo["equipment"]
        assert empty_bmo["equipment"]["equipment_1"].coe2_emission_factor == 1.5

    def test_add_object_already_exists(self, one_equipment):
        eq = Equipment(name="equipment_1", coe2_emission_factor=2.0)

        change = AddObject.from_obj(eq)

        with pytest.raises(KeyError, match="Object already exists"):
            change.apply(one_equipment)

    def test_add_object_from_dict(self):
        equipment_1 = Equipment(name="equipment_1")

        data = {
            "equipment": {
                "equipment_1": equipment_1,
            },
        }

        equipment_2 = Equipment(name="equipment_2", coe2_emission_factor=1.5)
        AddObject.from_obj(equipment_2).apply(data)

        equipment_3 = {
            "name": "equipment_3",
            "coe2_emission_factor": 2.2,
        }
        AddObject("equipment", equipment_3).apply(data)

        assert "equipment_2" in data["equipment"]
        assert "equipment_3" in data["equipment"]

    def test_add_object_rollback(self, empty_bmo):
        eq = Equipment(name="equipment_1", coe2_emission_factor=1.5)

        change = AddObject.from_obj(eq)
        change.apply(empty_bmo)

        assert "equipment_1" in empty_bmo["equipment"]

        change.rollback(empty_bmo)

        assert "equipment_1" not in empty_bmo["equipment"]


# ======================
# UpdateObject tests
# ======================


class TestUpdateObject:
    def test_update_object_attribute(self, one_equipment):
        eq = Equipment(name="equipment_1", coe2_emission_factor=2.5)

        change = UpdateObject.from_obj(eq)
        change.apply(one_equipment)

        assert one_equipment["equipment"]["equipment_1"].coe2_emission_factor == 2.5

    def test_update_object_rename(self, one_equipment):
        change = UpdateObject(
            "equipment",
            "equipment_1",
            {"name": "equipment_renamed", "coe2_emission_factor": 1.5},
        )
        change.apply(one_equipment)

        assert "equipment_1" not in one_equipment["equipment"]
        assert "equipment_renamed" in one_equipment["equipment"]

    def test_update_object_rollback_attribute(self, one_equipment):
        original = one_equipment["equipment"]["equipment_1"].coe2_emission_factor

        eq = Equipment(name="equipment_1", coe2_emission_factor=9.9)
        change = UpdateObject.from_obj(eq)

        change.apply(one_equipment)
        assert one_equipment["equipment"]["equipment_1"].coe2_emission_factor == 9.9

        change.rollback(one_equipment)
        assert one_equipment["equipment"]["equipment_1"].coe2_emission_factor == original

    def test_update_object_rollback_rename(self, one_equipment):
        change = UpdateObject(
            "equipment",
            "equipment_1",
            {"name": "equipment_renamed", "coe2_emission_factor": 1.0},
        )
        change.apply(one_equipment)

        assert "equipment_renamed" in one_equipment["equipment"]
        assert "equipment_1" not in one_equipment["equipment"]

        change.rollback(one_equipment)

        assert "equipment_1" in one_equipment["equipment"]
        assert "equipment_renamed" not in one_equipment["equipment"]


# ======================
# DeleteObject tests
# ======================


class TestDeleteObject:
    def test_delete_object_success(self, one_equipment):
        eq = one_equipment["equipment"]["equipment_1"]

        change = DeleteObject.from_obj(eq)
        change.apply(one_equipment)

        assert "equipment_1" not in one_equipment["equipment"]

    def test_delete_object_not_exists(self, empty_bmo):
        change = DeleteObject("equipment", "not present")

        with pytest.raises(KeyError):
            change.apply(empty_bmo)

    def test_delete_object_from_obj_not_exists(self):
        equipment_1 = Equipment(name="equipment_1")

        data = {
            "equipment": {
                "equipment_1": equipment_1,
            },
        }

        equipment_2_module = Equipment(name="equipment_2", coe2_emission_factor=1.5)

        with pytest.raises(KeyError, match="Object doesn't exist"):
            DeleteObject.from_obj(equipment_2_module).apply(data)

    def test_delete_object_rollback(self, one_equipment):
        eq = one_equipment["equipment"]["equipment_1"]

        change = DeleteObject.from_obj(eq)
        change.apply(one_equipment)

        assert "equipment_1" not in one_equipment["equipment"]

        change.rollback(one_equipment)

        assert "equipment_1" in one_equipment["equipment"]
