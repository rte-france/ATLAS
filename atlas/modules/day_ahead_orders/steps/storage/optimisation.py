"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import atlas.config as cfg
from atlas.common.optimal_dispatch.dispatch.storage import StorageDispatch
from atlas.common.optimal_dispatch.steps import AbstractOptimStep
from atlas.enums import StorageType
from atlas.modules.day_ahead_orders.input_objects.storage import StorageDAO
from atlas.solver.models import SolverOptions
from atlas.solver.solver_interface import OptimisationModel
from atlas.timing import generate_datetimes

if TYPE_CHECKING:
    from pendulum import DateTime

    from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters


@dataclass
class StorageOptimisationResult:
    """
    Raw LP output for one storage unit — solved variable values, nothing else.

    Deliberately free of business objects: this crosses the process boundary when
    multiprocessing is enabled, so it holds plain floats rather than orders (which would
    drag the whole equipment/portfolio/market-area graph through pickle, and come back
    referencing copies instead of the dataset's own objects). Orders are built from it in
    the main process by :func:`~atlas.modules.day_ahead_orders.steps.storage.orders.build_storage_bids`.

    :param sell_volumes: Sell (discharge) volume per timestep, in MW, positive
    :type sell_volumes: dict[DateTime, float]
    :param buy_volumes: Buy (charge) volume per timestep, in MW, positive
    :type buy_volumes: dict[DateTime, float]
    """

    sell_volumes: dict[DateTime, float] = field(default_factory=dict)
    buy_volumes: dict[DateTime, float] = field(default_factory=dict)


class StorageDAOStep(AbstractOptimStep[StorageDAO, "DayAheadOrdersParameters"]):
    """
    Step owning the day-ahead bidding optimisation of a single storage unit.

    Composes :class:`StorageDispatch` for the physical variables and constraints and adds
    what is specific to day-ahead order formulation: the fragment-priced profit objective,
    and — for electric vehicles — the displacement-energy compensation constraint that
    replaces the cycle balance.

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
                self.dispatch.add_sell_buy_separation(model, time)
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


def optimize_single_storage(
    storage: StorageDAO,
    parameters: DayAheadOrdersParameters,
    local_timewindow: list[DateTime],
) -> StorageOptimisationResult | None:
    """
    Build and solve the day-ahead bidding model of a single storage unit.

    Runs either in a worker process or in the main process, depending on the
    multiprocessing parameters.

    :param storage: Storage unit to optimise
    :type storage: StorageDAO
    :param parameters: Optimisation parameters
    :type parameters: DayAheadOrdersParameters
    :param local_timewindow: Timesteps of the day-ahead delivery window
    :type local_timewindow: list[DateTime]
    :return: Solved volumes, or ``None`` when the unit is skipped or the solve fails
    :rtype: StorageOptimisationResult | None
    """
    try:
        if storage.maximum_energy.filter(item=local_timewindow, inplace=False).max() <= 0:
            cfg.logger.debug(f"Equipment {storage.name} avoided, as its maximum_energy is 0")
            return None

        settings = _fragment_settings(storage, parameters)
        if settings is None:
            cfg.logger.error(f"equipment {storage.name} has an unsupported storage type {storage.storage_type}")
            return None
        nb_fragments, smoothing_factor = settings

        cfg.logger.debug(f"Optimizing storage equipment {storage.name}")

        # the unit optimises over a horizon extended by its own lookahead, so that the orders it
        # submits for the delivery day account for what it will need on the following hours
        time_window = generate_datetimes(
            parameters.temporal.start_date,
            parameters.temporal.end_date + storage.additional_hours - parameters.temporal.timestep,
            parameters.temporal.timestep,
        )

        model = OptimisationModel(
            parameters.solver.solver_name,
            f"Optimization of the storage unit {storage.name}",
            SolverOptions(
                presolve=parameters.solver.use_presolve,
                duality_gap=parameters.solver.duality_gap,
                time_limit=parameters.solver.timeout,
            ),
        )
        model.set_direction("maximize")

        step = StorageDAOStep(storage, time_window, nb_fragments, smoothing_factor)
        step.add_variables(model, parameters)
        step.add_constraints(model, parameters)
        step.add_objective(model, parameters, _price_forecasts(storage, time_window, parameters))

        if parameters.solver.export_lp:
            lp_dir = parameters.get_lp_dir()
            lp_dir.mkdir(parents=True, exist_ok=True)
            model.export_model(lp_dir / f"storage_{storage.name}.lp")

        model.solve()

        result = StorageOptimisationResult()
        for time in time_window:
            if time >= parameters.temporal.end_date:
                break
            result.sell_volumes[time] = round(step.dispatch.power_level_sell_var.get_value(time).solution_value(), 2)
            # buy power is negative in the dispatch convention, orders are expressed as positive volumes
            result.buy_volumes[time] = round(-step.dispatch.power_level_buy_var.get_value(time).solution_value(), 2)

        return result

    except Exception as e:
        cfg.logger.error(f"Optimization failed for storage {storage.name}: {e}")
        return None


def _fragment_settings(storage: StorageDAO, parameters: DayAheadOrdersParameters) -> tuple[int, float] | None:
    """Return the (nb_fragments, smoothing_factor) pair configured for the unit's storage type."""
    mapping: dict[StorageType | None, tuple[int, float]] = {
        StorageType.BATTERY: (parameters.battery_nb_fragments, parameters.battery_smoothing_factor),
        StorageType.PUMPED_HYDRAULIC_STORAGE: (
            parameters.pumped_hydraulic_nb_fragments,
            parameters.pumped_hydraulic_smoothing_factor,
        ),
        StorageType.ELECTRIC_VEHICLE: (
            parameters.electric_vehicle_nb_fragments,
            parameters.electric_vehicle_smoothing_factor,
        ),
    }
    return mapping.get(storage.storage_type)


def _price_forecasts(
    storage: StorageDAO, time_window: list[DateTime], parameters: DayAheadOrdersParameters
) -> dict[DateTime, float]:
    """Medium price forecast of the unit's market area over its optimisation horizon."""
    price_forecast_medium = storage.portfolio.market_area.price_forecast_medium
    if price_forecast_medium is None:
        raise AttributeError(f"{storage.portfolio.market_area.name} has no attribute 'price_forecast_medium'")

    forecast = price_forecast_medium.get_forecast(
        parameters.temporal.execution_date,
        parameters.temporal.start_date,
        time_window[-1],
        parameters.temporal.timestep,
    )
    return {time: forecast.get_value(time) for time in time_window}
