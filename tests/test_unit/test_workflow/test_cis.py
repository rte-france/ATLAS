import pytest
from atlas import MarketArea, Node, Order
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.workflow.current_input_state import CurrentInputState


@pytest.fixture
def dataset():
    ds = AtlasDataset()
    ds.order.add(Order(name="order_1", price=10))
    ds.order.add(Order(name="order_2", price=50))
    ds.market_area.add(MarketArea(name="ma1"))
    ds.market_area.add(MarketArea(name="ma2"))
    ds.node.add(Node(name="NodeA"))
    ds.node.add(Node(name="NodeB"))
    return ds


@pytest.fixture
def cis(dataset):
    return CurrentInputState(dataset)


class TestFilterDataset:
    def test_include_types_only(self, cis):
        subset = cis.filter_dataset(included_types=["order", "market_area"])
        data = subset.to_dict()
        assert "order" in data
        assert "market_area" in data
        assert "node" not in data
        assert len(subset.order) == 2
        assert len(subset.market_area) == 2

    def test_filter_only(self, cis):
        subset = cis.filter_dataset(filters={"node": lambda n: n.name.startswith("NodeA")})
        nodes = subset.node.all()
        assert len(nodes) == 1
        assert nodes[0].name == "NodeA"
        # Only node key should be present
        data_keys = subset.to_dict().keys()
        assert "node" in data_keys
        assert "order" not in data_keys

    def test_include_and_filter(self, cis):
        subset = cis.filter_dataset(
            included_types=["order", "node"], filters={"node": lambda n: n.name.startswith("NodeB")}
        )
        data = subset.to_dict()
        # Orders included fully because node has filter
        assert "order" in data
        assert len(subset.order) == 2
        # Nodes filtered
        nodes = subset.node.all()
        assert len(nodes) == 1
        assert nodes[0].name == "NodeB"

    def test_filter_takes_precedence_over_included(self, cis):
        # Node is in included_types but has a filter → should be filtered
        subset = cis.filter_dataset(included_types=["node"], filters={"node": lambda n: n.name.startswith("NodeB")})
        nodes = subset.node.all()
        assert len(nodes) == 1
        assert nodes[0].name == "NodeB"

    def test_empty_included_types_and_filters(self, cis):
        subset = cis.filter_dataset()
        assert subset.to_dict() == {}

    def test_unknown_type_included_types(self, cis):
        subset = cis.filter_dataset(included_types=["unknown_type"])
        assert subset.to_dict() == {}

    def test_unknown_type_in_filters(self, cis):
        subset = cis.filter_dataset(filters={"unknown_type": lambda x: True})
        assert subset.to_dict() == {}

    def test_combined_filters_and_included_types(self, cis):
        # Include orders, filter orders by price > 20
        subset = cis.filter_dataset(included_types=["order"], filters={"order": lambda o: o.price > 20})
        orders = subset.order.all()
        assert len(orders) == 1
        assert orders[0].name == "order_2"
