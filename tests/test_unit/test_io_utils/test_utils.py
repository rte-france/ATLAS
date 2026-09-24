import pandas as pd
import pendulum
import polars as pl
import pytest

from atlas.io_utils.utils import deep_update, get_metadata_from_file, get_metadata_from_frame, deduplicate_names


def test_get_metadata_from_frame_polars():
    df = pl.DataFrame(
        {
            "time": [pendulum.datetime(2025, 1, 1), pendulum.datetime(2025, 1, 2)],
            "category": ["A", "B"],
            "value": [1.0, 2.0],
        }
    )
    meta = get_metadata_from_frame(df)
    assert meta == {
        "shape": (2, 3),
        "memory_mb": "0.00",
        "datetime": {
            "column": "time",
            "min": "2025-01-01 00:00:00",
            "max": "2025-01-02 00:00:00",
            "nulls": 0,
        },
        "categorical": {"column": "category", "categories": ["A", "B"], "nulls": 0},
        "numerical": {"column": "value", "nulls": 0, "min": 1.0, "max": 2.0},
    }


def test_get_metadata_from_frame_pandas():
    df = pd.DataFrame(
        {
            "time": [pendulum.datetime(2025, 1, 1), pendulum.datetime(2025, 1, 2)],
            "category": ["A", "B"],
            "value": [1.0, 2.0],
        }
    )
    meta = get_metadata_from_frame(df)
    assert meta["shape"] == (2, 3)
    assert meta["datetime"]["column"] == "time"
    assert meta["categorical"]["column"] == "category"
    assert meta["numerical"]["column"] == "value"


def test_get_metadata_from_frame_multiple_numeric():
    df = pl.DataFrame(
        {
            "time": [pendulum.datetime(2025, 1, 1), pendulum.datetime(2025, 1, 2)],
            "value1": [1.0, 2.0],
            "value2": [3.0, 4.0],
        }
    )
    meta = get_metadata_from_frame(df)
    assert "numericals" in meta
    assert set(meta["numericals"]) == {"value1", "value2"}


def test_get_metadata_from_frame_invalid():
    df = pl.DataFrame(
        {
            "time1": [pendulum.datetime(2025, 1, 1), pendulum.datetime(2025, 1, 2)],
            "time2": [pendulum.datetime(2025, 1, 3), pendulum.datetime(2025, 1, 4)],
            "value": [1.0, 2.0],
        }
    )
    with pytest.raises(ValueError):
        get_metadata_from_frame(df)


def test_get_metadata_from_file(tmp_path):
    df = pl.DataFrame(
        {
            "time": [pendulum.datetime(2025, 1, 1), pendulum.datetime(2025, 1, 2)],
            "category": ["A", "B"],
            "value": [1.0, 2.0],
        }
    )
    file_path = tmp_path / "test.parquet"
    df.write_parquet(file_path)
    meta = get_metadata_from_file(file_path)
    assert meta == {
        "shape": (2, 3),
        "memory_mb": "0.00",
        "datetime": {
            "column": "time",
            "min": "2025-01-01 00:00:00",
            "max": "2025-01-02 00:00:00",
            "nulls": 0,
        },
        "categorical": {"column": "category", "categories": ["A", "B"], "nulls": 0},
        "numerical": {"column": "value", "nulls": 0, "min": 1.0, "max": 2.0},
    }


def test_deep_update():
    a = {"t": {"a": 0, "b": 2}}
    x = {"t": {"a": -1, "b": 2, "c": -3}}
    y = {"t": {"a": 1, "c": 3}}

    deep_update(a, x, False)
    assert a == {"t": {"a": 0, "b": 2, "c": -3}}
    assert x == {"t": {"a": -1, "b": 2, "c": -3}}
    assert y == {"t": {"a": 1, "c": 3}}

    deep_update(a, y, True)
    assert a == {"t": {"a": 1, "b": 2, "c": 3}}
    assert x == {"t": {"a": -1, "b": 2, "c": -3}}
    assert y == {"t": {"a": 1, "c": 3}}


class TestDeduplicateNames:
    def test_empty_list_returns_empty_list(self):
        assert deduplicate_names([]) == []

    def test_single_name_is_unchanged(self):
        assert deduplicate_names(["job_test"]) == ["job_test"]

    def test_all_unique_names_are_unchanged(self):
        names = ["job_a", "job_b", "job_c"]
        assert deduplicate_names(names) == ["job_a", "job_b", "job_c"]

    def test_recompute_after_appending_extends_suffixes_without_recollision(self):
        raw_names = ["job_test", "job_test"]
        assert deduplicate_names(raw_names) == ["job_test_1", "job_test_2"]

        raw_names.append("job_test")
        assert deduplicate_names(raw_names) == ["job_test_1", "job_test_2", "job_test_3"]

        raw_names.append("job_test")
        assert deduplicate_names(raw_names) == [
            "job_test_1",
            "job_test_2",
            "job_test_3",
            "job_test_4",
        ]

    def test_unique_name_that_collides_with_a_suffixed_name_is_left_unchanged(self):
        names = ["job_test", "job_test", "job_test_1"]
        with pytest.raises(ValueError, match="job_test_1"):
            deduplicate_names(names)

    def test_does_not_mutate_input_sequence(self):
        names = ["job_test", "job_test"]
        original = list(names)
        deduplicate_names(names)
        assert names == original

    def test_returns_new_list_not_same_object(self):
        names = ["job_a", "job_b"]
        result = deduplicate_names(names)
        assert result is not names

    def test_accepts_any_sequence_not_just_list(self):
        assert deduplicate_names(("job_test", "job_test")) == ["job_test_1", "job_test_2"]

    def test_two_duplicates_get_suffixed_in_order(self):
        names = ["job_test", "job_test"]
        assert deduplicate_names(names) == ["job_test_1", "job_test_2"]

    @pytest.mark.parametrize(
        "names, expected",
        [
            ([], []),
            (["a"], ["a"]),
            (["a", "a"], ["a_1", "a_2"]),
            (["a", "a", "a"], ["a_1", "a_2", "a_3"]),
            (["a", "b", "a"], ["a_1", "b", "a_2"]),
            (["a", "b", "a", "b", "b"], ["a_1", "b_1", "a_2", "b_2", "b_3"]),
        ],
    )
    def test_parametrized_cases(self, names, expected):
        assert deduplicate_names(names) == expected
