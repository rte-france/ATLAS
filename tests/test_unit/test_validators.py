import pytest
from pendulum import duration

from atlas.validators import convert_to_duration


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


def test_duration_P_stirng():
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
