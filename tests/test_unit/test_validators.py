import pytest
from pendulum import duration
from pydantic import BaseModel, ValidationError

from atlas.objects.business_model import BusinessModel
from atlas.objects.equipment.equipment import Equipment
from atlas.objects.market.market_area import MarketArea
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling
from atlas.objects.market_operator.portfolio import Portfolio
from atlas.objects.network.node import Node
from atlas.objects.network_operator.control_block import ControlBlock
from atlas.validators import (
    DateFormat,
    PipeSeparatedFloats,
    convert_to_duration,
    serializer_business_model,
    serializer_list_business_model,
    serializer_list_float,
)


def test_basic_conversions():
    """Test basic number to duration conversions."""
    # Hours
    result = convert_to_duration("2h")
    assert result.total_seconds() == 7200  # 2 hours

    # Hours and minutes
    result = convert_to_duration("2h30m")
    assert result.total_seconds() == 9000  # 2 hours and 30 minutes

    # Minutes
    result = convert_to_duration("30m")
    assert result.total_seconds() == 1800  # 30 minutes

    # Seconds
    result = convert_to_duration("90s")
    assert result.total_seconds() == 90

    # None handling
    assert convert_to_duration(None) is None


def test_none_and_zero():
    """Test None and zero inputs."""
    assert convert_to_duration(None) is None
    assert convert_to_duration("0s").total_seconds() == 0


def test_duration_objects():
    """Test that duration objects pass through."""
    dur = duration(hours=1, minutes=30)
    result = convert_to_duration(dur)
    assert result.total_seconds() == dur.total_seconds()


def test_duration_P_string():
    """Test that duration objects pass through."""
    dur = "P"

    result = convert_to_duration(dur)
    assert result.total_seconds() == 0


def test_errors():
    """Test error cases."""
    # Negative values
    with pytest.raises(ValueError):
        convert_to_duration(-1)

    # Zero not allowed
    with pytest.raises(ValueError):
        convert_to_duration("0s", allow_zero=False)

    # Invalid value
    with pytest.raises(ValueError):
        convert_to_duration("invalide format")

    # Invalid types
    with pytest.raises(ValueError):
        convert_to_duration(0)


def test_serializer_business_model_valid():
    """Test serializer_business_model with valid BusinessModel instance."""
    # Create a simple BusinessModel instance
    bm = BusinessModel(name="test_model")
    result = serializer_business_model(bm)
    assert result == "test_model"


def test_serializer_business_model_none():
    """Test serializer_business_model with None value."""
    result = serializer_business_model(None)
    assert result is None


def test_serializer_business_model_invalid():
    """Test serializer_business_model with invalid input."""
    with pytest.raises(ValueError, match="Expected BusinessModel instance"):
        serializer_business_model("not_a_business_model")

    with pytest.raises(ValueError, match="Expected BusinessModel instance"):
        serializer_business_model(123)


def test_serializer_list_float_valid():
    """Test serializer_list_float with valid list of floats."""
    result = serializer_list_float([1.0, 2.5, 3.7])
    assert result == "1.0|2.5|3.7"

    result = serializer_list_float([0.0])
    assert result == "0.0"

    result = serializer_list_float([])
    assert result == ""


def test_serializer_list_float_none():
    """Test serializer_list_float with None value."""
    result = serializer_list_float(None)
    assert result is None


def test_serializer_list_float_invalid():
    """Test serializer_list_float with invalid input."""
    with pytest.raises(ValueError, match="Expected list of floats"):
        serializer_list_float("not_a_list")

    with pytest.raises(ValueError, match="Expected list of floats"):
        serializer_list_float(123)


def test_serializer_list_business_model_valid():
    """Test serializer_list_business_model with valid list of BusinessModel instances."""
    bm1 = BusinessModel(name="model_1")
    bm2 = BusinessModel(name="model_2")
    bm3 = BusinessModel(name="model_3")

    result = serializer_list_business_model([bm1, bm2, bm3])
    assert result == "model_1|model_2|model_3"

    result = serializer_list_business_model([bm1])
    assert result == "model_1"

    result = serializer_list_business_model([])
    assert result == ""


def test_serializer_list_business_model_none():
    """Test serializer_list_business_model with None value."""
    result = serializer_list_business_model(None)
    assert result is None


def test_serializer_list_business_model_invalid():
    """Test serializer_list_business_model with invalid input."""
    with pytest.raises(ValueError, match="Expected list of BusinessModel"):
        serializer_list_business_model("not_a_list")

    with pytest.raises(ValueError, match="Expected list of BusinessModel"):
        serializer_list_business_model(123)


def test_field_serializer_integration():
    """Test that field serializers work correctly with model_dump(mode='json')."""

    # Create test instances with required nested objects
    control_block = ControlBlock(name="test_cb")
    market_area = MarketArea(name="test_ma", control_block=control_block)
    node = Node(name="test_node", control_block=control_block, market_area=market_area)
    portfolio = Portfolio(name="test_portfolio", control_block=control_block, market_area=market_area)

    equipment = Equipment(
        name="test_equipment",
        node=node,
        portfolio=portfolio,
        co2_emission_factor=0.5,
    )

    dumped = equipment.model_dump(mode="json")

    assert dumped["name"] == "test_equipment"
    assert dumped["node"] == "test_node"
    assert dumped["portfolio"] == "test_portfolio"
    assert dumped["co2_emission_factor"] == 0.5


