"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
from pendulum import DateTime

import atlas.config as cfg
from atlas.common.optimal_dispatch.dispatch.storage import StorageDispatch
from atlas.enums import ComplementDirection, CouplingType, OrderType, Product, StorageType
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
from atlas.modules.day_ahead_orders.input_objects.order_coupling import OrderCouplingDAO
from atlas.modules.day_ahead_orders.input_objects.storage import StorageDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.steps.storage.optimisation_result import StorageOptimisationResult
from atlas.solver.models import SolverOptions
from atlas.solver.solver_interface import OptimisationModel
from atlas.timing import generate_datetimes

if TYPE_CHECKING:
    pass


class StorageOrders:
    """
    Single entry point for storage unit order formulation in the day-ahead context.

    Combines the LP solve and order construction in one object, following the
    pattern: each equipment runs an optimisation then builds its orders.

    Call :meth:`run` for the full pipeline, or :meth:`solve` + :meth:`build_orders`
    when solving in a worker process and building orders in the main process.

    :param parameters: Module parameters.
    :param local_timewindow: Timesteps within the local optimisation window.

    Example::

        storage_orders = StorageOrders(parameters, local_timewindow)
        orders, couplings = storage_orders.run(storage)
    """

    def __init__(self, parameters: DayAheadOrdersParameters, local_timewindow: list[DateTime]) -> None:
        self._parameters = parameters
        self._local_timewindow = local_timewindow
        self._dispatch: StorageDispatch | None = None
        self._time_frame: list[DateTime] = []

    def run(self, storage: StorageDAO) -> tuple[list[OrderDAO], list[OrderCouplingDAO]]:
        """Solve the LP then build and return orders."""
        raw = self.solve(storage)
        return self.build_orders(storage, raw)

    def solve(self, storage: StorageDAO) -> StorageOptimisationResult:
        """
        Build and solve the LP for a storage unit.

        :param storage: Storage unit to optimise.
        :return: Raw LP solver output.
        :rtype: StorageOptimisationResult
        """
        nb_fragments, _ = self._fragment_config(storage)
        self._time_frame = generate_datetimes(
            self._parameters.temporal.start_date,
            self._parameters.temporal.end_date + storage.additional_hours - self._parameters.temporal.timestep,
            self._parameters.temporal.timestep,
        )
        self._dispatch = StorageDispatch(storage)

        solver_options = SolverOptions(
            presolve=self._parameters.solver.use_presolve,
            duality_gap=self._parameters.solver.duality_gap,
            time_limit=self._parameters.solver.timeout,
        )
        model = OptimisationModel(
            self._parameters.solver.solver_name,
            f"Optimization of the storage unit {storage.name}",
            solver_options,
        )

        self._add_variables(model, storage, nb_fragments)
        self._add_constraints(model, storage)
        self._add_objective(model, storage)

        if self._parameters.solver.export_lp:
            lp_dir = self._parameters.get_lp_dir()
            lp_dir.mkdir(parents=True, exist_ok=True)
            model.export_model(str(lp_dir / f"storage_{storage.name}.lp"))

        model.solve()
        return self._extract_result()

    def build_orders(
        self,
        storage: StorageDAO,
        raw: StorageOptimisationResult,
    ) -> tuple[list[OrderDAO], list[OrderCouplingDAO]]:
        """
        Build market orders from raw LP output.

        :param storage: Storage unit.
        :param raw: Raw LP solver output as returned by :meth:`solve`.
        :return: Orders and order couplings.
        :rtype: tuple[list[OrderDAO], list[OrderCouplingDAO]]
        """
        buy_submitted_volumes = Timeseries.from_values(
            self._parameters.temporal.start_date, self._parameters.temporal.timestep, list(raw.buy_volumes.values())
        )
        sell_submitted_volumes = Timeseries.from_values(
            self._parameters.temporal.start_date, self._parameters.temporal.timestep, list(raw.sell_volumes.values())
        )

        psale, ppurchase = self._price_calculation(storage, raw)

        orders: list[OrderDAO] = []
        coupling_orders: list[OrderDAO] = []

        for t, qa in raw.buy_volumes.items():
            order = self._create_spot_order(OrderType.Buy, storage, t, qa, ppurchase)
            orders.append(order)
            coupling_orders.append(order)

        for t, qv in raw.sell_volumes.items():
            order = self._create_spot_order(OrderType.Sell, storage, t, qv, psale)
            orders.append(order)
            coupling_orders.append(order)

        order_couplings = [
            self._create_coupling(storage, raw, buy_submitted_volumes, sell_submitted_volumes, coupling_orders)
        ]

        return orders, order_couplings

    def compute_submitted_volumes(self, raw: StorageOptimisationResult) -> tuple[Timeseries, Timeseries]:
        """
        Return buy and sell submitted volume timeseries from raw LP output.

        :param raw: Raw LP solver output.
        :return: (buy_submitted_volumes, sell_submitted_volumes) in MW.
        :rtype: tuple[Timeseries, Timeseries]
        """
        buy = Timeseries.from_values(
            self._parameters.temporal.start_date, self._parameters.temporal.timestep, list(raw.buy_volumes.values())
        )
        sell = Timeseries.from_values(
            self._parameters.temporal.start_date, self._parameters.temporal.timestep, list(raw.sell_volumes.values())
        )
        return buy, sell

    def compute_variable_cost(self, storage: StorageDAO, raw: StorageOptimisationResult) -> Timeseries:
        """
        Derive variable cost timeseries from LP result and price forecast.

        :param storage: Storage unit.
        :param raw: Raw LP solver output.
        :return: Variable cost timeseries.
        :rtype: Timeseries
        """
        psale, ppurchase = self._price_calculation(storage, raw)
        if ppurchase != 0:
            variable_cost = round(ppurchase, 2)
        elif storage.discharge_efficiency != 0 and storage.charge_efficiency != 0:
            variable_cost = round(psale * storage.discharge_efficiency * storage.charge_efficiency, 2)
        else:
            variable_cost = round(psale, 2)
            cfg.logger.warning(
                f"ChargeEfficiency or DischargeEfficiency is null for equipment {storage.name}. "
                "This is not supposed to be the case, as the default value for these is 1 and not 0"
            )
        return Timeseries.from_values(
            self._parameters.temporal.start_date,
            self._parameters.temporal.timestep,
            [variable_cost] * len(self._local_timewindow),
        )

    # ------------------------------------------------------------------ #
    #  LP model building (previously in StorageDAOStep)                   #
    # ------------------------------------------------------------------ #

    def _add_variables(self, model: OptimisationModel, storage: StorageDAO, nb_fragments: int) -> None:
        assert self._dispatch is not None
        self._dispatch.setup(model, self._parameters, nb_fragments)
        for t in self._time_frame:
            self._dispatch.add_variables(t)
            max_power = storage.maximum_power.get_value(t)
            min_power = storage.minimum_power.get_value(t)
            self._dispatch.add_fragment_variables(t, max_power, min_power)

    def _add_constraints(self, model: OptimisationModel, storage: StorageDAO) -> None:
        assert self._dispatch is not None
        for t in self._time_frame:
            max_power = storage.maximum_power.get_value(t)
            min_power = storage.minimum_power.get_value(t)
            power_sell = self._dispatch.power_level_sell_var.get_value(t)
            power_buy = self._dispatch.power_level_buy_var.get_value(t)
            is_sell = self._dispatch.is_sell_var.get_value(t)

            self._dispatch.add_fragment_sum_constraints(t, power_sell, power_buy)
            self._dispatch.add_storage_level_evolution(model, t, self._parameters)

            if storage.storage_type == StorageType.ELECTRIC_VEHICLE:
                model.add_constraint(
                    power_sell <= storage.is_v2g * is_sell * max_power,
                    f"Respect_Pmax_sale_at_{t}",
                )
                model.add_constraint(
                    -power_buy <= (1 - is_sell * storage.is_v2g) * abs(min_power),
                    f"Respect_Pmax_purchase_at_{t}",
                )
            else:
                model.add_constraint(power_sell <= is_sell * max_power, f"Respect_Pmax_sale_at_{t}")
                model.add_constraint(-power_buy <= (1 - is_sell) * abs(min_power), f"Respect_Pmax_purchase_at_{t}")

        if storage.storage_type == StorageType.ELECTRIC_VEHICLE:
            self._add_ev_displacement_constraint(model, storage)
        else:
            self._dispatch.add_cycle_balance_constraint(model, self._time_frame)

    def _add_objective(self, model: OptimisationModel, storage: StorageDAO) -> None:
        assert self._dispatch is not None
        nb_fragments, smoothing_factor = self._fragment_config(storage)

        if storage.portfolio.market_area.price_forecast_medium is None:
            raise AttributeError(f"{storage.portfolio.market_area.name} has no attribute 'price_forecast_medium'")

        price_forecast_ts = storage.portfolio.market_area.price_forecast_medium.get_forecast(
            self._parameters.temporal.execution_date,
            self._parameters.temporal.start_date,
            self._parameters.temporal.end_date + storage.additional_hours,
            self._parameters.temporal.timestep,
        )

        model.set_direction("maximize")
        dt = self._parameters.temporal.timestep.total_hours()

        if nb_fragments == 1:
            model.add_objective(
                sum(
                    price_forecast_ts.get_value(t)
                    * (self._dispatch.get_fragment_sell_var(t, 0) + self._dispatch.get_fragment_buy_var(t, 0))
                    * dt
                    for t in self._time_frame
                )
            )
        else:
            model.add_objective(
                sum(
                    sum(
                        price_forecast_ts.get_value(t)
                        * (1 - i * smoothing_factor / (nb_fragments - 1))
                        * self._dispatch.get_fragment_sell_var(t, i)
                        * dt
                        + price_forecast_ts.get_value(t)
                        * (1 + i * smoothing_factor / (nb_fragments - 1))
                        * self._dispatch.get_fragment_buy_var(t, i)
                        * dt
                        for i in range(nb_fragments)
                    )
                    for t in self._time_frame
                )
            )

    def _extract_result(self) -> StorageOptimisationResult:
        assert self._dispatch is not None
        sell_volumes: dict[DateTime, float] = {}
        buy_volumes: dict[DateTime, float] = {}
        for t in self._time_frame:
            if t >= self._parameters.temporal.end_date:
                break
            sell_volumes[t] = round(self._dispatch.power_level_sell_var.get_model_var(t).solution_value(), 2)
            buy_volumes[t] = round(-self._dispatch.power_level_buy_var.get_model_var(t).solution_value(), 2)
        return StorageOptimisationResult(sell_volumes=sell_volumes, buy_volumes=buy_volumes)

    def _add_ev_displacement_constraint(self, model: OptimisationModel, storage: StorageDAO) -> None:
        assert self._dispatch is not None
        assert storage.displacement_energy is not None, f"displacement_energy required for EV {storage.name}"
        model.add_constraint(
            sum(-self._dispatch.power_level_buy_var.get_value(t) for t in self._time_frame) * storage.charge_efficiency
            >= (
                storage.displacement_energy.get_value(
                    self._parameters.temporal.end_date + storage.additional_hours - self._parameters.temporal.timestep
                )
                - storage.displacement_energy.get_value(
                    self._parameters.temporal.start_date - self._parameters.temporal.timestep
                )
            )
            * self._parameters.ev_energy_coef,
            f"DisplacementEnergy_compensation_for_{storage.name}",
        )

    def _fragment_config(self, storage: StorageDAO) -> tuple[int, float]:
        storage_type = storage.storage_type
        if storage_type == StorageType.ELECTRIC_VEHICLE:
            return self._parameters.electric_vehicle_nb_fragments, self._parameters.electric_vehicle_smoothing_factor
        if storage_type == StorageType.PUMPED_HYDRAULIC_STORAGE:
            return self._parameters.pumped_hydraulic_nb_fragments, self._parameters.pumped_hydraulic_smoothing_factor
        return self._parameters.battery_nb_fragments, self._parameters.battery_smoothing_factor

    # ------------------------------------------------------------------ #
    #  Order building (previously in StorageOrderBuilder)                 #
    # ------------------------------------------------------------------ #

    def _price_calculation(
        self,
        storage: StorageDAO,
        raw: StorageOptimisationResult,
    ) -> tuple[float, float]:
        if storage.portfolio.market_area.price_forecast_medium is None:
            raise AttributeError(f"{storage.portfolio.market_area.name} has no attribute 'price_forecast_medium'")

        price_forecast = storage.portfolio.market_area.price_forecast_medium.get_forecast(
            self._parameters.temporal.execution_date,
            self._parameters.temporal.start_date,
            self._parameters.temporal.end_date,
            self._parameters.temporal.timestep,
        )

        p_a_max = 0.0
        p_v_min = 0.0

        nonzero_qv = [t for t, v in raw.sell_volumes.items() if v != 0]
        if nonzero_qv:
            p_v_min = price_forecast.dataframe.filter(pl.col("time").is_in(nonzero_qv)).min().select("value").item()

        nonzero_qa = [t for t, v in raw.buy_volumes.items() if v != 0]
        if nonzero_qa:
            p_a_max = price_forecast.dataframe.filter(pl.col("time").is_in(nonzero_qa)).max().select("value").item()

        if (storage.storage_type in [StorageType.BATTERY, StorageType.PUMPED_HYDRAULIC_STORAGE]) or storage.is_v2g:
            p_a_max = max(p_a_max, 0.0)
            p_v_min = max(p_v_min, 0.0)

            if not nonzero_qa:
                return p_v_min, 0.0
            if not nonzero_qv:
                return 0.0, p_a_max
            if p_a_max == 0 and p_v_min == 0:
                return 0.0, 0.0

            a = (storage.discharge_efficiency * storage.charge_efficiency * p_v_min - p_a_max) / (
                storage.discharge_efficiency * storage.charge_efficiency * p_v_min + p_a_max
            )
            return p_v_min * (1 - a), p_a_max * (1 + a)

        return 0.0, p_a_max

    def _create_coupling(
        self,
        storage: StorageDAO,
        raw: StorageOptimisationResult,
        buy_submitted_volumes: Timeseries,
        sell_submitted_volumes: Timeseries,
        coupling_orders: list[OrderDAO],
    ) -> OrderCouplingDAO:
        daily_buy_volume = sum(v * self._parameters.temporal.timestep.total_hours() for v in raw.buy_volumes.values())

        if storage.storage_type == StorageType.ELECTRIC_VEHICLE and daily_buy_volume > 0:
            assert storage.displacement_energy is not None, "displacement_energy must be set for electric vehicles"
            energy_requirement = storage.displacement_energy.get_value(
                self._parameters.penultimate_date
            ) - storage.displacement_energy.get_value(
                self._parameters.temporal.start_date - self._parameters.temporal.timestep
            )
            complement_energy = min(daily_buy_volume, energy_requirement)
            name = (
                f"COMPLEMENT_DA_{storage.name}_{self._parameters.temporal.execution_date.format('DD_MM_YYYY_HH_mm_ss')}"
            )
        else:
            complement_energy = buy_submitted_volumes.sum() - sell_submitted_volumes.sum()
            name = f"COMPLEMENT_DA_{storage.name}_{self._parameters.temporal.execution_date}"

        return OrderCouplingDAO(
            name=name,
            coupling_type=CouplingType.COMPLEMENT,
            complement_direction=ComplementDirection.EqualTo,
            complement_energy=complement_energy,
            orders=coupling_orders,  # type: ignore[arg-type]
        )

    def _create_spot_order(
        self,
        order_type: OrderType,
        storage: StorageDAO,
        start_date: DateTime,
        qmax: float,
        price: float,
    ) -> OrderDAO:
        return OrderDAO(
            name=f"storage_order_type_{order_type}_at_{start_date.format('DD_MM_YYYY_HH_mm_ss')}_for_unit_{storage.name}",
            equipment=storage,
            portfolio=storage.portfolio,
            market_area=storage.portfolio.market_area,
            execution_date=self._parameters.temporal.execution_date,
            start_date=start_date,  # type: ignore[arg-type]
            end_date=start_date + self._parameters.temporal.timestep,  # type: ignore[arg-type]
            order_type=order_type,
            product=Product.DayAhead,
            qmax=qmax,
            qmin=0.0,
            price=price,
        )
