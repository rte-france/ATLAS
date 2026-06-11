"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from collections.abc import Iterable

from loguru import logger

import atlas.config as cfg
from atlas.core.abstract_class.module import AbstractModule
from atlas.core.io_utils.atlas_dataset import AtlasDataset
from atlas.enums import BusinessModelName
from atlas.modules.portfolio_optimisation.input_dataset import PortfolioOptimisationInputDataset
from atlas.modules.portfolio_optimisation.input_objects.portfolio import PortfolioPO
from atlas.modules.portfolio_optimisation.input_objects.portfolio_equipments import PortfolioEquipments
from atlas.modules.portfolio_optimisation.output_dataset import PortfolioOptimisationOutputDataset
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.orchestration import (
    PortfolioOptimisationResult,
    optimise_portfolio_manual_activated,
    run_parallel,
    run_sequential,
)


class PortfolioOptimisationModule(
    AbstractModule[
        PortfolioOptimisationParameters,
        PortfolioOptimisationInputDataset,
        PortfolioOptimisationOutputDataset,
    ]
):
    def get_parameters_class(self):
        """
        Returns the concrete Parameters class for this module.

        :return: The PortfolioOptimisationParameters class
        :rtype: type[PortfolioOptimisationParameters]
        """
        return PortfolioOptimisationParameters

    def import_data(
        self,
        input_data: AtlasDataset,
        parameters: PortfolioOptimisationParameters,
    ) -> PortfolioOptimisationInputDataset:
        """
        Imports data using business objects and parameters.

        :param input_data: Dictionary of business model objects
        :type input_data: dict[str, list[BusinessModel]]
        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :return: Input dataset for portfolio optimization
        :rtype: PortfolioOptimisationInputDataset
        """
        return PortfolioOptimisationInputDataset(
            input_data.set_frequency_all(parameters.temporal.timestep, inplace=True), parameters
        )

    def validate_data(
        self,
        parameters: PortfolioOptimisationParameters,
        input_dataset: PortfolioOptimisationInputDataset,
    ) -> bool:
        """
        Validates imported or generated data.

        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :param input_dataset: Input dataset to validate
        :type input_dataset: PortfolioOptimisationInputDataset
        :return: True if validation passes, False otherwise
        :rtype: bool
        """
        return True

    def validates_results(
        self,
        parameters: PortfolioOptimisationParameters,
        input_dataset: PortfolioOptimisationInputDataset,
        output_dataset: PortfolioOptimisationOutputDataset,
    ) -> bool:
        """
        Validates results.

        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :param input_dataset: Input dataset
        :type input_dataset: PortfolioOptimisationInputDataset
        :param output_dataset: Output dataset to validate
        :type output_dataset: PortfolioOptimisationOutputDataset
        :return: True if validation passes
        :rtype: bool
        """
        return True

    def export_results(
        self,
        parameters: PortfolioOptimisationParameters,
        input_dataset: PortfolioOptimisationInputDataset,
        output_dataset: PortfolioOptimisationOutputDataset,
    ) -> None:
        """
        Exports results.

        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :param input_dataset: Input dataset
        :type input_dataset: PortfolioOptimisationInputDataset
        :param output_dataset: Output dataset to export
        :type output_dataset: PortfolioOptimisationOutputDataset
        """
        logger.debug("Exporting Portfolio Optimisation results ..")

    def execute(
        self,
        parameters: PortfolioOptimisationParameters,
        input_dataset: PortfolioOptimisationInputDataset,
    ) -> PortfolioOptimisationOutputDataset:
        """
        Executes the module's main logic.

        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :param dataset: Input dataset
        :type dataset: PortfolioOptimisationInputDataset
        :return: Output dataset containing optimization results
        :rtype: PortfolioOptimisationOutputDataset
        """

        cfg.logger.info(
            "Starting Portfolio Optimisation\n"
            f"  Start Date:          {parameters.temporal.start_date}\n"
            f"  End Date:            {parameters.temporal.end_date}\n"
            f"  Execution Date:      {parameters.temporal.execution_date}\n"
            f"  Portfolios:          {len(input_dataset.portfolios)}\n"
            f"  Manual Activation:   {len(input_dataset.portfolios_manual_activation)}\n"
            f"  Mode:                {'Portfolio Bidding' if parameters.is_portfolio_bidding else 'Individual Equipment'}\n"
        )
        optimisation_results: list[PortfolioOptimisationResult] = []

        if parameters.is_portfolio_bidding:
            portfolios = input_dataset.portfolios
        else:
            portfolios = self._prepare_equipment_portfolios(input_dataset, parameters)

        if parameters.multiprocessing.enable:
            optimisation_results = run_parallel(portfolios, parameters)
        else:
            optimisation_results = run_sequential(portfolios, parameters)

        if parameters.is_portfolio_bidding:
            for portfolio in input_dataset.portfolios_manual_activation:
                optimisation_results.append(
                    optimise_portfolio_manual_activated(portfolio=portfolio, parameters=parameters)
                )
        else:
            for portfolio_manual in input_dataset.portfolios_manual_activation:
                for equipment_type, list_equipment in portfolio_manual.equipments.iter_by_type():
                    for equipment in list_equipment:
                        single_equipment = PortfolioEquipments()
                        single_equipment.add(equipment_type, equipment)

                        equipment_portfolio = PortfolioPO(
                            name=equipment.name,
                            equipments=single_equipment,
                            control_block=portfolio_manual.control_block,
                            market_area=portfolio_manual.market_area,
                        )

                        optimisation_results.append(
                            optimise_portfolio_manual_activated(portfolio=equipment_portfolio, parameters=parameters)
                        )

        output_dataset = PortfolioOptimisationOutputDataset(
            parameters=parameters, optimisation_results=optimisation_results
        )

        return output_dataset

    def _prepare_equipment_portfolios(
        self, input_dataset: PortfolioOptimisationInputDataset, parameters: PortfolioOptimisationParameters
    ) -> list[PortfolioPO]:
        """
        Prepare individual equipment portfolios from the input portfolios.

        :param input_dataset: Input dataset containing portfolios
        :type input_dataset: PortfolioOptimisationInputDataset
        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        :return: List of single-equipment portfolios
        :rtype: list[PortfolioPO]
        """
        equipment_portfolios: list[PortfolioPO] = []

        for portfolio in input_dataset.portfolios:
            cfg.logger.debug(f"Processing portfolio {portfolio.name} for individual equipment optimisation")
            for equipment_type, list_equipment in portfolio.equipments.iter_by_type():
                for equipment in list_equipment:
                    single_equipment = PortfolioEquipments()
                    setattr(single_equipment, equipment_type, [equipment])

                    equipment_portfolio = PortfolioPO(
                        name=equipment.name,
                        equipments=single_equipment,
                        control_block=portfolio.control_block,
                        market_area=portfolio.market_area,
                    )

                    equipment_portfolio.market_area.set_market_context(parameters.market, parameters.use_forecast)

                    equipment_portfolios.append(equipment_portfolio)

        return equipment_portfolios

    @staticmethod
    def get_business_model_class_used() -> Iterable[BusinessModelName]:
        """Return list of business model classes used in this dataset."""
        return [
            BusinessModelName.MARKET_AREA,
            BusinessModelName.CONTROL_BLOCK,
            BusinessModelName.PORTFOLIO,
            BusinessModelName.THERMAL,
            BusinessModelName.LOAD,
            BusinessModelName.HYDRO,
            BusinessModelName.STORAGE,
            BusinessModelName.WIND,
            BusinessModelName.SOLAR,
            BusinessModelName.OTHER_NON_DISPATCHABLE,
        ]
