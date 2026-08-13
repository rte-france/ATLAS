"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pendulum import DateTime

from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.enums import StorageType
from atlas.solver.model_var import ModelVar
from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    from atlas.common.optimal_dispatch.input_objects.storage import StorageDispatchInput


class StorageDispatch:
    """
    Physical dispatch component for a single storage unit.

    Owns sell/buy power, binary sell/buy state, stored energy variables, and optionally
    fragment variables for piecewise-linear bid modelling.
    Handles physical constraints (level evolution, sell/buy separation, cycle balance)
    and fragment constraints (sum and bound). Does **not** handle reserves or objective terms.

    Typical usage::

        dispatch = StorageDispatch(equipment)
        dispatch.setup(model, parameters, nb_fragments=3)  # init vars + initial stock
        for time in time_window:
            dispatch.add_variables(time)                   # per-timestep decision variables
            dispatch.add_fragment_variables(time, max_p, min_p)
        for time in time_window:
            dispatch.add_constraints(model, time, parameters)
            dispatch.add_fragment_sum_constraints(time, power_sell, power_buy)
        dispatch.add_cycle_balance_constraint(model, time_window)  # non-EV only
    """

    def __init__(self, equipment: StorageDispatchInput) -> None:
        self._eq = equipment
        self._initial_stock: float = 0.0
        self._model: OptimisationModel = None  # type: ignore[assignment]
        self._nb_fragments: int = 0

        self.power_level_sell_var: ModelVar = None  # type: ignore[assignment]
        self.power_level_buy_var: ModelVar = None  # type: ignore[assignment]
        self.is_sell_var: ModelVar = None  # type: ignore[assignment]
        self.stored_energy_var: ModelVar = None  # type: ignore[assignment]

    def setup(self, model: OptimisationModel, parameters: AbstractModuleParameters, nb_fragments: int = 0) -> None:
        """
        Compute initial stock and create ModelVar objects.

        Must be called before :meth:`add_variables` or :meth:`add_constraints`.

        :param model: The optimisation model
        :param parameters: Module parameters — must expose ``temporal.timestep``,
            ``temporal.start_date``, ``temporal.execution_date``
        :param nb_fragments: Number of power fragments for piecewise-linear bid modelling.
            Pass 0 (default) when fragments are not used.
        :type nb_fragments: int
        """
        self._model = model
        self._nb_fragments = nb_fragments
        self._compute_initial_stock(parameters)
        self._setup_state_variables(model)

    def add_variables(self, time: DateTime) -> None:
        """
        Register decision variables for *time* in the model.

        :param time: The timestep for which to create variables
        :type time: DateTime
        """
        self.power_level_sell_var.set_model_var(time)
        self.power_level_buy_var.set_model_var(time)
        self.is_sell_var.set_model_var(time)
        self.stored_energy_var.set_model_var(time)

    def add_fragment_variables(self, time: DateTime, max_power: float, min_power: float) -> None:
        """
        Register fragment decision variables for *time* in the model.

        Creates ``nb_fragments`` sell fragments (≥ 0) and buy fragments (≤ 0), each
        bounded by ``max_power / nb_fragments`` and ``min_power / nb_fragments`` respectively.
        No-op when ``nb_fragments`` is 0.

        :param time: The timestep for which to create variables
        :type time: DateTime
        :param max_power: Maximum sell power at *time* (MW)
        :type max_power: float
        :param min_power: Minimum buy power at *time* (MW, negative)
        :type min_power: float
        """
        if self._nb_fragments == 0:
            return
        nb = self._nb_fragments
        for n in range(nb):
            self._model.add_continuous_variable(self._sell_n_key(time, n), 0, max_power / nb)
            self._model.add_continuous_variable(self._buy_n_key(time, n), min_power / nb, 0)

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
        nb = self._nb_fragments
        n = self._eq.name
        self._model.add_constraint(
            power_sell == sum(self._model.get_variable(self._sell_n_key(time, i)) for i in range(nb)),
            f"sell_fragment_sum_{time}_{n}",
        )
        self._model.add_constraint(
            power_buy == sum(self._model.get_variable(self._buy_n_key(time, i)) for i in range(nb)),
            f"buy_fragment_sum_{time}_{n}",
        )

    def get_fragment_sell_var(self, time: DateTime, n: int):
        """
        Return the *n*-th sell fragment variable at *time*.

        :param time: The timestep
        :type time: DateTime
        :param n: Fragment index
        :type n: int
        """
        return self._model.get_variable(self._sell_n_key(time, n))

    def get_fragment_buy_var(self, time: DateTime, n: int):
        """
        Return the *n*-th buy fragment variable at *time*.

        :param time: The timestep
        :type time: DateTime
        :param n: Fragment index
        :type n: int
        """
        return self._model.get_variable(self._buy_n_key(time, n))

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

        power_sell = self.power_level_sell_var.get_value(time)
        power_buy = self.power_level_buy_var.get_value(time)
        stored_energy = self.stored_energy_var.get_value(time)

        displacement = int(eq.displacement_energy.get_value(time)) if eq.displacement_energy else 0
        displacement_prev = int(eq.displacement_energy.get_value(prev_time)) if eq.displacement_energy else 0

        # power_buy is negative (charging draws power from grid); energy added = -buy * efficiency
        energy_delta = (
            -power_buy * (eq.charge_efficiency or 1.0) * dt_h
            - power_sell * dt_h / (eq.discharge_efficiency or 1.0)
            + (displacement - displacement_prev)
        )

        if time == parameters.temporal.start_date:
            model.add_constraint(
                stored_energy == self._initial_stock * energy_ratio + energy_delta,
                f"storage_level_evol_{time}_{n}",
            )
        else:
            prev_stored_energy = self.stored_energy_var.get_value(prev_time)
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

    def add_cycle_balance_constraint(self, model: OptimisationModel, time_window: list[DateTime]) -> None:
        """
        Add the cycle balance constraint over *time_window*.

        Ensures the storage returns to its initial state of charge at the end of the
        optimisation horizon: total energy charged equals total energy discharged
        (accounting for efficiencies).

        In DA, electric vehicles use a displacement-energy fill-up constraint instead —
        callers are responsible for not invoking this method for EV units in that context.

        ``Σ (−power_buy) × charge_efficiency = Σ power_sell / discharge_efficiency``

        :param model: The optimisation model
        :param time_window: Ordered list of timesteps covering the optimisation horizon
        :type time_window: list[DateTime]
        """

        eq = self._eq
        charge_eff = eq.charge_efficiency or 1.0
        discharge_eff = eq.discharge_efficiency or 1.0

        model.add_constraint(
            sum(-self.power_level_buy_var.get_value(t) for t in time_window) * charge_eff
            == sum(self.power_level_sell_var.get_value(t) for t in time_window) / discharge_eff,
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
        eff = eq.discharge_efficiency or 1.0
        if eq.storage_type == StorageType.ELECTRIC_VEHICLE:
            return (eq.is_v2g or 0.0) * max_p * eff
        return max_p * eff

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
        return eq.minimum_power.get_value(time) / (eq.charge_efficiency or 1.0)

    @property
    def name(self) -> str:
        return self._eq.name

    def _sell_n_key(self, time: DateTime, n: int) -> str:
        return f"{self._eq.name}_power_level_sell_n_{n}_{time}"

    def _buy_n_key(self, time: DateTime, n: int) -> str:
        return f"{self._eq.name}_power_level_buy_n_{n}_{time}"

    def _compute_initial_stock(self, parameters: AbstractModuleParameters) -> None:
        eq = self._eq
        temporal = parameters.temporal
        prev = temporal.start_date - temporal.timestep
        default = eq.maximum_energy.get_value(prev) * (eq.storage_initial_level or 0.0)

        if eq.stored_energy is None:
            self._initial_stock = default
            return

        forecast = eq.stored_energy.get_forecast(
            temporal.execution_date,
            temporal.start_date.subtract(days=2),
            prev,
            temporal.timestep,
        )
        self._initial_stock = forecast.get_value(prev) if len(forecast) > 0 else default

    def _setup_state_variables(self, model: OptimisationModel) -> None:
        eq = self._eq
        n = eq.name

        self.power_level_sell_var = ModelVar(
            getter=lambda time: model.get_variable(f"{n}_power_level_sell_{time}"),
            setter=lambda time: model.add_continuous_variable(
                f"{n}_power_level_sell_{time}", 0, eq.maximum_power.get_value(time)
            ),
        )
        self.power_level_buy_var = ModelVar(
            getter=lambda time: model.get_variable(f"{n}_power_level_buy_{time}"),
            setter=lambda time: model.add_continuous_variable(
                f"{n}_power_level_buy_{time}", eq.minimum_power.get_value(time), 0
            ),
        )
        self.is_sell_var = ModelVar(
            getter=lambda time: model.get_variable(f"{n}_is_sell_{time}"),
            setter=lambda time: model.add_boolean_variable(f"{n}_is_sell_{time}"),
        )
        self.stored_energy_var = ModelVar(
            getter=lambda time: model.get_variable(f"{n}_stored_energy_{time}"),
            setter=lambda time: model.add_continuous_variable(
                f"{n}_stored_energy_{time}",
                eq.minimum_state_of_charge.get_value(time) * eq.maximum_energy.get_value(time),
                eq.maximum_energy.get_value(time),
            ),
        )

    def _add_sell_buy_separation(self, model: OptimisationModel, time: DateTime) -> None:
        n = self._eq.name
        is_sell = self.is_sell_var.get_value(time)
        power_sell = self.power_level_sell_var.get_value(time)
        power_buy = self.power_level_buy_var.get_value(time)

        model.add_constraint(power_sell <= self.effective_max_sell(time) * is_sell, f"relative_power_max_{time}_{n}")
        model.add_constraint(
            power_buy >= self.effective_min_buy(time) * (1 - is_sell), f"relative_power_min_{time}_{n}"
        )
