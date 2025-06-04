import pytest

from atlas.timing import datetime_to_pendulum, pendulum_to_datetime


@pytest.mark.parametrize(
    "dt_fmt,expected_pendulum_fmt",
    [
        ("%Y-%m-%d", "YYYY-MM-DD"),
        ("%H:%M:%S", "HH:mm:ss"),
        ("%I:%M %p", "hh:mm A"),
        ("%B %d, %Y", "MMMM DD, YYYY"),
        ("%A, %B %d", "dddd, MMMM DD"),
        ("%j %U %W", "DDDD ww ww"),
        ("%c", "llll"),
        ("%x", "ll"),
        ("%X", "LTS"),
    ],
)
def test_datetime_to_pendulum(dt_fmt, expected_pendulum_fmt):
    result = datetime_to_pendulum(dt_fmt)
    assert result == expected_pendulum_fmt


@pytest.mark.parametrize(
    "pendulum_fmt,expected_dt_fmt",
    [
        ("YYYY-MM-DD", "%Y-%m-%d"),
        ("HH:mm:ss", "%H:%M:%S"),
        ("hh:mm A", "%I:%M %p"),
        ("MMMM DD, YYYY", "%B %d, %Y"),
        ("DDDD ww ww", "%j %W %W"),  # `%W` used for both "ww"
        ("llll", "%c"),
        ("ll", "%x"),
        ("LTS", "%X"),
    ],
)
def test_pendulum_to_datetime(pendulum_fmt, expected_dt_fmt):
    result = pendulum_to_datetime(pendulum_fmt)
    assert result == expected_dt_fmt


def test_round_trip_conversion():
    original_fmt = "%Y-%m-%d %H:%M:%S"
    pendulum_fmt = datetime_to_pendulum(original_fmt)
    back_to_dt = pendulum_to_datetime(pendulum_fmt)
    assert back_to_dt == original_fmt
