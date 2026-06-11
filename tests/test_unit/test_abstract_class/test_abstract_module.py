"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Test AbstractModule
"""

from unittest.mock import Mock

from atlas import BusinessModel
from atlas.abstract_class.dataset import ID, OD
from atlas.abstract_class.module import AbstractModule
from atlas.abstract_class.parameters import P


class ModuleTest(AbstractModule[P, ID, OD]):
    def __init__(self):
        pass

    def get_parameters_class(self) -> type[P]:
        return Mock

    def import_data(self, raw_data: dict[str, list[BusinessModel]], parameters: P) -> ID:
        return Mock()

    def validate_data(self, parameters: P, input_dataset: ID) -> bool:
        if len(input_dataset.loads) > 1:
            return False
        return True

    def execute(self, parameters: P, input_dataset: ID) -> OD:
        return Mock()

    def validates_results(
        self,
        parameters: P,
        input_dataset: ID,
        output_dataset: OD,
    ) -> bool:
        if parameters.valid_result:
            return True
        return False

    def export_results(
        self,
        parameters: P,
        input_dataset: ID,
        output_dataset: OD,
    ) -> None:
        print("Export of results")


def test_validate_data_is_true():
    valid_input_dataset = Mock()
    valid_input_dataset.loads = [1]
    assert ModuleTest().validate_data(Mock(), valid_input_dataset)


def test_validate_data_is_false():
    invalid_input_dataset = Mock()
    invalid_input_dataset.loads = [1, 2]
    assert not ModuleTest().validate_data(Mock(), invalid_input_dataset)


def test_validate_results_is_true():
    valid_result_parameters = Mock()
    valid_result_parameters.valid_result = True
    assert ModuleTest().validates_results(valid_result_parameters, Mock(), Mock())


def test_validate_results_is_false():
    invalid_result_parameters = Mock()
    invalid_result_parameters.valid_result = False
    assert not ModuleTest().validates_results(invalid_result_parameters, Mock(), Mock())
