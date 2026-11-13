"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import atlas.config as cfg
from atlas.abstract_class.module import AbstractModule
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.balancing_markets_tso_orders.input_dataset import TSOOrdersInputDataset
from atlas.modules.balancing_markets_tso_orders.parameters import TSOOrdersParameters
from atlas.modules.balancing_markets_tso_orders.result import TSOOrdersResult


class TSOOrdersModule(AbstractModule[TSOOrdersParameters, TSOOrdersInputDataset, TSOOrdersResult]):
    @classmethod
    def get_parameters_class(cls) -> type[TSOOrdersParameters]:
        return TSOOrdersParameters

    def import_data(self, input_data: AtlasDataset, parameters: TSOOrdersParameters) -> TSOOrdersInputDataset:
        """Imports data using business objects and parameters."""
        return TSOOrdersInputDataset(
            input_data.set_frequency_all(parameters.temporal.timestep, inplace=True), parameters
        )

    def validate_data(self, parameters: TSOOrdersParameters, input_dataset: TSOOrdersInputDataset) -> bool:
        """Validates imported or generated data."""
        return True

    def validates_results(
        self,
        parameters: TSOOrdersParameters,
        input_dataset: TSOOrdersInputDataset,
        result: TSOOrdersResult,
    ) -> bool:
        """Validates results"""
        return True

    def export_results(
        self,
        parameters: TSOOrdersParameters,
        input_dataset: TSOOrdersInputDataset,
        result: TSOOrdersResult,
    ) -> None:
        """Exports results."""
        pass

    def execute(self, parameters: TSOOrdersParameters, input_dataset: TSOOrdersInputDataset) -> TSOOrdersResult:
        cfg.logger.info("Initialization of the Balancing market TSO orders module...")

        pass
