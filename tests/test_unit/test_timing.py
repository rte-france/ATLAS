from datetime import UTC, datetime, timedelta

import pendulum
import polars as pl
import pytest

from atlas.timing import (
    build_datetime,
    datetime_to_pendulum,
    epoch_key,
    generate_datetimes,
    infer_frequency,
    parse_frequency,
    pendulum_to_datetime,
)


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


JAN_1_2025_UTC_US = 1_735_689_600_000_000


def test_epoch_key_utc_datetime():
    assert epoch_key(pendulum.datetime(2025, 1, 1, tz="UTC")) == JAN_1_2025_UTC_US


def test_epoch_key_same_instant_in_other_timezone():
    paris = pendulum.datetime(2025, 1, 1, 1, tz="Europe/Paris")
    assert epoch_key(paris) == JAN_1_2025_UTC_US


def test_epoch_key_stdlib_aware_datetime():
    assert epoch_key(datetime(2025, 1, 1, tzinfo=UTC)) == JAN_1_2025_UTC_US


def test_epoch_key_distinguishes_ambiguous_dst_hour():
    # 2025-10-26 02:30 happens twice in Europe/Paris: first at UTC+2, then at UTC+1.
    first = pendulum.datetime(2025, 10, 26, 0, 30, tz="UTC").in_tz("Europe/Paris")
    second = pendulum.datetime(2025, 10, 26, 1, 30, tz="UTC").in_tz("Europe/Paris")
    assert epoch_key(second) - epoch_key(first) == 3_600_000_000


def test_epoch_key_is_exact_to_the_microsecond():
    dt = pendulum.datetime(2025, 1, 1, 0, 0, 0, 123_457, tz="UTC")
    assert epoch_key(dt) == JAN_1_2025_UTC_US + 123_457


def test_epoch_key_matches_timestamp():
    dt = pendulum.datetime(2031, 7, 14, 13, 45, tz="Europe/Paris")
    assert epoch_key(dt) == int(dt.timestamp()) * 1_000_000


def test_epoch_key_naive_datetime_follows_build_datetime():
    naive = datetime(2025, 1, 1)
    assert epoch_key(naive, timezone="Europe/Paris") == epoch_key(build_datetime(naive).in_tz("Europe/Paris"))
    assert epoch_key(naive) == JAN_1_2025_UTC_US


def test_epoch_key_string():
    assert epoch_key("2025-01-01 00:00:00") == JAN_1_2025_UTC_US
    assert epoch_key("01/01/2025 01h", date_format="DD/MM/YYYY HH[h]") == JAN_1_2025_UTC_US + 3_600_000_000


def test_epoch_key_before_epoch():
    assert epoch_key(pendulum.datetime(1969, 12, 31, 23, 59, 59, tz="UTC")) == -1_000_000


def test_epoch_key_unsupported_type():
    with pytest.raises(TypeError):
        epoch_key(timedelta(hours=1))  # type: ignore[arg-type]
