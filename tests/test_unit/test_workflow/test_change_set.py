"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pytest

from atlas import MarketArea, Order
from atlas.enums import BusinessModelName
from atlas.models.business_model import BusinessModel
from atlas.workflow.change_set import AddObject, ChangeSet, DeleteObject, UpdateObject


class _ConcreteChangeSet(ChangeSet):
    """Minimal concrete subclass for testing the abstract ChangeSet base."""

    kind = "test"

    def to_dict(self):
        return {"type": self.kind}

    @classmethod
    def _build_from_obj(cls, obj: BusinessModel, model_type):
        return cls(model_type)


class TestChangSetGetModelType:
    def test_accepts_business_model_name(self):
        result = ChangeSet.get_model_type(BusinessModelName.ORDER)
        assert result == BusinessModelName.ORDER

    def test_accepts_model_class(self):
        result = ChangeSet.get_model_type(Order)
        assert result == BusinessModelName.ORDER

    def test_accepts_string(self):
        result = ChangeSet.get_model_type("order")
        assert result == BusinessModelName.ORDER

    def test_invalid_class_raises_type_error(self):
        class NotAModel:
            pass

        with pytest.raises(TypeError):
            ChangeSet.get_model_type(NotAModel)

    def test_invalid_string_raises_value_error(self):
        with pytest.raises(ValueError):
            ChangeSet.get_model_type("not_a_real_model_name_xyz")

    def test_invalid_type_raises_type_error(self):
        with pytest.raises(TypeError):
            ChangeSet.get_model_type(42)  # type: ignore[arg-type]

    def test_non_business_model_subclass_raises_type_error(self):
        with pytest.raises(TypeError):
            ChangeSet.get_model_type(int)  # type: ignore[arg-type]


class TestChangeSetFromObject:
    def test_add_from_object_builds_correct_type(self):
        order = Order(name="o1", price=10.0)
        cs = AddObject.from_object(order)
        assert isinstance(cs, AddObject)
        assert cs.model_type == BusinessModelName.ORDER

    def test_update_from_object_builds_correct_type(self):
        order = Order(name="o1", price=10.0)
        cs = UpdateObject.from_object(order)
        assert isinstance(cs, UpdateObject)
        assert cs.model_type == BusinessModelName.ORDER

    def test_delete_from_object_builds_correct_type(self):
        order = Order(name="o1", price=10.0)
        cs = DeleteObject.from_object(order)
        assert isinstance(cs, DeleteObject)
        assert cs.name == "o1"
        assert cs.model_type == BusinessModelName.ORDER

    def test_from_object_with_market_area(self):
        ma = MarketArea(name="ma1")
        cs = AddObject.from_object(ma)
        assert cs.model_type == BusinessModelName.MARKET_AREA


class TestAddObject:
    def test_construction_with_dict(self):
        cs = AddObject({"name": "o1", "price": 5.0}, model_type=Order)
        assert cs.data == {"name": "o1", "price": 5.0}
        assert cs.model_type == BusinessModelName.ORDER

    def test_construction_with_model_class(self):
        cs = AddObject({"name": "o1"}, model_type=Order)
        assert cs.model_type == BusinessModelName.ORDER

    def test_construction_with_business_model_name(self):
        cs = AddObject({"name": "o1"}, model_type=BusinessModelName.ORDER)
        assert cs.model_type == BusinessModelName.ORDER

    def test_construction_with_string_model_type(self):
        cs = AddObject({"name": "o1"}, model_type="order")
        assert cs.model_type == BusinessModelName.ORDER

    def test_missing_name_raises_key_error(self):
        with pytest.raises(KeyError):
            AddObject({"price": 5.0}, model_type=Order)

    def test_to_dict(self):
        cs = AddObject({"name": "o1", "price": 5.0}, model_type=Order)
        result = cs.to_dict()
        assert result == {"type": "add", "data": {"name": "o1", "price": 5.0}}

    def test_kind(self):
        assert AddObject.kind == "add"

    def test_from_object_copies_attributes(self):
        order = Order(name="o1", price=99.0)
        cs = AddObject.from_object(order)
        assert cs.data["name"] == "o1"

    def test_from_object_data_is_independent_copy(self):
        order = Order(name="o1", price=10.0)
        cs = AddObject.from_object(order)
        cs.data["price"] = 999.0
        # The original object should be unaffected
        assert order.price == 10.0


class TestUpdateObject:
    def test_construction(self):
        cs = UpdateObject({"name": "o1", "price": 42.0}, model_type=Order)
        assert cs.data == {"name": "o1", "price": 42.0}
        assert cs.model_type == BusinessModelName.ORDER

    def test_missing_name_raises_key_error(self):
        with pytest.raises(KeyError):
            UpdateObject({"price": 5.0}, model_type=Order)

    def test_to_dict(self):
        cs = UpdateObject({"name": "o1", "price": 42.0}, model_type=Order)
        result = cs.to_dict()
        assert result == {"type": "update", "data": {"name": "o1", "price": 42.0}}

    def test_kind(self):
        assert UpdateObject.kind == "update"

    def test_from_object(self):
        order = Order(name="o1", price=7.0)
        cs = UpdateObject.from_object(order)
        assert isinstance(cs, UpdateObject)
        assert cs.data["name"] == "o1"
        assert cs.model_type == BusinessModelName.ORDER

    def test_accepts_business_model_name(self):
        cs = UpdateObject({"name": "o1"}, model_type=BusinessModelName.ORDER)
        assert cs.model_type == BusinessModelName.ORDER

    def test_accepts_string_model_type(self):
        cs = UpdateObject({"name": "o1"}, model_type="order")
        assert cs.model_type == BusinessModelName.ORDER


class TestDeleteObject:
    def test_construction_with_name_and_class(self):
        cs = DeleteObject("o1", model_type=Order)
        assert cs.name == "o1"
        assert cs.model_type == BusinessModelName.ORDER

    def test_construction_with_business_model_name(self):
        cs = DeleteObject("o1", model_type=BusinessModelName.ORDER)
        assert cs.model_type == BusinessModelName.ORDER

    def test_construction_with_string_model_type(self):
        cs = DeleteObject("o1", model_type="order")
        assert cs.model_type == BusinessModelName.ORDER

    def test_to_dict(self):
        cs = DeleteObject("o1", model_type=Order)
        result = cs.to_dict()
        assert result == {"type": "delete", "name": "o1"}

    def test_kind(self):
        assert DeleteObject.kind == "delete"

    def test_from_object(self):
        order = Order(name="o1", price=5.0)
        cs = DeleteObject.from_object(order)
        assert cs.name == "o1"
        assert cs.model_type == BusinessModelName.ORDER
