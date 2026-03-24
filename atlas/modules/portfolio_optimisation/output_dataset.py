"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.abstract_class.abstract_dataset import AbstractModuleOutput
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.matrix import ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.portfolio_optimisation.input_dataset import PortfolioOptimisationInputDataset
from atlas.modules.portfolio_optimisation.models import EquipmentPO
from atlas.modules.portfolio_optimisation.models.hydro import HydroPO
from atlas.modules.portfolio_optimisation.models.storage import StoragePO
from atlas.modules.portfolio_optimisation.models.thermal.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.portfolio_orchestrator import PortfolioOptimisationResult
from atlas.workflow.change_set import UpdateObject


class PortfolioOptimisationOutputDataset(AbstractModuleOutput[PortfolioOptimisationParameters]):
    def __init__(
        self,
        parameters: PortfolioOptimisationParameters,
        optimisation_results: dict[str, PortfolioOptimisationResult],
        input_dataset: PortfolioOptimisationInputDataset,
    ):
        super().__init__()
        self.optimisation_results = optimisation_results
        self.parameters = parameters
        self.input_dataset = input_dataset

    def build_change_sets(self) -> None:
        """Run in-place mutations then export each modified object as an UpdateObject changeset."""
        self.build()
        for model in self.optimisation_results.values():
            portfolio = model.portfolio
            if self.parameters.is_portfolio_bidding:
                portfolio_data: dict = {
                    "name": portfolio.name,
                    "imbalance": portfolio.imbalance,
                    "power": portfolio.power,
                }
                self.change_sets.append(UpdateObject(portfolio_data, type(portfolio)))

                for _, equipment_list in portfolio.equipments.iter_by_type():
                    for equipment in equipment_list:
                        equipment_data: dict = {"name": equipment.name, "power": equipment.power}
                        if isinstance(equipment, (HydroPO, StoragePO)):
                            equipment_data["stored_energy"] = equipment.stored_energy
                        if isinstance(equipment, ThermalPO):
                            equipment_data["state_sequence"] = equipment.state_sequence
                        self.change_sets.append(UpdateObject(equipment_data, type(equipment)))

    def build(self):
        for model in self.optimisation_results.values():
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
                    frequency=self.parameters.temporal.timestep,
                    values=imbalance_values,
                )
                if portfolio.imbalance:
                    portfolio.imbalance.add(imbalance_ts, self.parameters.temporal.execution_date)
                else:
                    portfolio.imbalance = ForecastingMatrix(
                        imbalance_ts.dataframe.rename(
                            {"value": self.parameters.temporal.execution_date.to_datetime_string()}
                        )
                    )

                power_values = [0.0] * len(self.parameters.target_times)
                for _, equipment_list in portfolio.equipments.iter_by_type():
                    for e in equipment_list:
                        if e.power:
                            forecast = e.power.get_forecast(
                                self.parameters.temporal.execution_date,
                                min(self.parameters.target_times),
                                max(self.parameters.target_times),
                            )

                            forecast_dict = {row[0]: row[1] for row in forecast.dataframe.iter_rows()}
                            for idx, t in enumerate(self.parameters.target_times):
                                power_values[idx] += forecast_dict.get(t, 0.0)

                power_ts = Timeseries.from_values(
                    start_date=self.parameters.target_times[0],
                    frequency=self.parameters.temporal.timestep,
                    values=power_values,
                )

                if portfolio.power:
                    if self.parameters.temporal.execution_date in portfolio.power:
                        portfolio.power.delete(self.parameters.temporal.execution_date)
                else:
                    portfolio.power = ForecastingMatrix(
                        power_ts.dataframe.rename({"value": self.parameters.temporal.execution_date.to_datetime_string()})
                    )

                for type, equipment_list in portfolio.equipments.iter_by_type():
                    self.update_equipment(model, type, equipment_list)

    def _extract_values(
        self, equipment: EquipmentPO, equipment_type: str, model: PortfolioOptimisationResult
    ) -> tuple[list[float], list[float], list[float]]:
        """
        Extract power and stored energy values from optimization variables.

        :param equipment: Equipment instance
        :type equipment: EquipmentPO
        :param equipment_type: Type of equipment
        :type equipment_type: str
        :param model: Optimization result containing the solved variables
        :type model: PortfolioOptimisationResult
        :return: Tuple of (power_values, stored_energy_values, state_sequence)
        :rtype: tuple[list[float], list[float], list[float]]
        """
        power_values: list[float] = []
        stored_energy_values: list[float] = []
        state_sequence: list[float] = []

        if equipment_type == "thermal":
            state_sequence = []
            has_t_start = equipment._T_start >= 1  # type:ignore [union-attr]
            has_t_stop = equipment._T_stop >= 1  # type:ignore [union-attr]
            has_t_stable = equipment._T_stable >= 1  # type:ignore [union-attr]

            for t in self.parameters.target_times:
                power = model.get_variable_value(f"{equipment.name}_power_level_{t}")

                if abs(power) <= self.parameters.allowed_round_off_error:
                    power = 0.0
                power_values.append(power)

                if model.get_variable_value(f"on_up_{equipment.name}_{t}") == 1:
                    state_sequence.append(1)
                elif model.get_variable_value(f"on_down_{equipment.name}_{t}") == 1:
                    state_sequence.append(2)
                elif model.get_variable_value(f"off_{equipment.name}_{t}") == 1:
                    state_sequence.append(3)
                elif has_t_start and model.get_variable_value(f"on_start_{equipment.name}_{t}") == 1:
                    state_sequence.append(4)
                elif has_t_stop and model.get_variable_value(f"stop_{equipment.name}_{t}") == 1:
                    state_sequence.append(5)
                elif has_t_stable and model.get_variable_value(f"on_flat_{equipment.name}_{t}") == 1:
                    state_sequence.append(6)

        elif equipment_type == "hydro":
            fragment_categories = list(equipment.fragment_data.keys())  # type: ignore
            for t in self.parameters.target_times:
                activated_power = 0.0
                for category in fragment_categories:
                    activated_power += model.get_variable_value(f"{equipment.name}_power_level_frag_{category}_{t}")

                if activated_power <= self.parameters.allowed_round_off_error:
                    activated_power = 0.0

                power_values.append(activated_power)

                stored_energy = model.get_variable_value(f"{equipment.name}_stored_energy_{t}")
                stored_energy_values.append(stored_energy)

        elif equipment_type == "storage":
            for t in self.parameters.target_times:
                power = model.get_variable_value(f"{equipment.name}_power_level_sell_{t}") + model.get_variable_value(
                    f"{equipment.name}_power_level_buy_{t}"
                )

                if abs(power) <= self.parameters.allowed_round_off_error:
                    power = 0.0

                power_values.append(power)

                stored_energy = model.get_variable_value(f"{equipment.name}_stored_energy_{t}")
                stored_energy_values.append(stored_energy)

        else:
            for t in self.parameters.target_times:
                power = model.get_variable_value(f"{equipment.name}_power_level_{t}")

                if abs(power) <= self.parameters.allowed_round_off_error:
                    power = 0.0

                power_values.append(power)

        return power_values, stored_energy_values, state_sequence

    def _update_power_forecasting_matrix(self, equipment: EquipmentPO, power_values: list[float]):
        """
        Update equipment's power forecasting matrix with optimized power values.

        :param equipment: Equipment instance to update
        :type equipment: EquipmentPO
        :param power_values: List of power values for target times
        :type power_values: list[float]
        """
        power_ts = Timeseries.from_values(
            start_date=self.parameters.target_times[0],
            frequency=self.parameters.temporal.timestep,
            values=power_values,
        )

        if equipment.power:
            if self.parameters.temporal.execution_date in equipment.power:
                equipment.power.replace(self.parameters.temporal.execution_date, power_ts)
            else:
                equipment.power.add(power_ts, self.parameters.temporal.execution_date)
        else:
            equipment.power = ForecastingMatrix(
                power_ts.dataframe.rename({"value": self.parameters.temporal.execution_date.to_datetime_string()})
            )

    def _update_id_po_orders_forecasting_matrix(self, equipment: EquipmentPO, power_values: list[float]):
        """
        Update equipment's id po orders forecasting matrix with optimized power values.

        :param equipment: Equipment instance to update
        :type equipment: EquipmentPO
        :param power_values: List of power values for target times
        :type power_values: list[float]
        """
        power_ts = Timeseries.from_values(
            start_date=self.parameters.target_times[0],
            frequency=self.parameters.temporal.timestep,
            values=power_values,
        )

        if equipment.id_po_for_orders:
            if self.parameters.temporal.execution_date in equipment.id_po_for_orders:
                equipment.id_po_for_orders.replace(self.parameters.temporal.execution_date, power_ts)
            else:
                equipment.id_po_for_orders.add(power_ts, self.parameters.temporal.execution_date)
        else:
            equipment.id_po_for_orders = ForecastingMatrix(
                power_ts.dataframe.rename({"value": self.parameters.temporal.execution_date.to_datetime_string()})
            )

    def _update_stored_energy_forecasting_matrix(
        self, equipment: HydroPO | StoragePO, stored_energy_values: list[float]
    ):
        """
        Update equipment's stored energy forecasting matrix.

        :param equipment: Equipment instance to update (must be HydroPO or StoragePO)
        :type equipment: HydroPO | StoragePO
        :param stored_energy_values: List of stored energy values for target times
        :type stored_energy_values: list[float]
        """
        if not stored_energy_values:
            return

        stored_energy_ts = Timeseries.from_values(
            start_date=self.parameters.target_times[0],
            frequency=self.parameters.temporal.timestep,
            values=stored_energy_values,
        )

        if equipment.stored_energy:
            if self.parameters.temporal.execution_date in equipment.stored_energy:
                equipment.stored_energy.delete(self.parameters.temporal.execution_date)
            equipment.stored_energy.add(stored_energy_ts, self.parameters.temporal.execution_date)
        else:
            equipment.stored_energy = ForecastingMatrix(
                stored_energy_ts.dataframe.rename({"value": self.parameters.temporal.execution_date.to_datetime_string()})
            )

    def _update_state_sequence(self, equipment: ThermalPO, state_sequence: list[float]):
        state_sequence_ts = Timeseries.from_values(
            start_date=self.parameters.target_times[0],
            frequency=self.parameters.temporal.timestep,
            values=state_sequence,
        )

        if equipment.state_sequence:
            if self.parameters.temporal.execution_date in equipment.state_sequence:
                equipment.state_sequence.replace(
                    self.parameters.temporal.execution_date.to_datetime_string(), state_sequence_ts
                )
            else:
                equipment.state_sequence.add(
                    state_sequence_ts, self.parameters.temporal.execution_date.to_datetime_string()
                )
        else:
            equipment.state_sequence = ScenarioMatrix(
                state_sequence_ts.dataframe.rename({"value": self.parameters.temporal.execution_date.to_datetime_string()})
            )

    def update_equipment(
        self, model: PortfolioOptimisationResult, equipment_type: str, equipment_list: list[EquipmentPO]
    ):
        """
        Update equipment output with optimization results.

        Extracts power and stored energy values from optimization variables and updates
        the equipment's forecasting matrices.

        :param model: Optimization result containing the solved variables
        :type model: PortfolioOptimisationResult
        :param equipment_type: Type of equipment (e.g., 'thermal', 'hydro', 'storage', etc.)
        :type equipment_type: str
        :param equipment_list: List of equipment instances to update
        :type equipment_list: list[EquipmentPO]
        """
        if equipment_type in ["other_non_dispatchable", "non_dispatchable_load"]:
            return

        for equipment in equipment_list:
            power_values, stored_energy_values, state_sequence = self._extract_values(equipment, equipment_type, model)

            if not self.parameters.use_forecast:
                self._update_power_forecasting_matrix(equipment, power_values)

                if isinstance(equipment, (HydroPO, StoragePO)):
                    self._update_stored_energy_forecasting_matrix(equipment, stored_energy_values)
                elif isinstance(equipment, ThermalPO):
                    self._update_state_sequence(equipment, state_sequence)
                else:
                    continue
            else:
                self._update_id_po_orders_forecasting_matrix(equipment, power_values)
                if isinstance(equipment, ThermalPO):
                    self._update_state_sequence(equipment, state_sequence)
                else:
                    continue
