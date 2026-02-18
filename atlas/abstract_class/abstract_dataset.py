"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements AbstractDataset
"""

from abc import ABC
from typing import Generic, TypeVar

from atlas.abstract_class.abstract_parameters import P
from atlas.workflow.change_set import ChangeSet


class AbstractDataset(ABC, Generic[P]):
    """Placeholder abstract class for input datasets."""

    pass


class AbstractModuleOutput(AbstractDataset[P]):
    def __init__(self):
        self.change_sets: list[ChangeSet] = []


ID = TypeVar("ID", bound=AbstractDataset)
OD = TypeVar("OD", bound=AbstractDataset)
