"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pytest

from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.models.business_model import BusinessModel


# Concrete subclass of AbstractDataset for testing
class ConcreteDataset(AbstractDataset):
    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return [BusinessModel]


def test_abstract_dataset_cannot_be_instantiated():
    with pytest.raises(TypeError):
        AbstractDataset()  # Should raise TypeError due to abstract method


def test_concrete_dataset_returns_expected_business_model():
    dataset = ConcreteDataset()
    result = dataset.get_business_model_class_used()
    assert isinstance(result, list)
    assert BusinessModel in result
