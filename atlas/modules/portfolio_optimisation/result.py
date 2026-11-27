"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.abstract_class.dataset import ModuleResult
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.matrix import ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.portfolio_optimisation.input_objects.hydro import HydroPO
from atlas.modules.portfolio_optimisation.input_objects.portfolio import PortfolioPO
from atlas.modules.portfolio_optimisation.input_objects.storage import StoragePO
from atlas.modules.portfolio_optimisation.input_objects.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.result_extraction import EquipmentSchedule, extract_equipment_schedule
from atlas.orchestrator.change_set import ChangeSet, UpdateObject

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.input_objects import EquipmentPO
    from atlas.modules.portfolio_optimisation.input_objects.load import LoadPO
    from atlas.modules.portfolio_optimisation.input_objects.other_non_dispatchable import OtherNonDispatchablePO
    from atlas.modules.portfolio_optimisation.utils.orchestration import SinglePortfolioResult


class PortfolioOptimisationResult(ModuleResult[PortfolioOptimisationParameters]):
    """
    Output of the portfolio optimisation module.

    Writes the solved schedules onto the portfolio and equipment objects, then exports the
    modified objects as changesets for the orchestrator to apply onto the current input state.
    """

    def __init__(
        self,
        parameters: PortfolioOptimisationParameters,
        optimisation_results: list[SinglePortfolioResult],
    ):
        self.optimisation_results = optimisation_results
        self.parameters = parameters

    def build_change_sets(self) -> list[ChangeSet]:
        """Run in-place mutations then export each modified object as an UpdateObject changeset."""
        change_sets: list[ChangeSet] = []
        self.update_equipments()
        self.update_portfolios()

        if self._writes_portfolio_level:
            for portfolio, _ in self._group_by_portfolio().values():
                portfolio_data: dict = {
                    "name": portfolio.name,
                    "imbalance": portfolio.imbalance,
                    "power": portfolio.power,
                }
                change_sets.append(UpdateObject(portfolio_data, type(portfolio)))

        for optimisation_result in self.optimisation_results:
            for _, equipment_list in optimisation_result.portfolio.equipments.iter_by_type():
                for equipment in equipment_list:
                    change_sets.append(UpdateObject(self._equipment_data(equipment), type(equipment)))
        return change_sets

    @property
    def _writes_portfolio_level(self) -> bool:
        """
        Whether the portfolio power and imbalance are computed and exported.

        Only in portfolio bidding mode (in individual equipment mode the portfolio is a synthetic
        single-equipment wrapper), and not in forecast mode, where the optimisation only builds
        orders and leaves the committed schedules untouched.
        """
        return self.parameters.is_portfolio_bidding and not self.parameters.use_forecast

    def _group_by_portfolio(self) -> dict[str, tuple[PortfolioPO, list[EquipmentPO]]]:
        """
        Gather the results of a same portfolio, keyed by its name.

        A portfolio whose equipments are partly excluded from the optimisation is split into an
        optimised part and a manually activated part sharing the same name. The first part met
        carries the portfolio-level results; the equipments of every part are gathered.

        :return: For each portfolio name, the portfolio carrying the results and all its equipments.
        :rtype: dict[str, tuple[PortfolioPO, list[EquipmentPO]]]
        """
        groups: dict[str, tuple[PortfolioPO, list[EquipmentPO]]] = {}
        for optimisation_result in self.optimisation_results:
            portfolio = optimisation_result.portfolio
            _, equipments = groups.setdefault(portfolio.name, (portfolio, []))
            equipments.extend(portfolio.equipments.get_all_equipment())
        return groups

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
        Write the optimised schedule of every equipment onto the equipment itself, and the
        forecasted power of every non-dispatchable equipment.

        Manually activated portfolios are skipped: their schedules are already set by
        :func:`atlas.modules.portfolio_optimisation.utils.manual_activation.set_manual_activation`.
        """
        for optimisation_result in self.optimisation_results:
            if optimisation_result.is_manual_activation:
                continue

            for _, equipment_list in optimisation_result.portfolio.equipments.iter_by_type_for_optimisation():
                for equipment in equipment_list:
                    self._write_equipment_schedule(equipment, optimisation_result)

            equipments = optimisation_result.portfolio.equipments
            non_dispatchable_equipment: list[LoadPO | OtherNonDispatchablePO] = [
                *equipments.non_dispatchable_load,
                *equipments.other_non_dispatchable,
            ]
            for non_dispatchable in non_dispatchable_equipment:
                self._write_forecasted_power(non_dispatchable)

    def _write_forecasted_power(self, equipment: LoadPO | OtherNonDispatchablePO) -> None:
        """
        Store the forecasted power of a non-dispatchable equipment as its schedule.

        Such an equipment has no variable in the optimisation: it delivers its maximum power
        forecast at the execution date whatever it sold or bought, the gap being carried by the
        portfolio imbalance. Like the optimised schedules, it feeds ``id_po_for_orders`` in
        forecast mode.

        :param equipment: Non-dispatchable load or other non-dispatchable equipment to update.
        :type equipment: LoadPO | OtherNonDispatchablePO
        """
        window = self.parameters.portfolio_time_window
        forecasted_power = equipment.maximum_power_forecast.get_forecast(
            self.parameters.temporal.execution_date, min(window), max(window), default_value=0
        )

        if self.parameters.use_forecast:
            equipment.id_po_for_orders = self._upsert_forecast(equipment.id_po_for_orders, forecasted_power)
        else:
            equipment.power = self._upsert_forecast(equipment.power, forecasted_power)

    def update_portfolios(self) -> None:
        """
        Write the aggregated power and the imbalance onto every portfolio.

        Every portfolio is processed, whether optimised, manually activated (by configuration or
        after an unsuccessful solve) or split between both. Its power is the sum of the power of
        all its equipments, and its imbalance the gap between that power and the quantities
        cleared (or activated) upstream, positive for excess production.

        Must run after :meth:`update_equipments`, since it reads back the equipment schedules.
        Does nothing when :attr:`_writes_portfolio_level` is false.
        """
        if not self._writes_portfolio_level:
            return

        for portfolio, equipments in self._group_by_portfolio().values():
            power_ts = self._sum_equipment_power(equipments)
            imbalance_ts = power_ts - self._sum_upstream_energy(equipments)

            portfolio.power = self._upsert_forecast(portfolio.power, power_ts)
            portfolio.imbalance = self._upsert_forecast(portfolio.imbalance, imbalance_ts)

    def _write_equipment_schedule(self, equipment: EquipmentPO, optimisation_result: SinglePortfolioResult) -> None:
        """
        Read the optimised schedule of an equipment and store it on the equipment itself.

        In forecast mode the schedule feeds ``id_po_for_orders`` and leaves the committed
        ``power`` and ``stored_energy`` untouched, since the optimisation is only run to build
        orders ahead of a market.

        :param equipment: Equipment to update.
        :type equipment: EquipmentPO
        :param optimisation_result: Solved optimisation holding the variable values.
        :type optimisation_result: SinglePortfolioResult
        """
        schedule = extract_equipment_schedule(equipment, optimisation_result)

        if self.parameters.use_forecast:
            equipment.id_po_for_orders = self._upsert_forecast(equipment.id_po_for_orders, schedule.power)
        else:
            equipment.power = self._upsert_forecast(equipment.power, schedule.power)
            if isinstance(equipment, (HydroPO, StoragePO)) and schedule.stored_energy is not None:
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
        if schedule.state_sequence is None:
            return

        execution_date = self.parameters.temporal.execution_date.to_datetime_string()

        if equipment.state_sequence is None:
            equipment.state_sequence = ScenarioMatrix()
        equipment.state_sequence.upsert(execution_date, schedule.state_sequence)

    def _empty_window_timeseries(self) -> Timeseries:
        """Zero-valued timeseries over the portfolio time window."""
        window = self.parameters.portfolio_time_window
        return Timeseries.from_index(min(window), self.parameters.temporal.timestep, max(window), default_value=0.0)

    def _sum_equipment_power(self, equipments: list[EquipmentPO]) -> Timeseries:
        """
        Sum the power of the given equipments over the portfolio time window.

        :param equipments: Every equipment of the portfolio, optimised or manually activated.
        :type equipments: list[EquipmentPO]
        :return: Aggregated power, zero where no equipment has a schedule.
        :rtype: Timeseries
        """
        start, end = min(self.parameters.portfolio_time_window), max(self.parameters.portfolio_time_window)
        power_ts = self._empty_window_timeseries()

        for equipment in equipments:
            if equipment.power:
                power_ts = power_ts + equipment.power.get_forecast(self.parameters.temporal.execution_date, start, end)

        return power_ts

    def _sum_upstream_energy(self, equipments: list[EquipmentPO]) -> Timeseries:
        """
        Sum the quantities cleared (or activated) upstream by the given equipments.

        Uses the same definition as the optimisation balance, see
        :meth:`~atlas.modules.portfolio_optimisation.input_objects.portfolio.PortfolioPO.get_upstream_energy`.

        :param equipments: Every equipment of the portfolio, optimised or manually activated.
        :type equipments: list[EquipmentPO]
        :return: Aggregated upstream commitment over the portfolio time window.
        :rtype: Timeseries
        """
        upstream_ts = self._empty_window_timeseries()

        for time in self.parameters.portfolio_time_window:
            upstream_ts.set_value(
                time,
                sum(PortfolioPO.get_upstream_energy(equipment, time, self.parameters) for equipment in equipments),
            )

        return upstream_ts

    def _upsert_forecast(
        self, matrix: ForecastingMatrix | LazyForecastingMatrix | None, timeseries: Timeseries
    ) -> ForecastingMatrix | LazyForecastingMatrix:
        """
        Write a forecast at the execution date, creating the matrix if the attribute is still empty.

        :param matrix: Existing forecasting matrix, or None if the object carries none yet.
        :type matrix: ForecastingMatrix | LazyForecastingMatrix | None
        :param timeseries: Values over the target times.
        :type timeseries: Timeseries
        :return: The matrix holding the new forecast.
        :rtype: ForecastingMatrix | LazyForecastingMatrix
        """
        execution_date = self.parameters.temporal.execution_date

        if matrix is None:
            return ForecastingMatrix().add(timeseries, execution_date)

        matrix.upsert(execution_date, timeseries)
        return matrix
