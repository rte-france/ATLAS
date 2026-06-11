"""
Tests for AbstractScenarioMatrix and AbstractTimeseries base classes.
These tests ensure that the abstract class properties and methods are properly covered.
"""

import pandas as pd
import pendulum
import polars as pl
import pytest

from atlas.core.math.lazy_timeseries import LazyTimeseries
from atlas.core.math.timeseries import Timeseries


class TestAbstractTimeseries:
    """Test AbstractTimeseries properties and methods via Timeseries."""

    @pytest.fixture
    def sample_timeseries(self):
        df = pd.DataFrame(
            {
                "time": pd.date_range(start="2025-01-01", periods=5, freq="D", tz="UTC"),
                "value": [1.0, 2.0, 3.0, 4.0, 5.0],
            }
        )
        return Timeseries(pl.from_pandas(df))

    @pytest.fixture
    def sample_lazy_timeseries(self, sample_timeseries):
        return LazyTimeseries(sample_timeseries.timeseries.lazy())

    def test_abs_method_inplace(self, sample_timeseries):
        """Test that abs() method works with inplace=True."""
        df_with_negatives = pd.DataFrame(
            {
                "time": pd.date_range(start="2025-01-01", periods=5, freq="D", tz="UTC"),
                "value": [-1.0, 2.0, -3.0, 4.0, -5.0],
            }
        )
        ts = Timeseries(pl.from_pandas(df_with_negatives))
        result = ts.abs(inplace=True)

        assert result is ts  # inplace should return self
        assert all(ts.timeseries["value"] >= 0)
        assert ts.values == [1.0, 2.0, 3.0, 4.0, 5.0]

    def test_abs_method_not_inplace(self, sample_timeseries):
        """Test that abs() method works with inplace=False."""
        df_with_negatives = pd.DataFrame(
            {
                "time": pd.date_range(start="2025-01-01", periods=5, freq="D", tz="UTC"),
                "value": [-1.0, 2.0, -3.0, 4.0, -5.0],
            }
        )
        ts = Timeseries(pl.from_pandas(df_with_negatives))
        result = ts.abs(inplace=False)

        assert result is not ts  # not inplace should return new instance
        # Original should be unchanged
        assert ts.values == [-1.0, 2.0, -3.0, 4.0, -5.0]
        # Result should have absolute values
        assert result.values == [1.0, 2.0, 3.0, 4.0, 5.0]

    def test_round_method_inplace(self, sample_timeseries):
        """Test that round() method works with inplace=True."""
        df_with_decimals = pd.DataFrame(
            {
                "time": pd.date_range(start="2025-01-01", periods=5, freq="D", tz="UTC"),
                "value": [1.234, 2.567, 3.891, 4.123, 5.789],
            }
        )
        ts = Timeseries(pl.from_pandas(df_with_decimals))
        result = ts.round(rounding_precision=1, inplace=True)

        assert result is ts
        assert ts.values == [1.2, 2.6, 3.9, 4.1, 5.8]

    def test_round_method_not_inplace(self, sample_timeseries):
        """Test that round() method works with inplace=False."""
        df_with_decimals = pd.DataFrame(
            {
                "time": pd.date_range(start="2025-01-01", periods=5, freq="D", tz="UTC"),
                "value": [1.234, 2.567, 3.891, 4.123, 5.789],
            }
        )
        ts = Timeseries(pl.from_pandas(df_with_decimals))
        result = ts.round(rounding_precision=1, inplace=False)

        assert result is not ts
        # Original unchanged
        assert ts.values == [1.234, 2.567, 3.891, 4.123, 5.789]
        # Result rounded
        assert result.values == [1.2, 2.6, 3.9, 4.1, 5.8]

    def test_lazy_abs_method(self, sample_lazy_timeseries):
        """Test that abs() method works on LazyTimeseries."""
        df_with_negatives = pd.DataFrame(
            {
                "time": pd.date_range(start="2025-01-01", periods=5, freq="D", tz="UTC"),
                "value": [-1.0, 2.0, -3.0, 4.0, -5.0],
            }
        )
        lazy_ts = LazyTimeseries(pl.from_pandas(df_with_negatives).lazy())
        result = lazy_ts.abs(inplace=False)

        # Collect to check values
        collected = result.collect()
        assert all(collected.timeseries["value"] >= 0)
        assert collected.values == [1.0, 2.0, 3.0, 4.0, 5.0]

    def test_lazy_round_method(self, sample_lazy_timeseries):
        """Test that round() method works on LazyTimeseries."""
        df_with_decimals = pd.DataFrame(
            {
                "time": pd.date_range(start="2025-01-01", periods=5, freq="D", tz="UTC"),
                "value": [1.234, 2.567, 3.891, 4.123, 5.789],
            }
        )
        lazy_ts = LazyTimeseries(pl.from_pandas(df_with_decimals).lazy())
        result = lazy_ts.round(rounding_precision=1, inplace=False)

        # Collect to check values
        collected = result.collect()
        assert collected.values == [1.2, 2.6, 3.9, 4.1, 5.8]


