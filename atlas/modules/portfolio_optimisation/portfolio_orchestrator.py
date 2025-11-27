"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

import atlas.config as cfg
from atlas.modules.portfolio_optimisation.input_dataset import PortfolioOptimisationInputDataset
from atlas.modules.portfolio_optimisation.models.portfolio import PortfolioPO
from atlas.modules.portfolio_optimisation.models.portfolio_equipments import PortfolioEquipments
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.portfolio_optimisation_model import PortfolioOptimisationModel
from atlas.modules.portfolio_optimisation.utils.manual_activation import set_manual_activation
from atlas.solver.models import SolverOptions


class PortfolioOptimisationOrchestrator:
    """Orchestrates optimization across multiple portfolios."""

    def __init__(self, parameters: PortfolioOptimisationParameters):
        self.parameters = parameters

    def run(self, input_dataset: PortfolioOptimisationInputDataset) -> dict[str, PortfolioOptimisationModel]:
        """
        Main optimisation method.
        """
        cfg.logger.info(
            f"Starting Portfolio Optimisation | Portfolios: {len(input_dataset.portfolios)}, Manual Activation: {len(input_dataset.portfolios_manual_activation)}"
        )
        models: dict[str, PortfolioOptimisationModel] = {}

        if self.parameters.is_portfolio_bidding:
            for portfolio in input_dataset.portfolios:
                models[portfolio.name] = self._optimise_portfolio(
                    portfolio=portfolio, time_window=input_dataset.time_windows[portfolio.name]
                )
            for portfolio in input_dataset.portfolios_manual_activation:
                models[portfolio.name] = self._optimise_portfolio_manual_activated(portfolio=portfolio)
        else:
            cfg.logger.debug("Individual equipment optimisation mode")

            for portfolio in input_dataset.portfolios:
                cfg.logger.debug(f"Processing portfolio {portfolio.name} for individual equipment optimisation")
                for equipment_type, list_equipment in portfolio.equipments.iter_by_type():
                    for equipment in list_equipment:
                        # Create a single-equipment portfolio
                        single_equipment = PortfolioEquipments()
                        setattr(single_equipment, equipment_type, [equipment])

                        equipment_portfolio = PortfolioPO(
                            name=equipment.name,
                            equipments=single_equipment,
                            control_block=portfolio.control_block,
                            market_area=portfolio.market_area,
                        )

                        equipment_portfolio.market_area.set_market_context(
                            self.parameters.market, self.parameters.use_forecast
                        )

                        models[portfolio.name] = self._optimise_portfolio(
                            portfolio=equipment_portfolio, time_window=input_dataset.time_windows[portfolio.name]
                        )

            for portfolio_manual in input_dataset.portfolios_manual_activation:
                for equipment_type, list_equipment in portfolio_manual.equipments.iter_by_type():
                    for equipment in list_equipment:
                        # Create a single-equipment portfolio
                        single_equipment = PortfolioEquipments()
                        single_equipment.add(equipment_type, equipment)

                        equipment_portfolio = PortfolioPO(
                            name=equipment.name,
                            equipments=single_equipment,
                            control_block=portfolio_manual.control_block,
                            market_area=portfolio_manual.market_area,
                        )

                        models[equipment_portfolio.name] = self._optimise_portfolio_manual_activated(
                            portfolio=equipment_portfolio
                        )

        return models

    def _optimise_portfolio(self, portfolio: PortfolioPO, time_window: list[DateTime]) -> PortfolioOptimisationModel:
        """Run a single portfolio using PortfolioOptimisationModel."""

        solver_options = SolverOptions(
            presolve=self.parameters.use_presolve,
            duality_gap=self.parameters.solver_duality_gap,
            time_limit=self.parameters.solver_timeout,
        )
        model = PortfolioOptimisationModel(portfolio, self.parameters, solver_options=solver_options)

        try:
            model.build_model(time_window)
            model.export_model(f"lp_validation/generated_lp/po_{portfolio.name}.lp")
            model.solve()
            return model

        except Exception as e:
            cfg.logger.error(f"Optimisation failed for portfolio {portfolio.name}: {e}")
            cfg.logger.debug("Falling back to manual activation")

            set_manual_activation(portfolio.equipments.get_all_equipment(), self.parameters)
            return model

    def _optimise_portfolio_manual_activated(self, portfolio: PortfolioPO):
        cfg.logger.info(f"Manual activation for portfolio: {portfolio.name}")
        cfg.logger.debug("Manual activation optimisation not yet implemented")
