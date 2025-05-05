"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Test AbstractDataset
"""

from typing import Type

from atlas import BusinessModel, Load, Wind
from atlas.abstract_class.abstract_dataset import AbstractDataset
from tests.test_unit.test_abstract_class.test_abstract_parameters import ParametersTest


class InputDatasetTest(AbstractDataset[ParametersTest]):
    def __init__(self, raw_data: dict[str, list[BusinessModel]], parameters: ParametersTest):
        self.raw_data = raw_data
        self.parameters = parameters
        self.loads = raw_data["Load"]

    def get_business_model_class_used(self) -> list[Type[BusinessModel]]:
        return [Load]


class OutputDatasetTest(AbstractDataset[ParametersTest]):
    def __init__(self, input_dataset: InputDatasetTest, parameters: ParametersTest):
        self.input_dataset = input_dataset
        self.parameters = parameters
        self.winds = []

    def get_business_model_class_used(self) -> list[Type[BusinessModel]]:
        return [Wind]

    def add_wind(self, wind: Wind):
        self.winds.append(wind)