class TestClip:
    """Tests for the clip() method on Timeseries."""

    @pytest.fixture
    def ts(self):
        df = pd.DataFrame(
            {
                "time": pd.date_range(start="2025-01-01", periods=5, freq="h", tz="UTC"),
                "value": [-10.0, 0.0, 5.0, 15.0, 25.0],
            }
        )
        return Timeseries(pl.from_pandas(df))

    def test_clip_lower_bound(self, ts):
        result = ts.clip(lower_bound=0.0, inplace=False)
        assert result.values == [0.0, 0.0, 5.0, 15.0, 25.0]

    def test_clip_upper_bound(self, ts):
        result = ts.clip(upper_bound=10.0, inplace=False)
        assert result.values == [-10.0, 0.0, 5.0, 10.0, 10.0]

    def test_clip_both_bounds(self, ts):
        result = ts.clip(lower_bound=0.0, upper_bound=10.0, inplace=False)
        assert result.values == [0.0, 0.0, 5.0, 10.0, 10.0]

    def test_clip_no_bounds_is_noop(self, ts):
        result = ts.clip(inplace=False)
        assert result.values == ts.values

    def test_clip_inplace_true(self, ts):
        result = ts.clip(lower_bound=0.0, upper_bound=10.0, inplace=True)
        assert result is ts
        assert ts.values == [0.0, 0.0, 5.0, 10.0, 10.0]

    def test_clip_inplace_false_does_not_mutate_original(self, ts):
        original_values = ts.values[:]
        ts.clip(lower_bound=0.0, upper_bound=10.0, inplace=False)
        assert ts.values == original_values

    def test_clip_lazy_timeseries(self, ts):
        lazy_ts = LazyTimeseries(ts.timeseries.lazy())
        result = lazy_ts.clip(lower_bound=0.0, upper_bound=10.0, inplace=False)
        assert result.collect().values == [0.0, 0.0, 5.0, 10.0, 10.0]

    def test_clip_pointwise_with_timeseries_bounds(self, ts):
        df = pd.DataFrame(
            {
                "time": pd.date_range(start="2025-01-01", periods=5, freq="h", tz="UTC"),
                "value": [0.0, 0.0, 6.0, 6.0, 20.0],
            }
        )
        upper = Timeseries(pl.from_pandas(df))
        result = ts.clip(upper_bound=upper, inplace=False)
        assert result.values == [-10.0, 0.0, 5.0, 6.0, 20.0]

    def test_clip_with_sparser_bound_leaves_unmatched_rows_unclipped(self, ts):
        # Bound covers only the first 3 timestamps
        df = pd.DataFrame(
            {
                "time": pd.date_range(start="2025-01-01", periods=3, freq="h", tz="UTC"),
                "value": [-5.0, -5.0, -5.0],
            }
        )
        lower = Timeseries(pl.from_pandas(df))
        result = ts.clip(lower_bound=lower, inplace=False)
        # Last two rows have null bound -> unclipped
        assert result.values == [-5.0, 0.0, 5.0, 15.0, 25.0]

    def test_clip_pointwise_lazy(self, ts):
        df = pd.DataFrame(
            {
                "time": pd.date_range(start="2025-01-01", periods=5, freq="h", tz="UTC"),
                "value": [100.0, 100.0, 4.0, 4.0, 4.0],
            }
        )
        upper = Timeseries(pl.from_pandas(df))
        lazy_ts = LazyTimeseries(ts.timeseries.lazy())
        result = lazy_ts.clip(upper_bound=upper, inplace=False)
        assert result.collect().values == [-10.0, 0.0, 4.0, 4.0, 4.0]


class TestReindex:
    """Tests for the reindex() method."""

    @pytest.fixture
    def sparse_ts(self):
        df = pd.DataFrame(
            {
                "time": pd.to_datetime(["2025-01-01 00:00", "2025-01-01 02:00"], utc=True),
                "value": [10.0, 20.0],
            }
        )
        return Timeseries(pl.from_pandas(df))

    def test_reindex_with_list_fills_missing(self, sparse_ts):
        target = [
            pendulum.datetime(2025, 1, 1, 0),
            pendulum.datetime(2025, 1, 1, 1),
            pendulum.datetime(2025, 1, 1, 2),
        ]
        result = sparse_ts.reindex(target, default=-1.0, inplace=False)
        assert result.values == [10.0, -1.0, 20.0]
        assert len(result) == 3

    def test_reindex_drops_rows_not_in_target(self, sparse_ts):
        target = [pendulum.datetime(2025, 1, 1, 0)]
        result = sparse_ts.reindex(target, default=0.0, inplace=False)
        assert result.values == [10.0]
        assert len(result) == 1

    def test_reindex_default_zero(self, sparse_ts):
        target = [pendulum.datetime(2025, 1, 1, 1)]
        result = sparse_ts.reindex(target, inplace=False)
        assert result.values == [0.0]

    def test_reindex_with_string_dates(self, sparse_ts):
        result = sparse_ts.reindex(
            ["2025-01-01 00:00:00", "2025-01-01 01:00:00", "2025-01-01 02:00:00"],
            default=-1.0,
            inplace=False,
        )
        assert result.values == [10.0, -1.0, 20.0]

    def test_reindex_with_other_timeseries(self, sparse_ts):
        target_df = pd.DataFrame(
            {
                "time": pd.date_range(start="2025-01-01", periods=4, freq="h", tz="UTC"),
                "value": [0.0, 0.0, 0.0, 0.0],
            }
        )
        target = Timeseries(pl.from_pandas(target_df))
        result = sparse_ts.reindex(target, default=-1.0, inplace=False)
        assert result.values == [10.0, -1.0, 20.0, -1.0]

    def test_reindex_inplace(self, sparse_ts):
        target = [
            pendulum.datetime(2025, 1, 1, 0),
            pendulum.datetime(2025, 1, 1, 1),
            pendulum.datetime(2025, 1, 1, 2),
        ]
        result = sparse_ts.reindex(target, default=0.0, inplace=True)
        assert result is sparse_ts
        assert sparse_ts.values == [10.0, 0.0, 20.0]

    def test_reindex_lazy(self, sparse_ts):
        lazy_ts = LazyTimeseries(sparse_ts.timeseries.lazy())
        target = [
            pendulum.datetime(2025, 1, 1, 0),
            pendulum.datetime(2025, 1, 1, 1),
            pendulum.datetime(2025, 1, 1, 2),
        ]
        result = lazy_ts.reindex(target, default=-1.0, inplace=False)
        assert result.collect().values == [10.0, -1.0, 20.0]


