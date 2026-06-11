import pytest
from pydantic_core._pydantic_core import ValidationError

from atlas import MarketArea
from atlas.core.io_utils.atlas_dataset import AtlasDataset
from atlas.core.orchestrator.change_set import AddObject, DeleteObject, UpdateObject
from atlas.core.orchestrator.current_input_state import CurrentInputState
from atlas.core.orchestrator.handler.change_set_handler import ChangeSetHandler
from atlas.objects.market.order import Order
from atlas.objects.network_operator.control_block import ControlBlock


# ------------------------
# Fixtures
# ------------------------
@pytest.fixture
def dataset():
    """Return a fresh AtlasDataset for each test."""
    return AtlasDataset()


@pytest.fixture
def cis(dataset):
    """Return a CurrentInputState initialized with the dataset."""
    return CurrentInputState(dataset)


@pytest.fixture
def cis_with_market_area(cis):
    """CIS with a MarketArea already added."""
    cb = ControlBlock(name="cb1")
    ma = MarketArea(name="ma1", control_block=cb)
    cis.data.market_area.add(ma)
    return cis


@pytest.fixture
def cis_with_order(cis_with_market_area):
    """CIS with both MarketArea and Order."""
    ma = cis_with_market_area.data.market_area.get("ma1")
    order = Order(name="order_1", price=10.0, market_area=ma)
    cis_with_market_area.data.order.add(order)
    return cis_with_market_area


class TestChangeSetSharedBehavior:
    def test_resolve_reference_str(self, cis_with_market_area):
        ma = cis_with_market_area.data.market_area.get("ma1")
        # Create order with the actual ma object initially
        order = Order.model_validate({"name": "o1", "market_area": ma})
        # Test that string reference gets resolved
        data = {"market_area": "ma1"}

        ChangeSetHandler._resolve_reference(data, cis_with_market_area, obj=order)

        assert data["market_area"] is ma

    def test_resolve_reference_obj(self, cis_with_market_area):
        ma = cis_with_market_area.data.market_area.get("ma1")
        cb = ControlBlock(name="cb1")
        order = Order.model_validate({"name": "o1", "market_area": ma})
        data = {"market_area": MarketArea(name="ma1", control_block=cb)}

        ChangeSetHandler._resolve_reference(data, cis_with_market_area, obj=order)

        assert data["market_area"] is ma

    def test_resolve_reference_missing_raises(self, cis_with_market_area):
        ma = cis_with_market_area.data.market_area.get("ma1")
        order = Order.model_validate({"name": "o1", "market_area": ma})
        data = {"market_area": "missing"}

        with pytest.raises(ValueError):
            ChangeSetHandler._resolve_reference(data, cis_with_market_area, obj=order)

    def test_fill_object_valid(self, cis_with_market_area):
        ma = cis_with_market_area.data.market_area.get("ma1")
        order = Order(name="o1", price=10.0, market_area=ma)

        ChangeSetHandler._fill_object(order, {"price": 20.0})

        assert order.price == 20.0

    def test_fill_object_invalid_type_raises(self, cis_with_market_area):
        ma = cis_with_market_area.data.market_area.get("ma1")
        order = Order(name="o1", price=10.0, market_area=ma)

        with pytest.raises(ValidationError):
            ChangeSetHandler._fill_object(order, {"price": "invalid"})


class TestAddChangeSetHandler:
    def test_add_creates_object(self, cis_with_market_area):
        add = AddObject({"name": "o1", "market_area": "ma1"}, model_type=Order)
        ChangeSetHandler.apply(add, cis_with_market_area)

        assert "o1" in cis_with_market_area.data.order

    def test_add_duplicate_raises(self, cis_with_market_area):
        add = AddObject({"name": "o1", "market_area": "ma1"}, model_type=Order)
        ChangeSetHandler.apply(add, cis_with_market_area)

        with pytest.raises(ValueError):
            ChangeSetHandler.apply(add, cis_with_market_area)

    def test_add_failure_does_not_pollute_container(self, cis_with_market_area):
        # Use an invalid price type to trigger validation error
        add = AddObject({"name": "o1", "market_area": "ma1", "price": "invalid_string"}, model_type=Order)

        # Now raises ValueError wrapping ValidationError
        with pytest.raises(ValueError):
            ChangeSetHandler.apply(add, cis_with_market_area)

        assert "o1" not in cis_with_market_area.data.order


class TestUpdateChangeSetHandler:
    def test_update_mutates_existing_object(self, cis_with_order):
        update = UpdateObject({"name": "order_1", "price": 42.0}, Order)
        ChangeSetHandler.apply(update, cis_with_order)

        assert cis_with_order.data.order.get("order_1").price == 42.0

    def test_update_preserves_identity(self, cis_with_order):
        obj = cis_with_order.data.order.get("order_1")

        update = UpdateObject({"name": "order_1", "price": 99.0}, Order)
        ChangeSetHandler.apply(update, cis_with_order)

        assert cis_with_order.data.order.get("order_1") is obj

    def test_update_missing_object_raises(self, cis):
        update = UpdateObject({"name": "missing", "price": 10.0}, Order)

        with pytest.raises(ValueError):
            ChangeSetHandler.apply(update, cis)


class TestDeleteChangeSetHandler:
    def test_remove_existing_object(self, cis_with_order):
        assert "order_1" in cis_with_order.data.order

        remove = DeleteObject(
            "order_1",
            model_type=Order,
        )

        ChangeSetHandler.apply(remove, cis_with_order)

        assert "order_1" not in cis_with_order.data.order

    def test_remove_preserves_other_objects(self, cis_with_market_area):
        ma = cis_with_market_area.data.market_area.get("ma1")
        order1 = Order(name="order_1", price=10.0, market_area=ma)
        order2 = Order(name="order_2", price=20.0, market_area=ma)

        cis_with_market_area.data.order.add(order1)
        cis_with_market_area.data.order.add(order2)

        remove = DeleteObject(
            "order_1",
            model_type=Order,
        )

        ChangeSetHandler.apply(remove, cis_with_market_area)

        assert "order_1" not in cis_with_market_area.data.order
        assert "order_2" in cis_with_market_area.data.order

    def test_remove_non_existing_object_raises(self, cis):
        remove = DeleteObject(
            "unknown",
            model_type=Order,
        )

        with pytest.raises(ValueError):
            ChangeSetHandler.apply(remove, cis)

    def test_remove_does_not_touch_other_collections(self, cis_with_market_area):
        ma = cis_with_market_area.data.market_area.get("ma1")
        order = Order(name="order_1", price=10.0, market_area=ma)
        cis_with_market_area.data.order.add(order)

        remove = DeleteObject(
            "order_1",
            model_type=Order,
        )

        ChangeSetHandler.apply(remove, cis_with_market_area)

        assert "order_1" not in cis_with_market_area.data.order
        assert "ma1" in cis_with_market_area.data.market_area
