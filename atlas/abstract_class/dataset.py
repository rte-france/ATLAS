"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements AbstractDataset
"""

from abc import ABC, abstractmethod

from atlas.orchestrator.change_set import ChangeSet


class AbstractDataset[P](ABC):  # noqa: B024
    """Placeholder abstract class for input datasets."""


class ModuleResult[P](AbstractDataset[P]):
    """In-memory object a module returns, carrying the change sets it produced."""

    change_sets: list[ChangeSet] = []

    @abstractmethod
    def build_change_sets(self) -> None:
        """Populate self.change_sets with the ChangeSet objects produced by this module."""
