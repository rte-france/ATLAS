"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

This module provides AbstractScenarioMatrix base class for ScenarioMatrix and LazyScenarioMatrix.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import timedelta
from pathlib import Path
from typing import Any, Generic, Literal, Self, TypeVar

import pendulum
import plotly.graph_objects as go
import polars as pl

TBackend = TypeVar("TBackend", pl.DataFrame, pl.LazyFrame)


class AbstractScenarioMatrix(ABC, Generic[TBackend]):
    """
    Abstract base class for ScenarioMatrix implementations.

    Provides shared interface and implementation for both eager (ScenarioMatrix)
    and lazy (LazyScenarioMatrix) scenario matrix classes.
    """

    timezone: str
    indexes: list[str]

    @abstractmethod
    def _get_data(self) -> TBackend:
        """Return the underlying DataFrame or LazyFrame."""
        ...

    @abstractmethod
    def _return(self, data: TBackend, inplace: bool) -> Self:
        """Wrap data into appropriate type (ScenarioMatrix or LazyScenarioMatrix)."""
        ...

    @abstractmethod
    def _get_shape(self) -> tuple[int, int]:
        """Return (rows, columns) of the underlying data."""
        ...

    @abstractmethod
    def _get_indexes(self) -> list[str]:
        """Get the indexes of the matrix."""
        ...

    @classmethod
    @abstractmethod
    def from_file(
        cls,
        file_path: str | Path,
        timezone: str = "UTC",
        filters: tuple[str, str] | None = None,
        separator: str = ";",
    ) -> Self:
        """Load a ScenarioMatrix from a file."""
        ...

    @property
    @abstractmethod
    def dataframe(self) -> pl.DataFrame | pl.LazyFrame:
        """Returns the underlying DataFrame or LazyFrame."""
        ...

    @property
    def shape(self) -> tuple[int, int]:
        """Returns the ScenarioMatrix shape."""
        return self._get_shape()

    @property
    def index(self) -> list[str]:
        """Returns the ScenarioMatrix indexes (e.g columns names)."""
        return self._get_indexes()

    @property
    @abstractmethod
    def metadata(self) -> dict[str, Any]:
        """Return the metadata of the matrix."""
        ...

    @abstractmethod
    def __len__(self) -> int:
        """Number of timeseries in the matrix."""
        ...

    @abstractmethod
    def __contains__(self, index: str) -> bool:
        """Check if an index exists in the matrix."""
        ...

    def abs(self, inplace: bool = True) -> Self:
        """Compute absolute value of all numeric columns."""
        backend = self._get_data()
        result = backend.select(["time"] + [pl.col(c).abs().alias(c) for c in self.index])
        return self._return(result, inplace)

    @abstractmethod
    def set_frequency(self, frequency: str | timedelta | pendulum.Duration, inplace: bool = True) -> Self:
        """Change the frequency (timestep) of all scenario time series."""
        ...

    @abstractmethod
    def to_file(
        self,
        path: str | Path,
        file_format: Literal["csv", "parquet", "pickle"] = "csv",
        separator: str = ";",
    ) -> None:
        """Export the matrix to a file."""
        ...

    @abstractmethod
    def to_file_with_attribute(
        self,
        path: str | Path,
        attribute: str,
        file_format: Literal["csv", "parquet", "pickle"] = "csv",
        separator: str = ";",
        concatenate: bool = True,
    ) -> None:
        """Export the matrix to a file with an attribute column."""
        ...

    @abstractmethod
    def __repr__(self) -> str:
        """Provide a string representation."""
        ...

    @abstractmethod
    def __eq__(self, other: object) -> bool:
        """Check equality with another matrix."""
        ...

    @abstractmethod
    def __getitem__(self, index: str) -> Any:
        """Get a timeseries by index."""
        ...

    @abstractmethod
    def select(self, index: str) -> Any:
        """Get a timeseries by index."""
        ...

    @abstractmethod
    def add(self, timeseries: Any, index: str) -> None:
        """Add a timeseries to the matrix."""
        ...

    @abstractmethod
    def delete(self, index: str) -> None:
        """Delete a timeseries by index."""
        ...

    @abstractmethod
    def replace(self, index: str, timeseries: Any) -> None:
        """Replace a Timeseries in the matrix."""
        ...

    @abstractmethod
    def get_matrix(self) -> TBackend:
        """Get the matrix data."""
        ...

    @abstractmethod
    def to_lazy(self) -> pl.LazyFrame:
        """Convert to LazyFrame representation."""
        ...

    @abstractmethod
    def plot(
        self,
        title: str = "ScenarioMatrix Timeseries Plot",
        height: int = 500,
        width: int = 800,
        show_grid: bool = True,
        line_shape: Literal["hv", "linear", "spline"] = "hv",
        template: str = "plotly_white",
    ) -> go.Figure:
        """Generate an interactive Plotly figure."""
        ...

    @abstractmethod
    def describe(self) -> dict[str, Any]:
        """Get metadata about the matrix."""
        ...
