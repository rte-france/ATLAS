"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import cast

from pendulum import DateTime

import atlas.config as cfg
from atlas.enum import SolverStatus
from atlas.modules.portfolio_optimisation.input_dataset import PortfolioOptimisationInputDataset
from atlas.modules.portfolio_optimisation.models import EquipmentPO
from atlas.modules.portfolio_optimisation.models.hydro import HydroPO
from atlas.modules.portfolio_optimisation.models.load import LoadPO
from atlas.modules.portfolio_optimisation.models.portfolio import PortfolioPO
from atlas.modules.portfolio_optimisation.models.solar import SolarPO
from atlas.modules.portfolio_optimisation.models.storage import StoragePO
from atlas.modules.portfolio_optimisation.models.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.models.wind import WindPO
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.manual_activation import set_manual_activation
from atlas.solver.solver_interface import OptimisationModel, SolutionInfo


class PortfolioOptimisationModel:
    """Main class for optimal placement optimization using OptimisationModel."""

    def __init__(self, parameters: PortfolioOptimisationParameters):
        self.parameters = parameters

    def optimize(self, input_dataset: PortfolioOptimisationInputDataset) -> None:
        """
        Main optimization method.
        """
        cfg.logger.info("Starting optimal placement optimization")

        if self.parameters.is_portfolio_bidding:
            for portfolio in input_dataset.portfolios:
                self._optimize_portfolio(
                    portfolio=portfolio,
                    max_optimisation_times=input_dataset.max_optimisation_times,
                )
            for portfolio in input_dataset.portfolios_manual_activation:
                self._optimize_portfolio_manual_activated(
                    portfolio=portfolio,
                )
        else:
            for portfolio in input_dataset.portfolios:
                for equipment_type, list_equipment in portfolio.equipments.items():
                    for equipment in list_equipment:
                        equipment_portfolio = PortfolioPO(
                            name=equipment.name,
                            equipments={equipment_type: [equipment]},
                            control_block=portfolio.control_block,
                            market_area=portfolio.market_area,
                        )

                        self._optimize_portfolio(
                            portfolio=equipment_portfolio,
                            max_optimisation_times=input_dataset.max_optimisation_times,
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

                    self._optimize_portfolio_manual_activated(
                        portfolio=equipment_portfolio,
                    )

    def _optimize_portfolio(
        self,
        portfolio: PortfolioPO,
        max_optimisation_times: list[DateTime],
    ) -> SolutionInfo:
        """Optimize a single portfolio using OptimisationModel."""

        cfg.logger.info(f"Optimizing portfolio: {portfolio.name}")

        model = OptimisationModel(solver_name=self.parameters.solver_name, name=portfolio.name)

        try:
            for time in max_optimisation_times:
                portfolio.add_variables(model, time, self.parameters)

                portfolio.add_constraints(time, model, self.parameters)

                portfolio.add_objective(model, time, self.parameters)

                # Get price forecast for equipment that need it
                price_forecast = None
                if time in self.parameters.target_times:
                    price_forecast = portfolio._get_price_forecast(time, self.parameters)

                for equipment_type in portfolio.equipments:
                    for equipment in cast(
                        list[EquipmentPO],
                        portfolio.equipments.get(equipment_type, []),
                    ):
                        if hasattr(equipment, "add_variables"):
                            equipment.add_variables(model, time, self.parameters)

                        if hasattr(equipment, "add_constraints"):
                            equipment.add_constraints(time, model, self.parameters)

                        if time in self.parameters.target_times and hasattr(equipment, "add_objective"):
                            equipment_type_name = type(equipment).__name__
                            if equipment_type_name in ("WindPO", "SolarPO"):
                                cast(WindPO | SolarPO, equipment).add_objective(model, time, self.parameters)
                            elif equipment_type_name in ("HydroPO", "LoadPO", "StoragePO", "ThermalPO"):
                                cast(HydroPO | LoadPO | StoragePO | ThermalPO, equipment).add_objective(
                                    model, time, price_forecast or 0.0, self.parameters
                                )

            solution_info = model.solve()

            cfg.logger.info(
                f"Portfolio {portfolio.name} optimization completed with status: {solution_info.status.name}"
            )

            return solution_info

        except Exception as e:
            cfg.logger.error(f"Optimization failed for portfolio {portfolio.name}: {e}")

            equipment_list = [equipment for t in portfolio.equipments for equipment in portfolio.equipments[t]]
            set_manual_activation(cast(list, equipment_list), self.parameters)

            return SolutionInfo(
                status=SolverStatus.NOT_SOLVED,
                objective_value=None,
                solve_time=None,
                num_iterations=None,
            )

    def _optimize_portfolio_manual_activated(self, portfolio: PortfolioPO):
        pass
