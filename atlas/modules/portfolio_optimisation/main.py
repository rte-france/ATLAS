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
    """Main class for optimal placement optimisation using OptimisationModel."""

    def __init__(self, parameters: PortfolioOptimisationParameters):
        self.parameters = parameters

    def optimize(self, input_dataset: PortfolioOptimisationInputDataset) -> None:
        """
        Main optimisation method.
        """
        cfg.logger.info("Starting optimal placement optimisation")
        cfg.logger.debug(f"Portfolio bidding mode: {self.parameters.is_portfolio_bidding}")
        cfg.logger.debug(f"Number of portfolios: {len(input_dataset.portfolios)}")
        cfg.logger.debug(f"Number of manual activation portfolios: {len(input_dataset.portfolios_manual_activation)}")

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

        cfg.logger.info(f"Optimising portfolio: {portfolio.name}")

        model = OptimisationModel(solver_name=self.parameters.solver_name, name=portfolio.name)

        try:
            for time in max_optimisation_times:
                cfg.logger.debug(f"Processing optimisation time: {time}")
                portfolio.add_variables(model, time, self.parameters)

                price_forecast = None
                if time in self.parameters.target_times:
                    price_forecast = portfolio.get_price_forecast(time, self.parameters)

                for equipment_type in portfolio.equipments:
                    equipment_list = portfolio.equipments.get(equipment_type, [])

                    for equipment in cast(list[EquipmentPO], equipment_list):
                        cfg.logger.debug(f"Processing equipment: {equipment.name}")

                        if hasattr(equipment, "add_variables"):
                            cfg.logger.debug(
                                f"Adding variables for equipment: {equipment.name}, of type {type(equipment).__name__}"
                            )
                            equipment.add_variables(model, time, self.parameters)

                        if hasattr(equipment, "add_constraints"):
                            cfg.logger.debug(
                                f"Adding constraints for equipment: {equipment.name}, of type {type(equipment).__name__}"
                            )
                            equipment.add_constraints(time, model, self.parameters)

                        if time in self.parameters.target_times and hasattr(equipment, "add_objective"):
                            equipment_type_name = type(equipment).__name__
                            cfg.logger.debug(
                                f"Adding objective for equipment {equipment.name} of type {equipment_type_name}"
                            )
                            if equipment_type_name in ("WindPO", "SolarPO"):
                                cast(WindPO | SolarPO, equipment).add_objective(model, time, self.parameters)
                            elif equipment_type_name in ("HydroPO", "LoadPO", "StoragePO", "ThermalPO"):
                                cast(HydroPO | LoadPO | StoragePO | ThermalPO, equipment).add_objective(
                                    model, time, price_forecast or 0.0, self.parameters
                                )

                portfolio.add_constraints(time, model, self.parameters)

                portfolio.add_objective(model, time, self.parameters)

            solution_info = model.solve()

            cfg.logger.info(
                f"Portfolio {portfolio.name} optimisation completed with status: {solution_info.status.name}"
            )
            if solution_info.objective_value is not None:
                cfg.logger.debug(f"Objective value: {solution_info.objective_value}")
            if solution_info.solve_time is not None:
                cfg.logger.debug(f"Solve time: {solution_info.solve_time}s")

            return solution_info

        except Exception as e:
            cfg.logger.error(f"optimisation failed for portfolio {portfolio.name}: {e}")
            cfg.logger.debug("Falling back to manual activation")

            equipment_list = [equipment for t in portfolio.equipments for equipment in portfolio.equipments[t]]
            cfg.logger.debug(f"Setting manual activation for {len(equipment_list)} equipment(s)")
            set_manual_activation(cast(list, equipment_list), self.parameters)

            return SolutionInfo(
                status=SolverStatus.NOT_SOLVED,
                objective_value=None,
                solve_time=None,
                num_iterations=None,
            )

    def _optimize_portfolio_manual_activated(self, portfolio: PortfolioPO):
        cfg.logger.info(f"Manual activation for portfolio: {portfolio.name}")
        cfg.logger.debug("Manual activation optimisation not yet implemented")
