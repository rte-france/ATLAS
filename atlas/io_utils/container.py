"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from collections.abc import Iterable, Iterator
from typing import ClassVar, Generic, TypeVar

from atlas.models.business_model import BusinessModel

T = TypeVar("T", bound=BusinessModel)


class Container(Generic[T]):
    item_type: ClassVar[type[BusinessModel]] = BusinessModel

    def __init__(self, items: Iterable[T] | None = None):
        self._items: dict[str, T] = {}

        if items:
            for item in items:
                self.add(item)

    def add(self, item: T) -> None:
        if not isinstance(item, self.item_type):
            raise TypeError(f"Expected {self.item_type.__name__}, got {type(item).__name__}")
        if item.name in self._items:
            raise ValueError(f"Item with name '{item.name}' already exists")
        self._items[item.name] = item

    def get(self, name: str) -> T:
        try:
            return self._items[name]
        except KeyError:
            raise KeyError(f"'{name}' not found") from None

    def remove(self, name: str) -> None:
        self._items.pop(name, None)

    def all(self) -> list[T]:
        return list(self._items.values())

    def clear(self) -> None:
        """Remove all items from the container."""
        self._items.clear()

    def is_empty(self) -> bool:
        """Return True if the container has no items."""
        return not self._items

    def __len__(self) -> int:
        """Return The size of the container."""
        return len(self._items)

    def __iter__(self) -> Iterator[T]:
        return iter(self._items.values())

    def __bool__(self) -> bool:
        """Return True if the container has any items."""
        return bool(self._items)

    def __contains__(self, item: object) -> bool:
        """
        Support 'in' operator:
        - If item is str → check if key exists
        - If item is BusinessModel → check if item.name exists
        """
        if isinstance(item, str):
            return item in self._items
        elif isinstance(item, BusinessModel):
            return item.name in self._items
        return False
