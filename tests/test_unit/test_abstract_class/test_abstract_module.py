"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Test AbstractModule
"""

import pytest
from typing import Any

from atlas import BusinessModel, Load
from atlas.abstract_class.abstract_module import AbstractModule
from tests.test_unit.test_abstract_class.test_abstract_dataset import InputDatasetTest, OutputDatasetTest
from tests.test_unit.test_abstract_class.test_abstract_parameters import ParametersTest, raw_params, parameters


class ModuleTest(AbstractModule[ParametersTest, InputDatasetTest, OutputDatasetTest]):
    def __init__(self):
        pass

    def create_parameters(self, raw_params: dict[str, Any]) -> ParametersTest:
        return ParametersTest(**raw_params)

    def import_data(self, raw_data: dict[str, list[BusinessModel]], parameters: ParametersTest) -> InputDatasetTest:
        return InputDatasetTest(raw_data, parameters)

    def validate_data(self, parameters: ParametersTest, input_dataset: InputDatasetTest) -> bool:
        if len(input_dataset.loads) > 1:
            return False
        return True

    def execute(self, parameters: ParametersTest, input_dataset: InputDatasetTest) -> OutputDatasetTest:
        return OutputDatasetTest(input_dataset, parameters)

    def validates_results(
        self, parameters: ParametersTest, input_dataset: InputDatasetTest, output_dataset: OutputDatasetTest
    ) -> bool:
        if parameters.valid_result:
            return True
        else:
            return False

    def export_results(
        self, parameters: ParametersTest, input_dataset: InputDatasetTest, output_dataset: OutputDatasetTest
    ) -> None:
        print("Export of results")


@pytest.fixture()
def raw_data() -> dict[str, list[BusinessModel]]:
    return {"Load": [Load()]}


@pytest.fixture
def input_dataset(parameters: ParametersTest, raw_data: dict[str, list[BusinessModel]]) -> InputDatasetTest:
    return InputDatasetTest(raw_data, parameters)


@pytest.fixture
def input_dataset_with_two_loads(parameters: ParametersTest) -> InputDatasetTest:
    return InputDatasetTest({"Load": [Load(), Load()]}, parameters)


@pytest.fixture
def output_dataset(parameters: ParametersTest, input_dataset: InputDatasetTest) -> OutputDatasetTest:
    return OutputDatasetTest(input_dataset, parameters)


def test_validate_data_is_true(parameters: ParametersTest, input_dataset: InputDatasetTest):
    assert ModuleTest().validate_data(parameters, input_dataset)


def test_validate_data_is_false(parameters: ParametersTest, input_dataset_with_two_loads: InputDatasetTest):
    assert not ModuleTest().validate_data(parameters, input_dataset_with_two_loads)


def test_validate_results_is_true(
    parameters: ParametersTest, input_dataset: InputDatasetTest, output_dataset: OutputDatasetTest
):
    assert ModuleTest().validates_results(parameters, input_dataset, output_dataset)


def test_validate_results_is_false(
    parameters: ParametersTest, input_dataset: InputDatasetTest, output_dataset: OutputDatasetTest
):
    parameters.valid_result = False
    assert not ModuleTest().validates_results(parameters, input_dataset, output_dataset)


def test_assertion_error_if_validate_data_is_false(raw_params: dict[str, Any]):
    raw_data = {"Load": [Load(), Load()]}
    with pytest.raises(AssertionError, match="Input*"):
        ModuleTest().run(raw_data, raw_params)


def test_assertion_error_if_validate_result_is_false(raw_data: dict[str, Any], raw_params: dict[str, Any]):
    raw_params["valid_result"] = False
    with pytest.raises(AssertionError, match="Results*"):
        ModuleTest().run(raw_data, raw_params)
