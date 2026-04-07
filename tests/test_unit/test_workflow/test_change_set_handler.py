import pytest
from pydantic_core._pydantic_core import ValidationError

from atlas import MarketArea
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.models.market.order import Order
from atlas.orchestrator.change_set import AddObject, DeleteObject, UpdateObject
from atlas.orchestrator.current_input_state import CurrentInputState
from atlas.orchestrator.handler.change_set_handler import ChangeSetHandler


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
def cis_with_order(cis):
    order = Order(name="order_1", price=10.0)
    cis.data.order.add(order)
    return cis


class TestChangeSetSharedBehavior:
    def test_resolve_reference_str(self, cis):
        ma = MarketArea(name="ma1")
        cis.data.market_area.add(ma)

        order = Order.model_validate({"name": "o1"})
        data = {"market_area": "ma1"}

        ChangeSetHandler._resolve_reference(order, data, cis)

        assert data["market_area"] is ma

    def test_resolve_reference_obj(self, cis):
        ma = MarketArea(name="ma1")
        cis.data.market_area.add(ma)

        order = Order.model_validate({"name": "o1"})
        data = {"market_area": MarketArea(name="ma1")}

        ChangeSetHandler._resolve_reference(order, data, cis)

        assert data["market_area"] is ma

    def test_resolve_reference_missing_raises(self, cis):
        order = Order.model_validate({"name": "o1"})
        data = {"market_area": "missing"}

        with pytest.raises(ValueError):
            ChangeSetHandler._resolve_reference(order, data, cis)

    def test_fill_object_valid(self):
        order = Order(name="o1", price=10.0)

        ChangeSetHandler._fill_object(order, {"price": 20.0})

        assert order.price == 20.0

    def test_fill_object_invalid_type_raises(self):
        order = Order(name="o1", price=10.0)

        with pytest.raises(ValidationError):
            ChangeSetHandler._fill_object(order, {"price": "invalid"})


class TestAddChangeSetHandler:
    def test_add_creates_object(self, cis):
        add = AddObject({"name": "o1"}, model_type=Order)
        ChangeSetHandler.apply(add, cis)

        assert "o1" in cis.data.order

    def test_add_duplicate_raises(self, cis):
        add = AddObject({"name": "o1"}, model_type=Order)
        ChangeSetHandler.apply(add, cis)

        with pytest.raises(ValueError):
            ChangeSetHandler.apply(add, cis)

    def test_add_failure_does_not_pollute_container(self, cis):
        add = AddObject({"name": "o1", "foo": "bar"}, model_type=Order)

        with pytest.raises(ValidationError):
            ChangeSetHandler.apply(add, cis)

        assert "o1" not in cis.data.order


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

    def test_remove_preserves_other_objects(self, cis):
        order1 = Order(name="order_1", price=10.0)
        order2 = Order(name="order_2", price=20.0)

        cis.data.order.add(order1)
        cis.data.order.add(order2)

        remove = DeleteObject(
            "order_1",
            model_type=Order,
        )

        ChangeSetHandler.apply(remove, cis)

        assert "order_1" not in cis.data.order
        assert "order_2" in cis.data.order

    def test_remove_non_existing_object_raises(self, cis):
        remove = DeleteObject(
            "unknown",
            model_type=Order,
        )

        with pytest.raises(ValueError):
            ChangeSetHandler.apply(remove, cis)

    def test_remove_does_not_touch_other_collections(self, cis):
        ma = MarketArea(name="ma1")
        cis.data.market_area.add(ma)

        order = Order(name="order_1", price=10.0)
        cis.data.order.add(order)

        remove = DeleteObject(
            "order_1",
            model_type=Order,
        )

        ChangeSetHandler.apply(remove, cis)

        assert "order_1" not in cis.data.order
        assert "ma1" in cis.data.market_area
