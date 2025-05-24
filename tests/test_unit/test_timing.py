from datetime import datetime

import pendulum
import polars as pl
import pytest

from atlas.timing import build_datetime, generate_datetimes, infer_frequency, parse_frequency


def test_infer_frequency_regular_hourly():
    times = [pendulum.datetime(2025, 1, 1, hour) for hour in range(5)]
    df = pl.DataFrame({"time": times, "value": [1, 2, 3, 4, 5]})
    freq = infer_frequency(df)
    assert freq == pendulum.duration(hours=1)


def test_infer_frequency_regular_minutes():
    times = [pendulum.datetime(2025, 1, 1, 0, m) for m in range(0, 60, 15)]
    df = pl.DataFrame({"time": times, "value": [1, 2, 3, 4]})
    freq = infer_frequency(df)
    assert freq == pendulum.duration(minutes=15)


def test_infer_frequency_irregular_raises():
    times = [
        pendulum.datetime(2025, 1, 1, 0, 0),
        pendulum.datetime(2025, 1, 1, 0, 10),
        pendulum.datetime(2025, 1, 1, 0, 25),
    ]
    df = pl.DataFrame({"time": times, "value": [1, 2, 3]})
    with pytest.raises(ValueError):
        infer_frequency(df)


def test_infer_frequency_single_row():
    times = [pendulum.datetime(2025, 1, 1, 0, 0)]
    df = pl.DataFrame({"time": times, "value": [1]})
    freq = infer_frequency(df)
    assert freq == pendulum.duration()


def test_infer_frequency_empty():
    df = pl.DataFrame({"time": [], "value": []})
    freq = infer_frequency(df)
    assert freq == pendulum.duration()


def test_build_datetime_from_string():
    dt_str = "2025-05-23 15:30:00"
    result = build_datetime(dt_str)
    assert isinstance(result, pendulum.DateTime)
    assert result.year == 2025
    assert result.month == 5
    assert result.day == 23
    assert result.hour == 15
    assert result.minute == 30
    assert result.second == 0


def test_build_datetime_from_datetime():
    dt = datetime(2025, 5, 23, 15, 30, 0)
    result = build_datetime(dt)
    assert isinstance(result, pendulum.DateTime)
    assert result.year == 2025
    assert result.month == 5
    assert result.day == 23
    assert result.hour == 15
    assert result.minute == 30
    assert result.second == 0


def test_build_datetime_from_pendulum():
    dt = pendulum.datetime(2025, 5, 23, 15, 30, 0)
    result = build_datetime(dt)
    assert isinstance(result, pendulum.DateTime)
    assert result == dt


@pytest.mark.parametrize(
    "freq_str, expected",
    [
        ("15m", pendulum.duration(minutes=15)),
        ("1h", pendulum.duration(hours=1)),
        ("2h30m", pendulum.duration(hours=2, minutes=30)),
        ("1d", pendulum.duration(days=1)),
        ("1d2h15m10s", pendulum.duration(days=1, hours=2, minutes=15, seconds=10)),
        ("1w", pendulum.duration(weeks=1)),
        ("1y", pendulum.duration(years=1)),
        ("1M", pendulum.duration(months=1)),
        ("100ms", pendulum.duration(milliseconds=100)),
        ("250us", pendulum.duration(microseconds=250)),
    ],
)
def test_parse_frequency_valid(freq_str, expected):
    result = parse_frequency(freq_str)
    assert result == expected


def test_parse_frequency_invalid():
    with pytest.raises(ValueError):
        parse_frequency("foo")
    with pytest.raises(ValueError):
        parse_frequency("10q")


def test_generate_datetimes_with_different_freq():
    """Test generating datetimes with different frequencies."""
    # Test minute frequency
    start = datetime(2023, 1, 1, 0, 0)
    end = datetime(2023, 1, 1, 0, 10)
    result_minutes = generate_datetimes(start, end, freq="5m")
    assert len(result_minutes) == 3
    assert result_minutes == [
        datetime(2023, 1, 1, 0, 0, tzinfo=pendulum.UTC),
        datetime(2023, 1, 1, 0, 5, tzinfo=pendulum.UTC),
        datetime(2023, 1, 1, 0, 10, tzinfo=pendulum.UTC),
    ]

    # Test daily frequency
    start = datetime(2023, 1, 1)
    end = datetime(2023, 1, 5)
    result_days = generate_datetimes(start, end, freq="1d")
    assert len(result_days) == 5
    assert result_days == [
        datetime(2023, 1, 1, tzinfo=pendulum.UTC),
        datetime(2023, 1, 2, tzinfo=pendulum.UTC),
        datetime(2023, 1, 3, tzinfo=pendulum.UTC),
        datetime(2023, 1, 4, tzinfo=pendulum.UTC),
        datetime(2023, 1, 5, tzinfo=pendulum.UTC),
    ]


def test_generate_datetimes_with_different_freq_as_duration():
    """Test generating datetimes with different frequencies."""
    # Test minute frequency
    start = datetime(2023, 1, 1, 0, 0)
    end = datetime(2023, 1, 1, 0, 10)
    result_minutes = generate_datetimes(start, end, freq=pendulum.duration(minutes=5))
    assert len(result_minutes) == 3
    assert result_minutes == [
        datetime(2023, 1, 1, 0, 0, tzinfo=pendulum.UTC),
        datetime(2023, 1, 1, 0, 5, tzinfo=pendulum.UTC),
        datetime(2023, 1, 1, 0, 10, tzinfo=pendulum.UTC),
    ]

    # Test daily frequency
    start = datetime(2023, 1, 1)
    end = datetime(2023, 1, 5)
    result_days = generate_datetimes(start, end, freq=pendulum.duration(days=1))
    assert len(result_days) == 5
    assert result_days == [
        datetime(2023, 1, 1, tzinfo=pendulum.UTC),
        datetime(2023, 1, 2, tzinfo=pendulum.UTC),
        datetime(2023, 1, 3, tzinfo=pendulum.UTC),
        datetime(2023, 1, 4, tzinfo=pendulum.UTC),
        datetime(2023, 1, 5, tzinfo=pendulum.UTC),
    ]


def test_generate_datetimes_with_invalid_type():
    """Test generating datetimes with different frequencies."""
    # Test minute frequency
    start = datetime(2023, 1, 1, 0, 0)
    end = datetime(2023, 1, 1, 0, 10)
    with pytest.raises(TypeError):
        generate_datetimes(start, end, freq=2)


def test_generate_datetimes_invalid_freq():
    """Test generating datetimes with an invalid frequency."""
    start = datetime(2023, 1, 1)
    end = datetime(2023, 1, 5)

    with pytest.raises(ValueError):
        generate_datetimes(start, end, freq="1q")
