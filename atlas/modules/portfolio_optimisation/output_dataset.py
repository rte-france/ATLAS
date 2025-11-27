"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import BusinessModel
from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.portfolio_optimisation.input_dataset import PortfolioOptimisationInputDataset
from atlas.modules.portfolio_optimisation.models import EquipmentPO
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
                if portfolio.imbalance:
                    portfolio.imbalance.add(imbalance_ts, self.parameters.execution_date)
                else:
                    portfolio.imbalance = ForecastingMatrix(
                        imbalance_ts.dataframe.rename({"value": self.parameters.execution_date.to_datetime_string()})
                    )

                power_values = []
                for _, equipment_list in portfolio.equipments.iter_by_type():
                    for e in equipment_list:
                        forecast = e.power.get_forecast(
                            self.parameters.execution_date,
                            min(self.parameters.target_times),
                            max(self.parameters.target_times),
                        )

                        for t in self.parameters.target_times:
                            value = forecast.get_value(t) if t in forecast else 0
                            power_values.append(value)

                power_ts = Timeseries.from_values(
                    start_date=self.parameters.target_times[0],
                    frequency=self.parameters.timestep,
                    values=power_values,
                )

                if portfolio.power:
                    if self.parameters.execution_date in portfolio.power.index:
                        portfolio.power.delete(self.parameters.execution_date)
                else:
                    portfolio.power = ForecastingMatrix(
                        power_ts.dataframe.rename({"value": self.parameters.execution_date.to_datetime_string()})
                    )

                for type, equipment_list in portfolio.equipments.iter_by_type():
                    self.update_equipment(type, equipment_list)

    def update_equipment(type: str, equipment_list: EquipmentPO):
        pass
