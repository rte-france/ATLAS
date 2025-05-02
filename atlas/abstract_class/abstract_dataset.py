"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements AbstractDataset
"""

from abc import ABC, abstractmethod

from atlas import BusinessModel


class AbstractDataset(ABC):
    """Placeholder abstract class for input datasets."""

    @abstractmethod
    def get_business_model_class_used(self) -> list[BusinessModel]:
        """Get the list of Business model class present in this Dataset"""
