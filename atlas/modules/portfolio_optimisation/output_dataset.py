"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.abstract_class.dataset import AbstractModuleOutput
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.matrix import ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.portfolio_optimisation.input_objects.hydro import HydroPO
from atlas.modules.portfolio_optimisation.input_objects.storage import StoragePO
from atlas.modules.portfolio_optimisation.input_objects.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.result_extraction import EquipmentSchedule, extract_equipment_schedule
from atlas.orchestrator.change_set import UpdateObject

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.input_objects import EquipmentPO
    from atlas.modules.portfolio_optimisation.input_objects.portfolio import PortfolioPO
    from atlas.modules.portfolio_optimisation.utils.orchestration import PortfolioOptimisationResult


class PortfolioOptimisationOutputDataset(AbstractModuleOutput[PortfolioOptimisationParameters]):
    """
    Output of the portfolio optimisation module.

    Writes the solved schedules onto the portfolio and equipment objects, then exports the
    modified objects as changesets for the orchestrator to apply onto the current input state.
    """

    def __init__(
        self,
        parameters: PortfolioOptimisationParameters,
        optimisation_results: list[PortfolioOptimisationResult],
    ):
        self.optimisation_results = optimisation_results
        self.parameters = parameters

    def build_change_sets(self) -> None:
        """Run in-place mutations then export each modified object as an UpdateObject changeset."""
        self.update_equipments()
        self.update_portfolios()

        for optimisation_result in self.optimisation_results:
            portfolio = optimisation_result.portfolio

            if self.parameters.is_portfolio_bidding and not optimisation_result.is_manual_activation:
                portfolio_data: dict = {
                    "name": portfolio.name,
                    "imbalance": portfolio.imbalance,
                    "power": portfolio.power,
                }
                self.change_sets.append(UpdateObject(portfolio_data, type(portfolio)))

            for _, equipment_list in portfolio.equipments.iter_by_type():
                for equipment in equipment_list:
                    self.change_sets.append(UpdateObject(self._equipment_data(equipment), type(equipment)))

    def _equipment_data(self, equipment: EquipmentPO) -> dict:
        """
        Build the payload of the changeset updating an equipment.

        :param equipment: Equipment carrying the optimised schedule.
        :type equipment: EquipmentPO
        :return: Attributes to write onto the corresponding current input state object.
        :rtype: dict
        """
        equipment_data: dict = {"name": equipment.name, "power": equipment.power}

        if self.parameters.use_forecast:
            equipment_data["id_po_for_orders"] = equipment.id_po_for_orders
        if isinstance(equipment, (HydroPO, StoragePO)):
            equipment_data["stored_energy"] = equipment.stored_energy
        if isinstance(equipment, ThermalPO):
            equipment_data["state_sequence"] = equipment.state_sequence

        return equipment_data

    def update_equipments(self) -> None:
        """
        Write the optimised schedule of every equipment onto the equipment itself.

        Manually activated portfolios are skipped: their schedules are already set by
        :func:`atlas.modules.portfolio_optimisation.utils.manual_activation.set_manual_activation`.
        """
        for optimisation_result in self.optimisation_results:
            if optimisation_result.is_manual_activation:
                continue

            for _, equipment_list in optimisation_result.portfolio.equipments.iter_by_type_for_optimisation():
                for equipment in equipment_list:
                    self._write_equipment_schedule(equipment, optimisation_result)

    def update_portfolios(self) -> None:
        """
        Write the imbalance and the aggregated power onto every optimised portfolio.

        Must run after :meth:`update_equipments`, since the portfolio power is the sum of the
        equipment schedules. Does nothing in individual equipment mode, where the portfolio is a
        synthetic single-equipment wrapper: portfolio-level results are neither meaningful there
        nor exported as changesets.
        """
        if not self.parameters.is_portfolio_bidding:
            return

        for optimisation_result in self.optimisation_results:
            if optimisation_result.is_manual_activation:
                continue

            self._write_portfolio_imbalance(optimisation_result.portfolio, optimisation_result)
            self._write_portfolio_power(optimisation_result.portfolio)

    def _write_equipment_schedule(
        self, equipment: EquipmentPO, optimisation_result: PortfolioOptimisationResult
    ) -> None:
        """
        Read the optimised schedule of an equipment and store it on the equipment itself.

        In forecast mode the schedule feeds ``id_po_for_orders`` and leaves the committed
        ``power`` and ``stored_energy`` untouched, since the optimisation is only run to build
        orders ahead of a market.

        :param equipment: Equipment to update.
        :type equipment: EquipmentPO
        :param optimisation_result: Solved optimisation holding the variable values.
        :type optimisation_result: PortfolioOptimisationResult
        """
        schedule = extract_equipment_schedule(
            equipment,
            optimisation_result,
            self.parameters.target_times,
            self.parameters.allowed_round_off_error,
        )

        if self.parameters.use_forecast:
            equipment.id_po_for_orders = self._upsert_forecast(equipment.id_po_for_orders, schedule.power)
        else:
            equipment.power = self._upsert_forecast(equipment.power, schedule.power)
            if isinstance(equipment, (HydroPO, StoragePO)):
                equipment.stored_energy = self._upsert_forecast(equipment.stored_energy, schedule.stored_energy)

        if isinstance(equipment, ThermalPO):
            self._write_state_sequence(equipment, schedule)

    def _write_state_sequence(self, equipment: ThermalPO, schedule: EquipmentSchedule) -> None:
        """
        Store the operating state sequence of a thermal unit, indexed by execution date.

        :param equipment: Thermal unit to update.
        :type equipment: ThermalPO
        :param schedule: Optimised schedule holding the state sequence.
        :type schedule: EquipmentSchedule
        """
        if not schedule.state_sequence:
            return

        state_sequence_ts = self._to_timeseries([float(state) for state in schedule.state_sequence])
        execution_date = self.parameters.temporal.execution_date.to_datetime_string()

        if equipment.state_sequence is None:
            equipment.state_sequence = ScenarioMatrix()
        equipment.state_sequence.upsert(execution_date, state_sequence_ts)

    def _write_portfolio_imbalance(
        self, portfolio: PortfolioPO, optimisation_result: PortfolioOptimisationResult
    ) -> None:
        """
        Store the net imbalance of a portfolio, counted positively when the portfolio is short.

        :param portfolio: Portfolio to update.
        :type portfolio: PortfolioPO
        :param optimisation_result: Solved optimisation holding the variable values.
        :type optimisation_result: PortfolioOptimisationResult
        """
        imbalance_values = [
            optimisation_result.get_variable_value(f"{portfolio.name}_large_imbalance_down_{time}")
            + optimisation_result.get_variable_value(f"{portfolio.name}_small_imbalance_down_{time}")
            - optimisation_result.get_variable_value(f"{portfolio.name}_large_imbalance_up_{time}")
            - optimisation_result.get_variable_value(f"{portfolio.name}_small_imbalance_up_{time}")
            for time in self.parameters.target_times
        ]

        portfolio.imbalance = self._upsert_forecast(portfolio.imbalance, imbalance_values)

    def _write_portfolio_power(self, portfolio: PortfolioPO) -> None:
        """
        Store the portfolio power as the sum of the power of its equipments.

        Must run after the equipments have been updated, since it reads back their schedules.

        :param portfolio: Portfolio to update.
        :type portfolio: PortfolioPO
        """
        power_ts = self._to_timeseries([0.0] * len(self.parameters.target_times))

        for _, equipment_list in portfolio.equipments.iter_by_type():
            for equipment in equipment_list:
                if equipment.power:
                    power_ts = power_ts + equipment.power.get_forecast(
                        self.parameters.temporal.execution_date,
                        min(self.parameters.target_times),
                        max(self.parameters.target_times),
                    )

        portfolio.power = self._upsert_forecast(portfolio.power, power_ts)

    def _to_timeseries(self, values: list[float]) -> Timeseries:
        """
        Build a timeseries spanning the target times.

        :param values: One value per target time.
        :type values: list[float]
        :return: The corresponding timeseries.
        :rtype: Timeseries
        """
        return Timeseries.from_values(
            start_date=self.parameters.target_times[0],
            frequency=self.parameters.temporal.timestep,
            values=values,
        )

    def _upsert_forecast(
        self, matrix: ForecastingMatrix | LazyForecastingMatrix | None, values: list[float] | Timeseries
    ) -> ForecastingMatrix | LazyForecastingMatrix:
        """
        Write a forecast at the execution date, creating the matrix if the attribute is still empty.

        :param matrix: Existing forecasting matrix, or None if the object carries none yet.
        :type matrix: ForecastingMatrix | LazyForecastingMatrix | None
        :param values: One value per target time, or an already-built timeseries.
        :type values: list[float] | Timeseries
        :return: The matrix holding the new forecast.
        :rtype: ForecastingMatrix | LazyForecastingMatrix
        """
        timeseries = values if isinstance(values, Timeseries) else self._to_timeseries(values)
        execution_date = self.parameters.temporal.execution_date

        if matrix is None:
            return ForecastingMatrix().add(timeseries, execution_date)

        matrix.upsert(execution_date, timeseries)
        return matrix
