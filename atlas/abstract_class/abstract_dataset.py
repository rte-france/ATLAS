"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements AbstractDataset
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from atlas import BusinessModel
from atlas.abstract_class.abstract_parameters import module_parameters_type_var


class AbstractDataset(ABC, Generic[module_parameters_type_var]):
    """Placeholder abstract class for input datasets."""

    @abstractmethod
    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        """Get the list of Business model class present in this Dataset"""


input_dataset_type_var = TypeVar("input_dataset_type_var", bound=AbstractDataset)
output_dataset_type_var = TypeVar("output_dataset_type_var", bound=AbstractDataset)
