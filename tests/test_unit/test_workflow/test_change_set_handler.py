import pytest

from atlas import MarketArea
from atlas.models.market.order import Order
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.workflow.change_set.change_set import AddObject
from atlas.workflow.current_input_state import CurrentInputState
from atlas.workflow.handler.changet_set_handler import ChangeSetHandler


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


class TestSimpleAddChangeSetHandler:
    def test_add_simple_order(self, cis):
        data = {
            "name": "order_1",
        }

        add_order = AddObject.from_obj(Order(**data))

        ChangeSetHandler.apply(add_order, cis)

        assert "order_1" in cis.data.order

    def test_add_order_already_present(self, cis):
        data = {
            "name": "order_1",
        }

        # model_type is automatically inferred in AddObject
        add_order = AddObject.from_obj(Order(**data))

        ChangeSetHandler.apply(add_order, cis)
        with pytest.raises(ValueError, match="Item with name 'order_1' already exists"):
            ChangeSetHandler.apply(add_order, cis)

        assert "order_1" in cis.data.order

    def test_add_order_with_market_area_present_as_str(self, cis):
        market_area_1 = MarketArea(name="market_area_1")
        cis.data.market_area.add(market_area_1)

        data = {"name": "order_1", "market_area": "market_area_1"}

        # model_type is automatically inferred in AddObject
        add_order = AddObject(data, model_type=Order)

        ChangeSetHandler.apply(add_order, cis)

        assert "order_1" in cis.data.order
        assert cis.data.order.get("order_1").market_area.name == "market_area_1"
        assert cis.data.order.get("order_1").market_area == market_area_1

    def test_add_order_with_market_area_present_as_obj(self, cis):
        market_area_1 = MarketArea(name="market_area_1")
        cis.data.market_area.add(market_area_1)

        data = {"name": "order_1", "market_area": MarketArea(name="market_area_1")}

        # model_type is automatically inferred in AddObject
        add_order = AddObject(data, model_type=Order)

        ChangeSetHandler.apply(add_order, cis)

        assert "order_1" in cis.data.order
        assert cis.data.order.get("order_1").market_area.name == "market_area_1"
        assert cis.data.order.get("order_1").market_area == market_area_1

    def test_add_order_with_non_businessmodel_reference(self, cis):
        data = {
            "name": "order_1",
            "price": 42.0,  # simple float attribute
        }
        add_order = AddObject(data, model_type=Order)

        ChangeSetHandler._add(add_order, cis)

        assert cis.data.order.get("order_1").price == 42.0


class TestAddObjectHandlerEdgeCases:
    def test_add_order_with_missing_reference_str_raises(self, cis):
        # MarketArea "unknown" does not exist in CIS
        data = {"name": "order_1", "market_area": "unknown"}
        add_order = AddObject(data, model_type=Order)

        with pytest.raises(ValueError, match="can't be retrieve"):
            ChangeSetHandler._add(add_order, cis)

    def test_add_order_with_missing_reference_obj_raises(self, cis):
        # MarketArea instance not yet in CIS
        missing_ma = MarketArea(name="missing")
        data = {"name": "order_1", "market_area": missing_ma}
        add_order = AddObject(data, model_type=Order)

        with pytest.raises(ValueError, match="is not present"):
            ChangeSetHandler._add(add_order, cis)

    def test_add_order_with_optional_reference_none(self, cis):
        # Optional attribute with None should work
        data = {"name": "order_1", "market_area": None}
        add_order = AddObject(data, model_type=Order)

        ChangeSetHandler._add(add_order, cis)

        order = cis.data.order.get("order_1")
        assert order.market_area is None

    def test_add_order_with_unrelated_attribute(self, cis):
        # Extra attribute not in Order should raise TypeError
        data = {"name": "order_1", "foo": "bar"}
        add_order = AddObject(data, model_type=Order)

        with pytest.raises(TypeError):
            ChangeSetHandler._add(add_order, cis)
