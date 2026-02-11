# test_abstract_classes.py
"""
Tests for AbstractScenarioMatrix and AbstractTimeseries base classes.
These tests ensure that the abstract class properties and methods are properly covered.
"""

import pandas as pd
import polars as pl
import pytest

from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries


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
