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
from atlas.modules.portfolio_optimisation.models.hydro import HydroPO
from atlas.modules.portfolio_optimisation.models.storage import StoragePO
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
                    self.update_equipment(model, type, equipment_list)

    def _extract_power_values(
        self, equipment: EquipmentPO, equipment_type: str, model: PortfolioOptimisationModel
    ) -> tuple[list[float], list[float]]:
        """
        Extract power and stored energy values from optimization variables.

        Args:
            equipment: Equipment instance
            equipment_type: Type of equipment
            model: Optimization model containing the solved variables

        Returns:
            Tuple of (power_values, stored_energy_values)
        """
        power_values: list[float] = []
        stored_energy_values: list[float] = []

        if equipment_type == "thermal":
            # For thermal equipment, extract power from power_level_var
            for t in self.parameters.target_times:
                power = model.get_variable_value(f"{equipment.name}_power_level_{t}")

                # Apply rounding for small values
                if abs(power) <= self.parameters.allowed_round_off_error:
                    power = 0.0

                power_values.append(power)

            # TODO: Handle thermal state sequence if needed
            # state_sequence values could be extracted from ON_UP, ON_DOWN, OFF, START, STOP, ON_FLAT variables

        elif equipment_type == "hydro":
            # For hydro equipment, sum power across all fragments
            if not isinstance(equipment, HydroPO):
                return power_values, stored_energy_values

            for t in self.parameters.target_times:
                activated_power = 0.0
                for category in equipment.fragment_data.keys():
                    activated_power += model.get_variable_value(f"{equipment.name}_power_level_frag_{category}_{t}")

                if activated_power <= self.parameters.allowed_round_off_error:
                    activated_power = 0.0

                power_values.append(activated_power)

                # Extract stored energy
                stored_energy = model.get_variable_value(f"{equipment.name}_stored_energy_{t}")
                stored_energy_values.append(stored_energy)

        elif equipment_type == "storage":
            # For storage equipment, sum buy and sell power
            if not isinstance(equipment, StoragePO):
                return power_values, stored_energy_values

            for t in self.parameters.target_times:
                power = model.get_variable_value(f"{equipment.name}_power_level_sell_{t}") + model.get_variable_value(
                    f"{equipment.name}_power_level_buy_{t}"
                )

                if abs(power) <= self.parameters.allowed_round_off_error:
                    power = 0.0

                power_values.append(power)

                # Extract stored energy
                stored_energy = model.get_variable_value(f"{equipment.name}_stored_energy_{t}")
                stored_energy_values.append(stored_energy)

        else:
            # For other equipment types (wind, solar, load), extract simple power level
            for t in self.parameters.target_times:
                power = model.get_variable_value(f"{equipment.name}_power_level_{t}")

                if abs(power) <= self.parameters.allowed_round_off_error:
                    power = 0.0

                power_values.append(power)

        return power_values, stored_energy_values

    def _update_power_forecasting_matrix(self, equipment: EquipmentPO, power_values: list[float]):
        """
        Update equipment's power forecasting matrix with optimized power values.

        Args:
            equipment: Equipment instance to update
            power_values: List of power values for target times
        """
        power_ts = Timeseries.from_values(
            start_date=self.parameters.target_times[0],
            frequency=self.parameters.timestep,
            values=power_values,
        )

        if equipment.power:
            if self.parameters.execution_date in equipment.power.index:
                equipment.power.delete(self.parameters.execution_date)
            equipment.power.add(power_ts, self.parameters.execution_date)
        else:
            equipment.power = ForecastingMatrix(
                power_ts.dataframe.rename({"value": self.parameters.execution_date.to_datetime_string()})
            )

    def _update_stored_energy_forecasting_matrix(
        self, equipment: HydroPO | StoragePO, stored_energy_values: list[float]
    ):
        """
        Update equipment's stored energy forecasting matrix.

        Args:
            equipment: Equipment instance to update (must be HydroPO or StoragePO)
            stored_energy_values: List of stored energy values for target times
        """
        if not stored_energy_values:
            return

        stored_energy_ts = Timeseries.from_values(
            start_date=self.parameters.target_times[0],
            frequency=self.parameters.timestep,
            values=stored_energy_values,
        )

        if equipment.stored_energy:
            if self.parameters.execution_date in equipment.stored_energy.index:
                equipment.stored_energy.delete(self.parameters.execution_date)
            equipment.stored_energy.add(stored_energy_ts, self.parameters.execution_date)
        else:
            equipment.stored_energy = ForecastingMatrix(
                stored_energy_ts.dataframe.rename({"value": self.parameters.execution_date.to_datetime_string()})
            )

    def update_equipment(
        self, model: PortfolioOptimisationModel, equipment_type: str, equipment_list: list[EquipmentPO]
    ):
        """
        Update equipment output with optimization results.

        Extracts power and stored energy values from optimization variables and updates
        the equipment's forecasting matrices.

        Args:
            model: Optimization model containing the solved variables
            equipment_type: Type of equipment (e.g., 'thermal', 'hydro', 'storage', etc.)
            equipment_list: List of equipment instances to update
        """
        for equipment in equipment_list:
            # Extract power and stored energy values
            power_values, stored_energy_values = self._extract_power_values(equipment, equipment_type, model)

            # Update power forecasting matrix
            self._update_power_forecasting_matrix(equipment, power_values)

            # Update stored energy forecasting matrix for hydro and storage equipment
            if equipment_type in ["hydro", "storage"] and isinstance(equipment, (HydroPO, StoragePO)):
                self._update_stored_energy_forecasting_matrix(equipment, stored_energy_values)
