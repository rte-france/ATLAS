"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.common.optimal_dispatch.dispatch.storage import StorageDispatch
from atlas.common.optimal_dispatch.steps import AbstractOptimStep
from atlas.enums import StorageType
from atlas.modules.day_ahead_orders.input_objects.storage import StorageDAO

if TYPE_CHECKING:
    from pendulum import DateTime

    from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
    from atlas.solver.solver_interface import OptimisationModel


class StorageDAOStep(AbstractOptimStep[StorageDAO, "DayAheadOrdersParameters"]):
    """
    Step owning the day-ahead bidding optimisation of a single storage unit.

    Composes :class:`StorageDispatch` for the physical variables and constraints and adds
    what is specific to day-ahead order formulation: the fragment-priced profit objective,
    and — for electric vehicles — the V2G sell/buy separation and the displacement-energy
    compensation constraint that replaces the cycle balance.

    Buy power follows the dispatch sign convention: ``power_level_buy`` is **negative**
    when the unit charges. Callers reading purchased volumes must negate it.

    :param equipment: Storage unit to optimise
    :type equipment: StorageDAO
    :param time_window: Ordered timesteps of the unit's optimisation horizon
    :type time_window: list[DateTime]
    :param nb_fragments: Number of price fragments used to build the orders
    :type nb_fragments: int
    :param smoothing_factor: Extra-cost coefficient applied to successive fragments
    :type smoothing_factor: float
    """

    def __init__(
        self,
        equipment: StorageDAO,
        time_window: list[DateTime],
        nb_fragments: int,
        smoothing_factor: float,
    ) -> None:
        super().__init__(equipment)
        self.dispatch = StorageDispatch(equipment)
        self._time_window = time_window
        self._nb_fragments = nb_fragments
        self._smoothing_factor = smoothing_factor

    def add_variables(self, model: OptimisationModel, parameters: DayAheadOrdersParameters) -> None:
        eq = self.equipment
        self.dispatch.setup(model, parameters, self._nb_fragments)

        for time in self._time_window:
            self.dispatch.add_variables(time)
            self.dispatch.add_fragment_variables(
                time, eq.maximum_power.get_value(time), eq.minimum_power.get_value(time)
            )

    def add_constraints(self, model: OptimisationModel, parameters: DayAheadOrdersParameters) -> None:
        eq = self.equipment
        is_ev = eq.storage_type == StorageType.ELECTRIC_VEHICLE

        for time in self._time_window:
            self.dispatch.add_constraints(model, time, parameters)
            if is_ev:
                self._add_v2g_separation(model, time)
            self.dispatch.add_fragment_sum_constraints(
                time,
                self.dispatch.power_level_sell_var.get_value(time),
                self.dispatch.power_level_buy_var.get_value(time),
            )

        if is_ev:
            self._add_displacement_compensation(model, parameters)
        else:
            self.dispatch.add_cycle_balance_constraint(model, self._time_window, parameters)

    def add_objective(
        self,
        model: OptimisationModel,
        parameters: DayAheadOrdersParameters,
        price_forecasts: dict | None = None,
    ) -> None:
        """
        Maximise the profit of the unit over its horizon.

        Each fragment is priced with an increasing penalty (``smoothing_factor``) so that
        the solver spreads volumes over fragments instead of bidding everything at the
        market price, which is what makes the resulting orders a price/volume curve.
        """
        prices = price_forecasts or {}
        nb = self._nb_fragments
        dt_h = parameters.temporal.timestep.total_hours()

        for time in self._time_window:
            price = prices.get(time, 0.0)
            for n in range(nb):
                sell_n = self.dispatch.get_fragment_sell_var(time, n)
                buy_n = self.dispatch.get_fragment_buy_var(time, n)
                if nb == 1:
                    model.add_objective(price * (sell_n + buy_n) * dt_h)
                else:
                    model.add_objective(
                        price * (1 - n * self._smoothing_factor / (nb - 1)) * sell_n * dt_h
                        + price * (1 + n * self._smoothing_factor / (nb - 1)) * buy_n * dt_h
                    )

    def _add_v2g_separation(self, model: OptimisationModel, time: DateTime) -> None:
        """
        Sell/buy separation for electric vehicles — a unit cannot charge and discharge at once.

        :class:`StorageDispatch.add_constraints` skips it for EVs, leaving the formulation to
        the calling module. Day-ahead gates the buy side on ``is_sell * is_v2g`` rather than on
        ``is_sell`` alone: a non-V2G vehicle can never sell, so ``is_sell`` is unconstrained for
        it and must not be allowed to block charging.
        """
        eq = self.equipment
        is_sell = self.dispatch.is_sell_var.get_value(time)

        model.add_constraint(
            self.dispatch.power_level_sell_var.get_value(time) <= self.dispatch.effective_max_sell(time) * is_sell,
            f"relative_power_max_{time}_{eq.name}",
        )
        model.add_constraint(
            self.dispatch.power_level_buy_var.get_value(time)
            >= self.dispatch.effective_min_buy(time) * (1 - is_sell * (eq.is_v2g or 0.0)),
            f"relative_power_min_{time}_{eq.name}",
        )

    def _add_displacement_compensation(self, model: OptimisationModel, parameters: DayAheadOrdersParameters) -> None:
        """
        Force purchases to cover the energy the vehicles spend driving over the horizon.

        Day-ahead deliberately does not apply the cycle balance to electric vehicles: the
        vehicle is free to end the horizon above or below its initial state of charge, only
        the driving has to be paid back. ``ev_energy_coef`` oversizes the requirement so
        that enough buy orders are formulated.
        """
        eq = self.equipment
        assert eq.displacement_energy is not None, f"displacement_energy is required for ElectricVehicle {eq.name}"

        required_energy = (
            eq.displacement_energy.get_value(self._time_window[-1])
            - eq.displacement_energy.get_value(self._time_window[0] - parameters.temporal.timestep)
        ) * parameters.ev_energy_coef

        model.add_constraint(
            sum(-self.dispatch.power_level_buy_var.get_value(time) for time in self._time_window) * eq.charge_efficiency
            >= required_energy,
            f"DisplacementEnergy_compensation_for_{eq.name}",
        )
