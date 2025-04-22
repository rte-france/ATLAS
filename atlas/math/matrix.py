"""
Copyright (c) 2016-2022, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements Matrix
"""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from atlas.math.timeseries import Timeseries

Index = TypeVar("Index", str, int, float, datetime)


class Matrix(Generic[Index]):
    """Base class for storing Timeseries objects indexed by scenario keys or datetimes."""

    def __init__(self, name: str, indexes: list[Index], timeseries: list[Timeseries]) -> None:
        """
        Initialize the matrix.

        :param name: The name of the matrix.
        :type name: str
        :param indexes: List of indexes (e.g., scenario names or datetimes).
        :type indexes: list[Index]
        :param timeseries: List of Timeseries corresponding to the indexes.
        :type timeseries: list[Timeseries]
        :raises ValueError: If the number of indexes and timeseries do not match.
        """
        if len(indexes) != len(timeseries):
            raise ValueError("Indexes and timeseries must have the same length.")

        self.name: str = name
        self.timeseries_map: dict[Index, Timeseries] = dict(zip(indexes, timeseries, strict=False))

    def __len__(self) -> int:
        """
        Number of timeseries in the matrix.

        :return: Number of elements in the matrix.
        :rtype: int
        """
        return len(self.timeseries_map)

    def __contains__(self, index: Index) -> bool:
        """
        Check if an index exists in the matrix.

        :param index: The index to check.
        :type index: Index
        :return: True if index exists, False otherwise.
        :rtype: bool
        """
        return index in self.timeseries_map

    def __getitem__(self, index: Index) -> Timeseries:
        """
        Get a timeseries by index.

        :param index: Index key.
        :type index: Index
        :raises KeyError: If the index is not found.
        :return: The Timeseries object.
        :rtype: Timeseries
        """
        if index not in self.timeseries_map:
            raise KeyError(f"No timeseries found for index: {index}")
        return self.timeseries_map[index]

    def __eq__(self, other: object) -> bool:
        """
        Check equality with another matrix.

        :param other: Another matrix instance.
        :type other: object
        :return: True if equal, False otherwise.
        :rtype: bool
        """
        if not isinstance(other, Matrix):
            raise NotImplementedError("Cannot compare with non-Matrix object")

        return (
            self.name == other.name
            and list(self.timeseries_map.keys()) == list(other.timeseries_map.keys())
            and all(self.timeseries_map[k] == other.timeseries_map[k] for k in self.timeseries_map)
        )

    def add_timeseries(self, index: Index, timeseries: Timeseries) -> None:
        """
        Add a timeseries to the matrix.

        :param index: Index key.
        :type index: Index
        :param timeseries: Timeseries to add.
        :type timeseries: Timeseries
        :raises TypeError: If types are invalid.
        """
        if not isinstance(timeseries, Timeseries):
            raise TypeError(f"Expected Timeseries, got {type(timeseries)}")

        self.timeseries_map[index] = timeseries

    def delete_timeseries(self, index: Index) -> None:
        """
        Delete a timeseries by index.

        :param index: Index key.
        :type index: Index
        :raises KeyError: If index is not found.
        """
        try:
            del self.timeseries_map[index]
        except KeyError:
            raise KeyError(f"No timeseries to delete at index: {index}")

    def get_timeseries(self, index: Index) -> Timeseries:
        """
        Retrieve a timeseries by index.

        :param index: Index key.
        :type index: Index
        :raises KeyError: If the index is not found.
        :return: The Timeseries object.
        :rtype: Timeseries
        """
        return self.__getitem__(index)

    @property
    def indexes(self) -> list[Index]:
        """
        Get the list of indexes.

        :return: List of index keys.
        :rtype: list[Index]
        """
        return list(self.timeseries_map.keys())
