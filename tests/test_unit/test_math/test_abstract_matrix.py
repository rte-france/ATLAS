# test_abstract_classes.py
"""
Tests for AbstractScenarioMatrix and AbstractTimeseries base classes.
These tests ensure that the abstract class properties and methods are properly covered.
"""

import pandas as pd
import polars as pl
import pytest

from atlas.math.lazy_matrix import LazyScenarioMatrix
from atlas.math.matrix import ScenarioMatrix


class TestAbstractScenarioMatrix:
    """Test AbstractScenarioMatrix properties and methods via ScenarioMatrix."""

    @pytest.fixture
    def sample_matrix(self):
        df = pd.DataFrame(
            {
                "time": pd.date_range(start="2025-01-01", periods=3, freq="D", tz="UTC"),
                "scenario1": [1.0, 2.0, 3.0],
                "scenario2": [4.0, 5.0, 6.0],
            }
        )
        return ScenarioMatrix(pl.from_pandas(df))

    @pytest.fixture
    def sample_lazy_matrix(self, sample_matrix):
        return LazyScenarioMatrix(sample_matrix.matrix.lazy())

    def test_shape_property(self, sample_matrix):
        """Test that .shape property works correctly."""
        shape = sample_matrix.shape
        assert shape == (3, 3)  # 3 rows, 3 columns (time + scenario1 + scenario2)
        assert isinstance(shape, tuple)
        assert len(shape) == 2

    def test_index_property(self, sample_matrix):
        """Test that .index property works correctly."""
        index = sample_matrix.index
        assert index == ["scenario1", "scenario2"]
        assert isinstance(index, list)
        assert len(index) == 2

    def test_abs_method_inplace(self, sample_matrix):
        """Test that abs() method works with inplace=True."""
        # Add negative values
        df_with_negatives = pd.DataFrame(
            {
                "time": pd.date_range(start="2025-01-01", periods=3, freq="D", tz="UTC"),
                "scenario1": [-1.0, 2.0, -3.0],
                "scenario2": [4.0, -5.0, 6.0],
            }
        )
        matrix = ScenarioMatrix(pl.from_pandas(df_with_negatives))
        result = matrix.abs(inplace=True)

        assert result is matrix  # inplace should return self
        assert all(matrix.matrix["scenario1"] >= 0)
        assert all(matrix.matrix["scenario2"] >= 0)
        assert matrix.matrix["scenario1"].to_list() == [1.0, 2.0, 3.0]
        assert matrix.matrix["scenario2"].to_list() == [4.0, 5.0, 6.0]

    def test_abs_method_not_inplace(self, sample_matrix):
        """Test that abs() method works with inplace=False."""
        df_with_negatives = pd.DataFrame(
            {
                "time": pd.date_range(start="2025-01-01", periods=3, freq="D", tz="UTC"),
                "scenario1": [-1.0, 2.0, -3.0],
                "scenario2": [4.0, -5.0, 6.0],
            }
        )
        matrix = ScenarioMatrix(pl.from_pandas(df_with_negatives))
        result = matrix.abs(inplace=False)

        assert result is not matrix  # not inplace should return new instance
        # Original should be unchanged
        assert matrix.matrix["scenario1"].to_list() == [-1.0, 2.0, -3.0]
        # Result should have absolute values
        assert result.matrix["scenario1"].to_list() == [1.0, 2.0, 3.0]
        assert result.matrix["scenario2"].to_list() == [4.0, 5.0, 6.0]

    def test_lazy_shape_property(self, sample_lazy_matrix):
        """Test that .shape property works on LazyScenarioMatrix."""
        shape = sample_lazy_matrix.shape
        assert shape == (3, 3)  # 3 rows, 3 columns (time + scenario1 + scenario2)
        assert isinstance(shape, tuple)

    def test_lazy_index_property(self, sample_lazy_matrix):
        """Test that .index property works on LazyScenarioMatrix."""
        index = sample_lazy_matrix.index
        assert index == ["scenario1", "scenario2"]
        assert isinstance(index, list)

    def test_lazy_abs_method(self, sample_lazy_matrix):
        """Test that abs() method works on LazyScenarioMatrix."""
        df_with_negatives = pd.DataFrame(
            {
                "time": pd.date_range(start="2025-01-01", periods=3, freq="D", tz="UTC"),
                "scenario1": [-1.0, 2.0, -3.0],
                "scenario2": [4.0, -5.0, 6.0],
            }
        )
        lazy_matrix = LazyScenarioMatrix(pl.from_pandas(df_with_negatives).lazy())
        result = lazy_matrix.abs(inplace=False)

        # Collect to check values
        collected = result.collect()
        assert all(collected.matrix["scenario1"] >= 0)
        assert all(collected.matrix["scenario2"] >= 0)