class DummyEquipment(Equipment):
    """Equipment subclass, to check that a reference typed with the base class accepts it."""


def test_resolve_by_name_round_trip():
    """A dumped reference is a name, and resolves back to the very same instance."""
    control_block = ControlBlock(name="test_cb")
    market_area = MarketArea(name="test_ma", control_block=control_block)
    registry = {"test_cb": [control_block], "test_ma": [market_area]}

    dumped = Node(name="test_node", control_block=control_block, market_area=market_area).model_dump()
    assert dumped["control_block"] == "test_cb"

    node = Node.model_validate(dumped, context={"registry": registry})

    assert node.control_block is control_block
    assert node.market_area is market_area


def test_resolve_by_name_list_round_trip():
    """List references are serialized pipe-separated and resolved back in order."""
    control_block = ControlBlock(name="cb")
    market_area = MarketArea(name="ma", control_block=control_block)
    orders = [Order(name="order_1", market_area=market_area), Order(name="order_2", market_area=market_area)]
    registry = {"order_1": [orders[0]], "order_2": [orders[1]]}

    dumped = OrderCoupling(name="coupling", orders=orders).model_dump()
    assert dumped["orders"] == "order_1|order_2"

    coupling = OrderCoupling.model_validate(dumped, context={"registry": registry})

    assert coupling.orders == orders


def test_resolve_by_name_uses_the_annotated_type():
    """Objects of different types may share a name: the field annotation picks the right one."""
    control_block = ControlBlock(name="fr")
    market_area = MarketArea(name="fr", control_block=control_block)
    registry = {"fr": [control_block, market_area]}

    node = Node.model_validate(
        {"name": "node_fr", "control_block": "fr", "market_area": "fr"}, context={"registry": registry}
    )

    assert node.control_block is control_block
    assert node.market_area is market_area


def test_resolve_by_name_accepts_a_subclass():
    """A reference typed with a base class resolves to any registered subclass."""
    control_block = ControlBlock(name="cb")
    market_area = MarketArea(name="ma", control_block=control_block)
    node = Node(name="node", control_block=control_block, market_area=market_area)
    portfolio = Portfolio(name="portfolio", control_block=control_block, market_area=market_area)
    equipment = DummyEquipment(name="eq", node=node, portfolio=portfolio)
    registry = {"ma": [market_area], "eq": [equipment]}

    order = Order.model_validate(
        {"name": "order", "market_area": "ma", "equipment": "eq"}, context={"registry": registry}
    )

    assert order.equipment is equipment


def test_resolve_by_name_unknown_reference():
    control_block = ControlBlock(name="cb")
    registry = {"cb": [control_block], "ma": [MarketArea(name="ma", control_block=control_block)]}

    with pytest.raises(ValidationError, match="No ControlBlock named 'typo'"):
        Node.model_validate(
            {"name": "node", "control_block": "typo", "market_area": "ma"}, context={"registry": registry}
        )


def test_resolve_by_name_without_registry_is_a_passthrough():
    """Direct construction from real objects is unaffected, and a name stays an invalid value."""
    control_block = ControlBlock(name="cb")
    market_area = MarketArea(name="ma", control_block=control_block)

    assert Node(name="node", control_block=control_block, market_area=market_area).control_block is control_block

    with pytest.raises(ValidationError, match="ControlBlock"):
        Node.model_validate({"name": "node", "control_block": "cb", "market_area": "ma"})


class _PipeModel(BaseModel):
    values: PipeSeparatedFloats = None


def test_pipe_separated_floats_round_trip():
    """PipeSeparatedFloats parses "a|b" on validation and re-emits it on dump."""
    assert _PipeModel.model_validate({"values": "1.0|2.5"}).values == [1.0, 2.5]
    assert _PipeModel.model_validate({"values": [1.0, 2.5]}).values == [1.0, 2.5]
    assert _PipeModel(values=[1.0, 2.5]).model_dump(mode="json")["values"] == "1.0|2.5"

    assert _PipeModel.model_validate({"values": None}).values is None
    assert _PipeModel().model_dump(mode="json")["values"] is None

    with pytest.raises(ValidationError):
        _PipeModel.model_validate({"values": "a|b"})


class _DateFormatModel(BaseModel):
    fmt: DateFormat = "YYYY-MM-DD HH:mm:ss"


def test_date_format_accepts_pendulum_tokens():
    """Genuine pendulum format tokens round-trip through format/parse."""
    assert _DateFormatModel(fmt="YYYY-MM-DD HH:mm:ss").fmt == "YYYY-MM-DD HH:mm:ss"
    assert _DateFormatModel(fmt="DD/MM/YYYY").fmt == "DD/MM/YYYY"


def test_date_format_rejects_garbage():
    """Strings with no or malformed date tokens fail the format/parse round-trip."""
    with pytest.raises(ValidationError, match="Invalid date format"):
        _DateFormatModel(fmt="hello world")

    with pytest.raises(ValidationError, match="Invalid date format"):
        _DateFormatModel(fmt="ZZZZZZZ")