class TestLookupDictCache:
    """Unit tests for the _lookup_cache mechanism on Timeseries."""

    @pytest.fixture
    def ts(self):
        df = pd.DataFrame(
            {
                "time": pd.date_range(start="2025-01-01", periods=4, freq="h", tz="UTC"),
                "value": [10.0, 20.0, 30.0, 40.0],
            }
        )
        return Timeseries(pl.from_pandas(df))

    def test_cache_is_none_before_first_access(self, ts):
        assert ts._lookup_cache is None

    def test_cache_is_built_on_first_get_lookup(self, ts):
        ts._get_lookup()
        assert ts._lookup_cache is not None

    def test_cache_contains_correct_mapping(self, ts):
        lookup = ts._get_lookup()
        assert len(lookup) == 4
        assert list(lookup.values()) == [10.0, 20.0, 30.0, 40.0]

    def test_to_lookup_dict_returns_same_object_as_cache(self, ts):
        d = ts.to_lookup_dict()
        assert d is ts._lookup_cache

    def test_cache_is_reused_on_repeated_calls(self, ts):
        first = ts._get_lookup()
        second = ts._get_lookup()
        assert first is second

    def test_cache_allows_o1_lookup_via_get_value(self, ts):
        dt = pendulum.datetime(2025, 1, 1, 1, 0, 0, tz="UTC")
        assert ts.get_value(dt) == 20.0

    def test_invalidate_cache_sets_none(self, ts):
        ts._get_lookup()
        ts._invalidate_cache()
        assert ts._lookup_cache is None

    def test_cache_rebuilt_after_invalidation(self, ts):
        first = ts._get_lookup()
        ts._invalidate_cache()
        second = ts._get_lookup()
        assert second is not first
        assert list(second.values()) == [10.0, 20.0, 30.0, 40.0]

    def test_cache_invalidated_after_set_value(self, ts):
        ts._get_lookup()
        dt = pendulum.datetime(2025, 1, 1, 0, 0, 0, tz="UTC")
        ts.set_value(dt, 99.0, inplace=True)
        assert ts._lookup_cache is None
        assert ts.get_value(dt) == 99.0

    def test_cache_reflects_new_value_after_set_value(self, ts):
        dt = pendulum.datetime(2025, 1, 1, 2, 0, 0, tz="UTC")
        ts.set_value(dt, 99.0, inplace=True)
        assert ts.to_lookup_dict()[dt] == 99.0

    def test_cache_invalidated_after_add_index(self, ts):
        ts._get_lookup()
        new_dt = pendulum.datetime(2025, 1, 1, 4, 0, 0, tz="UTC")
        ts.add_index(new_dt, 50.0, inplace=True)
        assert ts._lookup_cache is None
        assert ts.get_value(new_dt) == 50.0

    def test_cache_invalidated_after_set_timezone(self, ts):
        ts._get_lookup()
        ts.set_timezone("Europe/Paris")
        assert ts._lookup_cache is None

    def test_cache_rebuilt_with_correct_tz_after_set_timezone(self, ts):
        ts.set_timezone("Europe/Paris")
        lookup = ts.to_lookup_dict()
        keys = list(lookup.keys())
        assert all(str(k.tzinfo) == "Europe/Paris" for k in keys)

    def test_non_inplace_mutation_does_not_invalidate_original_cache(self, ts):
        ts._get_lookup()
        cache_before = ts._lookup_cache
        dt = pendulum.datetime(2025, 1, 1, 0, 0, 0, tz="UTC")
        new_ts = ts.set_value(dt, 99.0, inplace=False)
        assert ts._lookup_cache is cache_before
        assert new_ts._lookup_cache is None
