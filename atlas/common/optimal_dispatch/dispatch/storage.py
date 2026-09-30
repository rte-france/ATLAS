"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pendulum import DateTime

from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.enums import StorageType, VariableType
from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    from collections.abc import Iterable

    from atlas.common.optimal_dispatch.input_objects.storage import StorageDispatchInput
    from atlas.solver.temporal_variable import TemporalVariable


class StorageDispatch:
    """
    Physical dispatch component for a single storage unit.

    Owns sell/buy power, binary sell/buy state, stored energy temporal variables, and optionally
    fragment temporal variables for piecewise-linear bid modelling. The stored energy is fixed
    to the initial stock at the timestep preceding the horizon.
    Handles physical constraints (level evolution, sell/buy separation, cycle balance)
    and fragment constraints (sum and bound). Does **not** handle reserves or objective terms.

    Typical usage::

        dispatch = StorageDispatch(equipment)
        dispatch.setup(model, parameters, nb_fragments=3)  # declare vars + fix initial stock
        dispatch.add_variables(time_window)                # decision and fragment variables
        for time in time_window:
            dispatch.add_constraints(model, time, parameters)
            dispatch.add_fragment_sum_constraints(time, power_sell, power_buy)
        dispatch.add_cycle_balance_constraint(model, time_window, parameters)
    """

    def __init__(self, equipment: StorageDispatchInput) -> None:
        self._eq = equipment
        self._initial_stock: float = 0.0
        self._model: OptimisationModel
        self._nb_fragments: int = 0

        self.power_level_sell: TemporalVariable
        self.power_level_buy: TemporalVariable
        self.is_sell: TemporalVariable
        self.stored_energy: TemporalVariable
        self.power_level_sell_n: list[TemporalVariable] = []
        self.power_level_buy_n: list[TemporalVariable] = []

    def setup(self, model: OptimisationModel, parameters: AbstractModuleParameters, nb_fragments: int = 0) -> None:
        """
        Compute the initial stock and declare the temporal variables.

        Must be called before :meth:`add_variables` or :meth:`add_constraints`.

        :param model: The optimisation model
        :param parameters: Module parameters
        :param nb_fragments: Number of power fragments for piecewise-linear bid modelling.
            Pass 0 (default) when fragments are not used.
        :type nb_fragments: int
        """
        self._nb_fragments = nb_fragments
        self._compute_initial_stock(parameters)
        self._declare_variables(model)
        temporal = parameters.temporal
        self.stored_energy.fix(temporal.start_date - temporal.timestep, self._initial_stock)

    def add_variables(self, times: Iterable[DateTime]) -> None:
        """
        Register decision variables for *times* in the model.

        Also creates ``nb_fragments`` sell fragments (≥ 0) and buy fragments (≤ 0) per timestep,
        each bounded by ``maximum_power / nb_fragments`` and ``minimum_power / nb_fragments``.

        :param times: The timesteps for which to create variables
        :type times: Iterable[DateTime]
        """
        times = list(times)
        for variable in (
            self.power_level_sell,
            self.power_level_buy,
            self.is_sell,
            self.stored_energy,
            *self.power_level_sell_n,
            *self.power_level_buy_n,
        ):
            variable.add_all(times)

    def add_fragment_sum_constraints(self, time: DateTime, power_sell, power_buy) -> None:
        """
        Add constraints linking aggregate sell/buy to the sum of their fragments.

        ``power_sell == Σ sell_n[i]``  and  ``power_buy == Σ buy_n[i]``

        No-op when ``nb_fragments`` is 0.

        :param time: Current timestep
        :type time: DateTime
        :param power_sell: Aggregate sell variable at *time*
        :param power_buy: Aggregate buy variable at *time*
        """
        if self._nb_fragments == 0:
            return
        n = self._eq.name
        model = self._model
        model.add_constraint(
            power_sell == sum(fragment[time] for fragment in self.power_level_sell_n),
            f"sell_fragment_sum_{time}_{n}",
        )
        model.add_constraint(
            power_buy == sum(fragment[time] for fragment in self.power_level_buy_n),
            f"buy_fragment_sum_{time}_{n}",
        )

    def add_storage_level_evolution(
        self, model: OptimisationModel, time: DateTime, parameters: AbstractModuleParameters
    ) -> None:
        """
        Add only the storage level evolution constraint for *time*.

        Use when you need the level-tracking constraint without sell/buy separation
        (e.g. when the calling module adds its own separation logic).

        :param model: The optimisation model
        :param time: Current timestep
        :type time: DateTime
        :param parameters: Module parameters
        """
        eq = self._eq
        n = eq.name
        ts = parameters.temporal.timestep
        prev_time = time - ts
        dt_h = ts.total_hours()

        max_energy = eq.maximum_energy.get_value(time)
        max_energy_prev = eq.maximum_energy.get_value(prev_time)
        energy_ratio = max_energy / max_energy_prev if max_energy_prev > 0 else 1.0

        power_sell = self.power_level_sell[time]
        power_buy = self.power_level_buy[time]
        stored_energy = self.stored_energy[time]
        prev_stored_energy = self.stored_energy[prev_time]

        displacement = int(eq.displacement_energy.get_value(time)) if eq.displacement_energy else 0
        displacement_prev = int(eq.displacement_energy.get_value(prev_time)) if eq.displacement_energy else 0

        # power_buy is negative (charging draws power from grid); energy added = -buy * efficiency
        energy_delta = (
            -power_buy * eq.charge_efficiency * dt_h
            - power_sell * dt_h / eq.discharge_efficiency
            - (displacement - displacement_prev)
        )

        # at start_date, the previous stored energy is the fixed initial stock
        model.add_constraint(
            stored_energy == prev_stored_energy * energy_ratio + energy_delta,
            f"storage_level_evol_{time}_{n}",
        )

    def add_constraints(self, model: OptimisationModel, time: DateTime, parameters: AbstractModuleParameters) -> None:
        """
        Add all physical constraints for *time*.

        For electric vehicles, sell/buy separation is left to the calling module —
        the DA fill-up and the PO reserve fill-up each govern it differently.

        :param model: The optimisation model
        :param time: Current timestep
        :type time: DateTime
        :param parameters: Module parameters
        """
        self.add_storage_level_evolution(model, time, parameters)
        if self._eq.storage_type != StorageType.ELECTRIC_VEHICLE:
            self._add_sell_buy_separation(model, time)

    def add_cycle_balance_constraint(
        self, model: OptimisationModel, time_window: list[DateTime], parameters: AbstractModuleParameters
    ) -> None:
        """
        Add the cycle balance constraint over *time_window*.

        Ensures the storage returns to its initial state of charge at the end of the
        optimisation horizon: total energy charged equals total energy discharged
        (accounting for efficiencies), plus the displacement energy accumulated over
        the window.

        ``Σ (−power_buy) × charge_efficiency × Δt
        = Σ power_sell × Δt / discharge_efficiency + Δdisplacement``

        The displacement term is the telescoped sum of the per-timestep contributions of
        :meth:`add_storage_level_evolution`, i.e.
        ``displacement[t_last] − displacement[t_first − Δt]``. Since that method *subtracts*
        the per-timestep displacement from the stored energy, imposing ``E_last == E_first``
        puts it on the charged side here: a fleet that drove must charge more than it
        discharged, by exactly what it spent on the road.

        Getting this sign wrong does not make the model infeasible — it silently moves the
        solution, leaving the unit ``2 × Δdisplacement`` below its initial state of charge.

        DA does not apply this constraint to electric vehicles. It bounds purchases from
        below instead (``Σ purchased × charge_efficiency ≥ Δdisplacement × ev_energy_coef``),
        which only guarantees the driving is paid back — the vehicle is free to end the
        horizon above or below its initial state of charge. That is a strictly weaker
        constraint, not a variant of this one, so callers must not invoke this method for
        EV units in a DA context.

        :param model: The optimisation model
        :param time_window: Ordered list of timesteps covering the optimisation horizon
        :type time_window: list[DateTime]
        :param parameters: Module parameters
        """

        eq = self._eq
        ts = parameters.temporal.timestep
        dt_h = ts.total_hours()
        charge_eff = eq.charge_efficiency
        discharge_eff = eq.discharge_efficiency

        displacement_delta = 0
        if eq.displacement_energy:
            displacement_delta = int(eq.displacement_energy.get_value(time_window[-1])) - int(
                eq.displacement_energy.get_value(time_window[0] - ts)
            )

        model.add_constraint(
            sum(-self.power_level_buy[t] for t in time_window) * charge_eff * dt_h
            == sum(self.power_level_sell[t] for t in time_window) * dt_h / discharge_eff + displacement_delta,
            f"cycle_balance_{eq.name}",
        )

    def effective_max_sell(self, time: DateTime) -> float:
        """
        Effective maximum sell (discharge) power at *time*, accounting for discharge efficiency
        and V2G gating for electric vehicles.

        :param time: The timestep
        :type time: DateTime
        :return: Upper bound on sell power (MW)
        :rtype: float
        """
        eq = self._eq
        max_p = eq.maximum_power.get_value(time)
        if eq.storage_type == StorageType.ELECTRIC_VEHICLE:
            return (eq.is_v2g or 0.0) * max_p
        return max_p

    def effective_min_buy(self, time: DateTime) -> float:
        """
        Effective minimum buy (charge) power at *time* (negative convention),
        accounting for charge efficiency.

        :param time: The timestep
        :type time: DateTime
        :return: Lower bound on buy power (MW, negative)
        :rtype: float
        """
        eq = self._eq
        return eq.minimum_power.get_value(time)

    @property
    def name(self) -> str:
        return self._eq.name

    def _compute_initial_stock(self, parameters: AbstractModuleParameters) -> None:
        eq = self._eq
        temporal = parameters.temporal
        prev = temporal.start_date - temporal.timestep
        default = eq.maximum_energy.get_value(prev) * (eq.storage_initial_level or 0.0)

        # an empty matrix raises inside get_forecast, so it is screened out here rather
        # than relying on the empty-forecast fallback below
        if eq.stored_energy is None or len(eq.stored_energy) == 0:
            self._initial_stock = default
            return

        forecast = eq.stored_energy.get_forecast(
            temporal.execution_date,
            temporal.start_date.subtract(days=2),
            prev,
            temporal.timestep,
        )
        self._initial_stock = forecast.get_value(prev) if len(forecast) > 0 else default

    def _declare_variables(self, model: OptimisationModel) -> None:
        eq = self._eq
        n = eq.name
        nb = self._nb_fragments
        self._model = model

        self.power_level_sell = model.add_temporal_variable(
            f"{n}_power_level_sell", lower_bound=0, upper_bound=eq.maximum_power
        )
        self.power_level_buy = model.add_temporal_variable(
            f"{n}_power_level_buy", lower_bound=eq.minimum_power, upper_bound=0
        )
        self.is_sell = model.add_temporal_variable(f"{n}_is_sell", variable_type=VariableType.BOOLEAN)
        self.stored_energy = model.add_temporal_variable(
            f"{n}_stored_energy",
            lower_bound=lambda time: eq.minimum_state_of_charge.get_value(time) * eq.maximum_energy.get_value(time),
            upper_bound=eq.maximum_energy,
        )
        self.power_level_sell_n = [
            model.add_temporal_variable(
                f"{n}_power_level_sell_n_{i}",
                lower_bound=0,
                upper_bound=lambda time: eq.maximum_power.get_value(time) / nb,
            )
            for i in range(nb)
        ]
        self.power_level_buy_n = [
            model.add_temporal_variable(
                f"{n}_power_level_buy_n_{i}",
                lower_bound=lambda time: eq.minimum_power.get_value(time) / nb,
                upper_bound=0,
            )
            for i in range(nb)
        ]

    def _add_sell_buy_separation(self, model: OptimisationModel, time: DateTime) -> None:
        n = self._eq.name
        is_sell = self.is_sell[time]
        power_sell = self.power_level_sell[time]
        power_buy = self.power_level_buy[time]

        model.add_constraint(power_sell <= self.effective_max_sell(time) * is_sell, f"relative_power_max_{time}_{n}")
        model.add_constraint(
            power_buy >= self.effective_min_buy(time) * (1 - is_sell), f"relative_power_min_{time}_{n}"
        )
