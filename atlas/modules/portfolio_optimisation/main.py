"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import cast

from pendulum import DateTime

import atlas.config as cfg
from atlas.modules.portfolio_optimisation.input_dataset import PortfolioOptimisationInputDataset
from atlas.modules.portfolio_optimisation.models import EquipmentPO
from atlas.modules.portfolio_optimisation.models.portfolio import PortfolioPO
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.solver.solver_interface import OptimisationModel, SolutionInfo


class PortfolioOptimisationModel(OptimisationModel):
    """Portfolio-specific optimization model that inherits OR-Tools capabilities."""

    def __init__(self, portfolio: PortfolioPO, parameters: PortfolioOptimisationParameters):
        super().__init__(solver_name=parameters.solver_name, name=portfolio.name)
        self.portfolio = portfolio
        self.parameters = parameters

    def build_model(self, time_window: list[DateTime]) -> None:
        """Build the optimization model by adding variables, constraints, and objectives."""
        cfg.logger.info(f"Building optimisation model for portfolio: {self.portfolio.name} ..")

        for thermal in self.portfolio.equipments.get("thermal", []):
            thermal.add_initial_conditions(self, self.parameters)

        for time in time_window:
            cfg.logger.debug(f"Building optimisation model at time: {time}..")

            self.portfolio.add_variables(self, time, self.parameters)
            price_forecast = self.portfolio.get_price_forecast(time, self.parameters)

            for equipment_type in self.portfolio.equipments:
                equipment_list = self.portfolio.equipments.get(equipment_type, [])

                for equipment in cast(list[EquipmentPO], equipment_list):
                    # Add variables for optimization times
                    equipment.add_variables(self, time, self.parameters)
                    equipment.add_constraints(self, time, self.parameters)
                    equipment.add_objective(
                        model=self, time=time, parameters=self.parameters, price_forecast=price_forecast or 0.0
                    )

            self.portfolio.add_constraints(self, time, self.parameters)
            self.portfolio.add_objective(self, time, self.parameters)

            cfg.logger.debug(f"Completed optimisation model at time: {time}")

        cfg.logger.info(f"Completed optimisation model for portfolio: {self.portfolio.name}.")

    def optimise(self) -> SolutionInfo:
        """Run this specific portfolio using inherited OptimisationModel capabilities."""
        cfg.logger.info(f"Solving portfolio optimisation problem for portfolio: {self.portfolio.name}")

        try:
            solution_info = self.solve(self.parameters.solver_timeout.total_seconds())
            return solution_info

        except Exception as e:
            cfg.logger.error(f"Optimisation failed for portfolio {self.portfolio.name}: {e}")
            raise


class PortfolioOptimisationOrchestrator:
    """Orchestrates optimization across multiple portfolios."""

    def __init__(self, parameters: PortfolioOptimisationParameters):
        self.parameters = parameters

    def run(self, input_dataset: PortfolioOptimisationInputDataset) -> None:
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
                for equipment_type, list_equipment in portfolio.equipments.items():
                    for equipment in list_equipment:
                        equipment_portfolio = PortfolioPO(
                            name=equipment.name,
                            equipments={equipment_type: [equipment]},
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
                for equipment_type, list_equipment in portfolio_manual.equipments.items():
                    for equipment in list_equipment:
                        equipment_portfolio = PortfolioPO(
                            name=equipment.name,
                            equipments={equipment_type: [equipment]},
                            control_block=portfolio_manual.control_block,
                            market_area=portfolio_manual.market_area,
                        )

                        models[equipment_portfolio.name] = self._optimise_portfolio_manual_activated(
                            portfolio=equipment_portfolio
                        )

    def _optimise_portfolio(self, portfolio: PortfolioPO, time_window: list[DateTime]) -> PortfolioOptimisationModel:
        """run a single portfolio using PortfolioOptimisationModel."""

        model = PortfolioOptimisationModel(portfolio, self.parameters)

        # try:
        model.build_model(time_window)
        model.export_model(f"po_{portfolio.name}.lp")
        model.optimise()
        return model

        # except Exception as e:
        #     cfg.logger.error(f"Optimisation failed for portfolio {portfolio.name}: {e}")
        #     cfg.logger.debug("Falling back to manual activation")

        #     equipment_list = [equipment for t in portfolio.equipments for equipment in portfolio.equipments[t]]
        #     cfg.logger.debug(f"Setting manual activation for {len(equipment_list)} equipment(s)")
        #     set_manual_activation(cast(list, equipment_list), self.parameters)

        #     return SolutionInfo(
        #         status=SolverStatus.NOT_SOLVED,
        #         objective_value=None,
        #         solve_time=None,
        #         num_iterations=None,
        #     )

    def _optimise_portfolio_manual_activated(self, portfolio: PortfolioPO):
        cfg.logger.info(f"Manual activation for portfolio: {portfolio.name}")
        cfg.logger.debug("Manual activation optimisation not yet implemented")
