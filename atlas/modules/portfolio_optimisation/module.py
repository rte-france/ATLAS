"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import BusinessModel
from atlas.abstract_class.abstract_module import AbstractModule
from atlas.modules.portfolio_optimisation.input_dataset import PortfolioOptimisationInputDataset
from atlas.modules.portfolio_optimisation.main import PortfolioOptimisationModel
from atlas.modules.portfolio_optimisation.output_dataset import PortfolioOptimisationOutputDataset
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


class PortfolioOptimisationModule(
    AbstractModule[
        PortfolioOptimisationParameters,
        PortfolioOptimisationInputDataset,
        PortfolioOptimisationOutputDataset,
    ]
):
    def get_parameters_class(self):
        """Returns the concrete Parameters class for this module."""
        return PortfolioOptimisationParameters

    def import_data(
        self,
        raw_data: dict[str, list[type[BusinessModel]]],
        parameters: PortfolioOptimisationParameters,
    ) -> PortfolioOptimisationInputDataset:
        """Imports data using business objects and parameters."""
        return PortfolioOptimisationInputDataset(raw_data, parameters)

    def validate_data(
        self,
        parameters: PortfolioOptimisationParameters,
        input_dataset: PortfolioOptimisationInputDataset,
    ) -> bool:
        """Validates imported or generated data."""
        return True

    def validates_results(
        self,
        parameters: PortfolioOptimisationParameters,
        input_dataset: PortfolioOptimisationInputDataset,
        output_dataset: PortfolioOptimisationOutputDataset,
    ) -> bool:
        """Validates results"""
        return True

    def export_results(
        self,
        parameters: PortfolioOptimisationParameters,
        input_dataset: PortfolioOptimisationInputDataset,
        output_dataset: PortfolioOptimisationOutputDataset,
    ) -> None:
        """Exports results."""
        pass

    def execute(
        self,
        parameters: PortfolioOptimisationParameters,
        dataset: PortfolioOptimisationInputDataset,
    ) -> PortfolioOptimisationOutputDataset:
        """Executes the module's main logic."""
        model = PortfolioOptimisationModel(parameters)
        model.optimize(dataset)
        return PortfolioOptimisationOutputDataset()
