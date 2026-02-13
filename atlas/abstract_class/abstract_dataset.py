"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements AbstractDataset
"""

from abc import ABC
from typing import Generic, TypeVar

from atlas.abstract_class.abstract_parameters import module_parameters_type_var
from atlas.workflow.change_set import ChangeSet


class AbstractDataset(ABC, Generic[module_parameters_type_var]):
    """Placeholder abstract class for input datasets."""

    pass


class AbstractModuleOutput(AbstractDataset[module_parameters_type_var]):
    def __init__(self):
        self.change_sets: list[ChangeSet] = []


input_dataset_type_var = TypeVar("input_dataset_type_var", bound=AbstractDataset)
output_dataset_type_var = TypeVar("output_dataset_type_var", bound=AbstractDataset)
