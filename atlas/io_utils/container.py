"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from collections.abc import Iterable
from typing import Generic, TypeVar

from atlas.models.business_model import BusinessModel

T = TypeVar("T", bound=BusinessModel)


class Container(Generic[T]):
    def __init__(self, items: Iterable[T] | None = None):
        # Dict is not used in case of set on name
        self._items: list[T] = list(items) if items else []

    def add(self, item: T) -> None:
        self._items.append(item)

    def get(self, name: str) -> T:
        for item in self._items:
            if item.name == name:
                return item
        raise KeyError(f"{name} not found")

    def remove(self, name: str) -> None:
        self._items = [i for i in self._items if i.name != name]

    def all(self) -> list[T]:
        return self._items

    def clear(self) -> None:
        """Remove all items from the container."""
        self._items.clear()

    def is_empty(self) -> bool:
        """Return True if the container has no items."""
        return len(self._items) == 0

    def __len__(self):
        return len(self._items)

    def __iter__(self):
        return iter(self._items)

    def __bool__(self) -> bool:
        """Return True if the container has any items."""
        return len(self._items) > 0
