"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import BusinessModel
from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.math.timeseries import Timeseries
from atlas.modules.portfolio_optimisation.input_dataset import PortfolioOptimisationInputDataset
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.portfolio_optimisation_model import PortfolioOptimisationModel


class PortfolioOptimisationOutputDataset(AbstractDataset[PortfolioOptimisationParameters]):
    def __init__(
        self,
        parameters: PortfolioOptimisationParameters,
        models: dict[str, PortfolioOptimisationModel],
        input_dataset: PortfolioOptimisationInputDataset,
    ):
        self.models = models
        self.parameters = parameters
        self.input_dataset = input_dataset

    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return []

    def build_output(self):
        for model in self.models.values():
            portfolio = model.portfolio

            if self.parameters.is_portfolio_bidding:
                imbalance_values = [
                    model.get_variable_value(f"{portfolio.name}_large_imbalance_down_{t}")
                    + model.get_variable_value(f"{portfolio.name}_small_imbalance_down_{t}")
                    - model.get_variable_value(f"{portfolio.name}_large_imbalance_up_{t}")
                    - model.get_variable_value(f"{portfolio.name}_small_imbalance_up_{t}")
                    for t in self.parameters.target_times
                ]
                imbalance_ts = Timeseries.from_values(
                    start_date=self.parameters.target_times[0],
                    frequency=self.parameters.timestep,
                    values=imbalance_values,
                )

                portfolio.imbalance.add(imbalance_ts)

                power_values = [
                    e.power.get_forecast(self.parameters.execution_date, t, t)
                    for e in portfolio.equipments.iter_by_type()
                    for t in self.parameters.target_times
                ]

                power_ts = Timeseries.from_values(
                    start_date=self.parameters.target_times[0],
                    frequency=self.parameters.timestep,
                    values=power_values,
                )

                if self.parameters.execution_date in portfolio.power:
                    portfolio.power.delete(self.parameters.execution_date)

                portfolio.power.add(power_ts)
