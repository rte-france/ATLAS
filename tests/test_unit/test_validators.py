import pytest
from pendulum import duration

from atlas.models.business_model import BusinessModel
from atlas.models.equipment.equipment import Equipment
from atlas.models.node import Node
from atlas.models.portfolio import Portfolio
from atlas.validators import (
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

    # Create test instances
    node = Node(name="test_node")
    portfolio = Portfolio(name="test_portfolio")

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

    equipment_no_node = Equipment(name="test_no_node", node=None, portfolio=None)
    dumped_no_node = equipment_no_node.model_dump(mode="json")
    assert dumped_no_node["node"] is None
    assert dumped_no_node["portfolio"] is None
