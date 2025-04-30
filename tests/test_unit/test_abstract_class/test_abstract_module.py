from typing import Any

from atlas.abstract_class.abstract_module import AbstractModule
from tests.test_unit.test_abstract_class.test_abstract_dataset import InputDatasetTest, OutputDatasetTest
from tests.test_unit.test_abstract_class.test_abstract_parameters import ParametersTest


class ModuleTest(AbstractModule):
    def create_parameters(self, raw_params: dict[str, Any]) -> ParametersTest:
        pass

    def import_data(self, raw_data: str, parameters: ParametersTest) -> InputDatasetTest:
        pass

    def validate_data(self, parameters: ParametersTest, input_dataset: InputDatasetTest) -> bool:
        pass

    def execute(self, parameters: ParametersTest, input_dataset: InputDatasetTest) -> OutputDatasetTest:
        pass

    def validates_results(
        self, parameters: ParametersTest, input_dataset: InputDatasetTest, output_dataset: OutputDatasetTest
    ) -> bool:
        pass

    def export_results(
        self, parameters: ParametersTest, input_dataset: InputDatasetTest, output_dataset: OutputDatasetTest
    ) -> None:
        pass
