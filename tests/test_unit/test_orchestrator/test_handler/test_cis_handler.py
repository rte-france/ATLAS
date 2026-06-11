from unittest.mock import patch

import pytest

from atlas import MarketArea
from atlas.core.io_utils.atlas_dataset import AtlasDataset
from atlas.core.orchestrator.change_set import AddObject, DeleteObject, UpdateObject
from atlas.core.orchestrator.current_input_state import CurrentInputState
from atlas.core.orchestrator.handler.cis_handler import CISHandler
from atlas.custom_errors import ChangeSetApplicationError
from atlas.enums import BusinessModelName
from atlas.objects.market.order import Order
from atlas.objects.network_operator.control_block import ControlBlock


@pytest.fixture
def cis():
    dataset = AtlasDataset()
    cis_obj = CurrentInputState(dataset)
    # Pre-populate with a MarketArea so Orders can reference it
    cb = ControlBlock(name="cb1")
    ma = MarketArea(name="ma1", control_block=cb)
    cis_obj.data.market_area.add(ma)
    return cis_obj


class TestCISHandler:
    def test_apply_multiple_add_objects_applies_in_order(self, cis):
        # Create several AddObjects with different types
        # Here we just use Order for simplicity, but in real cases, use different models in MODEL_ORDER_INSTANTIATION
        add1 = AddObject({"name": "order_1", "market_area": "ma1"}, model_type=Order)
        add2 = AddObject({"name": "order_2", "market_area": "ma1"}, model_type=Order)

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
        ma = cis.data.market_area.get("ma1")
        initial = Order(name="order_1", price=10.0, market_area=ma)
        cis.data.order.add(initial)

        update = UpdateObject({"name": "order_1", "price": 42.0}, model_type=Order)

        CISHandler.apply([update], cis)

        # Check that the price was updated
        assert cis.data.order.get("order_1").price == 42.0

        # Object identity preserved
        assert cis.data.order.get("order_1") is initial

    def test_apply_respects_ordering_with_multiple_types(self, cis, monkeypatch):
        # This test checks that MarketArea is created before Order when they're in the right order
        # Clear the pre-populated ma1 from fixture for this test
        cis.data.market_area.remove("ma1")
        # Also need to add control_block first for MarketArea
        cb = ControlBlock(name="cb1")
        cis.data.control_block.add(cb)
        add1 = AddObject({"name": "order_1", "market_area": "ma1"}, model_type=Order)
        add2 = AddObject({"name": "ma1", "control_block": "cb1"}, model_type=MarketArea)

        # Patch MODEL_ORDER_INSTANTIATION
        with (
            patch("atlas.config.MODEL_ORDER_INSTANTIATION", [BusinessModelName.MARKET_AREA, BusinessModelName.ORDER]),
            patch(
                "atlas.config.INVERSE_MODEL_MAPPING_NAME",
                {
                    Order: BusinessModelName.ORDER,
                    MarketArea: BusinessModelName.MARKET_AREA,
                    ControlBlock: BusinessModelName.CONTROL_BLOCK,
                },
            ),
        ):
            CISHandler.apply([add1, add2], cis)

        assert "order_1" in cis.data.order
        assert "ma1" == cis.data.order.get("order_1").market_area.name
        assert "ma1" in cis.data.market_area
        assert cis.data.market_area.get("ma1") is cis.data.order.get("order_1").market_area

    def test_apply_with_add_update_delete_mixed(self, cis):
        # Prepare initial object
        ma = cis.data.market_area.get("ma1")
        order_initial = Order(name="order_1", price=10.0, market_area=ma)
        cis.data.order.add(order_initial)

        add = AddObject({"name": "order_2", "price": 5.0, "market_area": "ma1"}, model_type=Order)
        update = UpdateObject({"name": "order_1", "price": 42.0}, model_type=Order)
        delete = DeleteObject("order_2", model_type=Order)

        with (
            patch("atlas.config.MODEL_ORDER_INSTANTIATION", [BusinessModelName.ORDER]),
            patch(
                "atlas.config.INVERSE_MODEL_MAPPING_NAME",
                {Order: BusinessModelName.ORDER, MarketArea: BusinessModelName.MARKET_AREA},
            ),
        ):
            CISHandler.apply([add, update, delete], cis)

        # order_1 should be updated
        assert cis.data.order.get("order_1").price == 42.0
        # order_2 should have been added then removed
        assert "order_2" not in cis.data.order

    def test_apply_with_delete_before_add_is_error(self, cis):
        # Prepare initial object
        ma = cis.data.market_area.get("ma1")
        order_initial = Order(name="order_1", price=10.0, market_area=ma)
        cis.data.order.add(order_initial)

        add = AddObject({"name": "order_2", "price": 5.0, "market_area": "ma1"}, model_type=Order)
        delete = DeleteObject("order_2", model_type=Order)

        with (
            patch("atlas.config.MODEL_ORDER_INSTANTIATION", [BusinessModelName.ORDER]),
            patch(
                "atlas.config.INVERSE_MODEL_MAPPING_NAME",
                {Order: BusinessModelName.ORDER, MarketArea: BusinessModelName.MARKET_AREA},
            ),
        ):
            with pytest.raises(ChangeSetApplicationError):
                CISHandler.apply([delete, add], cis)

    def test_rollback_on_error_restores_state(self, cis):
        """Test that failed change set application rolls back all changes"""
        # Add initial objects
        ma = cis.data.market_area.get("ma1")
        order1 = Order(name="order_1", price=10.0, market_area=ma)
        order2 = Order(name="order_2", price=20.0, market_area=ma)
        cis.data.order.add(order1)
        cis.data.order.add(order2)

        # Create change sets: valid add, then invalid update
        add = AddObject({"name": "order_3", "price": 30.0, "market_area": "ma1"}, model_type=Order)
        invalid_update = UpdateObject({"name": "order_999", "price": 99.0}, model_type=Order)

        with (
            patch("atlas.config.MODEL_ORDER_INSTANTIATION", [BusinessModelName.ORDER]),
            patch(
                "atlas.config.INVERSE_MODEL_MAPPING_NAME",
                {Order: BusinessModelName.ORDER, MarketArea: BusinessModelName.MARKET_AREA},
            ),
        ):
            with pytest.raises(ChangeSetApplicationError):
                CISHandler.apply([add, invalid_update], cis, rollback_on_error=True)

        # Verify order_3 was NOT added (rollback occurred)
        assert "order_3" not in cis.data.order
        # Verify original objects still exist
        assert "order_1" in cis.data.order
        assert "order_2" in cis.data.order

    def test_no_rollback_keeps_partial_changes(self, cis):
        """Test that with rollback_on_error=False, partial changes are kept"""
        # Add initial object
        ma = cis.data.market_area.get("ma1")
        order1 = Order(name="order_1", price=10.0, market_area=ma)
        cis.data.order.add(order1)

        # Create change sets: valid add, then invalid update
        add = AddObject({"name": "order_2", "price": 20.0, "market_area": "ma1"}, model_type=Order)
        invalid_update = UpdateObject({"name": "order_999", "price": 99.0}, model_type=Order)

        with (
            patch("atlas.config.MODEL_ORDER_INSTANTIATION", [BusinessModelName.ORDER]),
            patch(
                "atlas.config.INVERSE_MODEL_MAPPING_NAME",
                {Order: BusinessModelName.ORDER, MarketArea: BusinessModelName.MARKET_AREA},
            ),
        ):
            with pytest.raises(ChangeSetApplicationError):
                CISHandler.apply([add, invalid_update], cis, rollback_on_error=False)

        # Verify order_2 WAS added (no rollback)
        assert "order_2" in cis.data.order
        assert cis.data.order.get("order_2").price == 20.0
