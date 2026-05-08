"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.abstract_class.dataset import AbstractModuleOutput
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.matrix import ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.portfolio_optimisation.input_dataset import PortfolioOptimisationInputDataset
from atlas.modules.portfolio_optimisation.input_objects import EquipmentPO
from atlas.modules.portfolio_optimisation.input_objects.hydro import HydroPO
from atlas.modules.portfolio_optimisation.input_objects.storage import StoragePO
from atlas.modules.portfolio_optimisation.input_objects.thermal.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.orchestration import PortfolioOptimisationResult
from atlas.orchestrator.change_set import UpdateObject


class PortfolioOptimisationOutputDataset(AbstractModuleOutput[PortfolioOptimisationParameters]):
    def __init__(
        self,
        parameters: PortfolioOptimisationParameters,
        optimisation_results: list[PortfolioOptimisationResult],
        input_dataset: PortfolioOptimisationInputDataset,
    ):
        self.optimisation_results = optimisation_results
        self.parameters = parameters

    def build_change_sets(self) -> None:
        """Run in-place mutations then export each modified object as an UpdateObject changeset."""
        self.build()

        for optimisation_results in self.optimisation_results:
            portfolio = optimisation_results.portfolio
            if self.parameters.is_portfolio_bidding:
                if not optimisation_results.is_manual_activation:
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
        for optimisation_results in self.optimisation_results:
            if optimisation_results.is_manual_activation:
                continue

            portfolio = optimisation_results.portfolio

            if self.parameters.is_portfolio_bidding:
                imbalance_values = [
                    optimisation_results.get_variable_value(f"{portfolio.name}_large_imbalance_down_{t}")
                    + optimisation_results.get_variable_value(f"{portfolio.name}_small_imbalance_down_{t}")
                    - optimisation_results.get_variable_value(f"{portfolio.name}_large_imbalance_up_{t}")
                    - optimisation_results.get_variable_value(f"{portfolio.name}_small_imbalance_up_{t}")
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
                    portfolio.imbalance = ForecastingMatrix().add(imbalance_ts, self.parameters.temporal.execution_date)

                power_values = [0.0] * len(self.parameters.target_times)
                for _, equipment_list in portfolio.equipments.iter_by_type():
                    for e in equipment_list:
                        if e.power:
                            forecast = e.power.get_forecast(
                                self.parameters.temporal.execution_date,
                                min(self.parameters.target_times),
                                max(self.parameters.target_times),
                            )

                            for idx, value in enumerate(forecast.values):
                                power_values[idx] += value

                power_ts = Timeseries.from_values(
                    start_date=self.parameters.target_times[0],
                    frequency=self.parameters.temporal.timestep,
                    values=power_values,
                )

                if portfolio.power:
                    if self.parameters.temporal.execution_date in portfolio.power:
                        portfolio.power.replace(self.parameters.temporal.execution_date, power_ts)
                    else:
                        portfolio.power.add(power_ts, self.parameters.temporal.execution_date)
                else:
                    portfolio.power = ForecastingMatrix().add(power_ts, self.parameters.temporal.execution_date)

                for type, equipment_list in portfolio.equipments.iter_by_type():
                    self.update_equipment(optimisation_results, type, equipment_list)

    def _extract_values(
        self, equipment: EquipmentPO, equipment_type: str, optimisation_results: PortfolioOptimisationResult
    ) -> tuple[list[float], list[float], list[float]]:
        """
        Extract power and stored energy values from optimization variables.

        :param equipment: Equipment instance
        :type equipment: EquipmentPO
        :param equipment_type: Type of equipment
        :type equipment_type: str
        :param optimisation_results: Optimization result containing the solved variables
        :type optimisation_results: PortfolioOptimisationResult
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
                power = optimisation_results.get_variable_value(f"{equipment.name}_power_level_{t}")

                if abs(power) <= self.parameters.allowed_round_off_error:
                    power = 0.0
                power_values.append(power)

                if optimisation_results.get_variable_value(f"on_up_{equipment.name}_{t}") == 1:
                    state_sequence.append(1)
                elif optimisation_results.get_variable_value(f"on_down_{equipment.name}_{t}") == 1:
                    state_sequence.append(2)
                elif optimisation_results.get_variable_value(f"off_{equipment.name}_{t}") == 1:
                    state_sequence.append(3)
                elif has_t_start and optimisation_results.get_variable_value(f"on_start_{equipment.name}_{t}") == 1:
                    state_sequence.append(4)
                elif has_t_stop and optimisation_results.get_variable_value(f"stop_{equipment.name}_{t}") == 1:
                    state_sequence.append(5)
                elif has_t_stable and optimisation_results.get_variable_value(f"on_flat_{equipment.name}_{t}") == 1:
                    state_sequence.append(6)

        elif equipment_type == "hydro":
            fragment_categories = list(equipment.fragment_data.keys())  # type: ignore
            for t in self.parameters.target_times:
                activated_power = 0.0
                for category in fragment_categories:
                    activated_power += optimisation_results.get_variable_value(
                        f"{equipment.name}_power_level_frag_{category}_{t}"
                    )

                if activated_power <= self.parameters.allowed_round_off_error:
                    activated_power = 0.0

                power_values.append(activated_power)

                stored_energy = optimisation_results.get_variable_value(f"{equipment.name}_stored_energy_{t}")
                stored_energy_values.append(stored_energy)

        elif equipment_type == "storage":
            for t in self.parameters.target_times:
                power = optimisation_results.get_variable_value(
                    f"{equipment.name}_power_level_sell_{t}"
                ) + optimisation_results.get_variable_value(f"{equipment.name}_power_level_buy_{t}")

                if abs(power) <= self.parameters.allowed_round_off_error:
                    power = 0.0

                power_values.append(power)

                stored_energy = optimisation_results.get_variable_value(f"{equipment.name}_stored_energy_{t}")
                stored_energy_values.append(stored_energy)

        else:
            for t in self.parameters.target_times:
                power = optimisation_results.get_variable_value(f"{equipment.name}_power_level_{t}")

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
            equipment.power = ForecastingMatrix().add(power_ts, self.parameters.temporal.execution_date)

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
            equipment.id_po_for_orders = ForecastingMatrix().add(power_ts, self.parameters.temporal.execution_date)

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
                equipment.stored_energy.replace(self.parameters.temporal.execution_date, stored_energy_ts)
            else:
                equipment.stored_energy.add(stored_energy_ts, self.parameters.temporal.execution_date)
        else:
            equipment.stored_energy = ForecastingMatrix().add(stored_energy_ts, self.parameters.temporal.execution_date)

    def _update_state_sequence(self, equipment: ThermalPO, state_sequence: list[float]):
        state_sequence_ts = Timeseries.from_values(
            start_date=self.parameters.target_times[0],
            frequency=self.parameters.temporal.timestep,
            values=state_sequence,
        )

        exec_date_str = self.parameters.temporal.execution_date.to_datetime_string()
        if equipment.state_sequence:
            if exec_date_str in equipment.state_sequence:
                equipment.state_sequence.replace(exec_date_str, state_sequence_ts)
            else:
                equipment.state_sequence.add(state_sequence_ts, exec_date_str)
        else:
            equipment.state_sequence = ScenarioMatrix().add(state_sequence_ts, exec_date_str)

    def update_equipment(
        self, optimisation_results: PortfolioOptimisationResult, equipment_type: str, equipment_list: list[EquipmentPO]
    ):
        """
        Update equipment output with optimization results.

        Extracts power and stored energy values from optimization variables and updates
        the equipment's forecasting matrices.

        :param optimisation_results: Optimization result containing the solved variables
        :type optimisation_results: PortfolioOptimisationResult
        :param equipment_type: Type of equipment (e.g., 'thermal', 'hydro', 'storage', etc.)
        :type equipment_type: str
        :param equipment_list: List of equipment instances to update
        :type equipment_list: list[EquipmentPO]
        """
        if equipment_type in ["other_non_dispatchable", "non_dispatchable_load"]:
            return

        for equipment in equipment_list:
            power_values, stored_energy_values, state_sequence = self._extract_values(
                equipment, equipment_type, optimisation_results
            )

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
