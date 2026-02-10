from unittest.mock import patch

import pytest

from atlas import MarketArea
from atlas.enum import BusinessModelName
from atlas.models.market.order import Order
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.workflow.change_set.change_set import AddObject, UpdateObject, DeleteObject
from atlas.workflow.current_input_state import CurrentInputState
from atlas.workflow.handler.cis_handler import CISHandler


@pytest.fixture
def cis():
    dataset = AtlasDataset()
    return CurrentInputState(dataset)


class TestCISHandler:
    def test_apply_multiple_add_objects_applies_in_order(self, cis):
        # Create several AddObjects with different types
        # Here we just use Order for simplicity, but in real cases, use different models in MODEL_ORDER_INSTANTIATION
        add1 = AddObject({"name": "order_1"}, model_type=Order)
        add2 = AddObject({"name": "order_2"}, model_type=Order)

        # Shuffle the list to ensure ordering is applied
        changes = [add2, add1]

        CISHandler.apply(changes, cis)

        # Both orders should be present
        assert "order_1" in cis.data.order
        assert "order_2" in cis.data.order

        # Ensure object identities preserved
        assert cis.data.order.get("order_1").name == "order_1"
        assert cis.data.order.get("order_2").name == "order_2"

    def test_apply_with_update_objects_updates_correctly(self, cis):
        # Add initial object
        initial = Order(name="order_1", price=10.0)
        cis.data.order.add(initial)

        update = UpdateObject({"name": "order_1", "price": 42.0}, model_type=Order)

        CISHandler.apply([update], cis)

        # Check that the price was updated
        assert cis.data.order.get("order_1").price == 42.0

        # Object identity preserved
        assert cis.data.order.get("order_1") is initial

    def test_apply_respects_ordering_with_multiple_types(self, cis, monkeypatch):
        add1 = AddObject({"name": "order_1", "market_area": "ma1"}, model_type=Order)
        add2 = AddObject({"name": "ma1"}, model_type=MarketArea)

        # Patch MODEL_ORDER_INSTANTIATION
        with (
            patch("atlas.config.MODEL_ORDER_INSTANTIATION", [BusinessModelName.MARKET_AREA, BusinessModelName.ORDER]),
            patch(
                "atlas.config.INVERSE_MODEL_MAPPING_NAME",
                {Order: BusinessModelName.ORDER, MarketArea: BusinessModelName.MARKET_AREA},
            ),
        ):
            CISHandler.apply([add1, add2], cis)

        assert "order_1" in cis.data.order
        assert "ma1" == cis.data.order.get("order_1").market_area.name
        assert "ma1" in cis.data.market_area
        assert cis.data.market_area.get("ma1") is cis.data.order.get("order_1").market_area

    def test_apply_with_add_update_delete_mixed(self, cis):
        # Prepare initial object
        order_initial = Order(name="order_1", price=10.0)
        cis.data.order.add(order_initial)

        add = AddObject({"name": "order_2", "price": 5.0}, model_type=Order)
        update = UpdateObject({"name": "order_1", "price": 42.0}, model_type=Order)
        delete = DeleteObject("order_2", model_type=Order)

        with (
            patch("atlas.config.MODEL_ORDER_INSTANTIATION", [BusinessModelName.ORDER]),
            patch("atlas.config.INVERSE_MODEL_MAPPING_NAME", {Order: BusinessModelName.ORDER}),
        ):
            CISHandler.apply([add, update, delete], cis)

        # order_1 should be updated
        assert cis.data.order.get("order_1").price == 42.0
        # order_2 should have been added then removed
        assert "order_2" not in cis.data.order

    def test_apply_with_delete_before_add_is_error(self, cis):
        # Prepare initial object
        order_initial = Order(name="order_1", price=10.0)
        cis.data.order.add(order_initial)

        add = AddObject({"name": "order_2", "price": 5.0}, model_type=Order)
        delete = DeleteObject("order_2", model_type=Order)

        with (
            patch("atlas.config.MODEL_ORDER_INSTANTIATION", [BusinessModelName.ORDER]),
            patch("atlas.config.INVERSE_MODEL_MAPPING_NAME", {Order: BusinessModelName.ORDER}),
        ):
            with pytest.raises(ValueError):
                CISHandler.apply([delete, add], cis)
