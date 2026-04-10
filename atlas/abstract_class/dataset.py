"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements AbstractDataset
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from atlas.abstract_class.parameters import P
from atlas.orchestrator.change_set import ChangeSet


class AbstractDataset(ABC, Generic[P]):
    """Placeholder abstract class for input datasets."""

    pass


class AbstractModuleOutput(AbstractDataset[P]):
    change_sets: list[ChangeSet] = []

    @abstractmethod
    def build_change_sets(self) -> None:
        """Populate self.change_sets with the ChangeSet objects produced by this module."""


ID = TypeVar("ID", bound=AbstractDataset)
OD = TypeVar("OD", bound=AbstractModuleOutput)
