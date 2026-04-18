"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pendulum import DateTime

import atlas.config as cfg
from atlas.enums import ComplementDirection, CouplingType, OrderType, Product, StorageType
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
from atlas.modules.day_ahead_orders.input_objects.order_coupling import OrderCouplingDAO
from atlas.modules.day_ahead_orders.input_objects.storage import StorageDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.steps.storage.optim.battery import BatteryModel
from atlas.modules.day_ahead_orders.steps.storage.optim.electric_vehicle import ElectricVehicleModel
from atlas.modules.day_ahead_orders.steps.storage.optim.storage import StorageModel
from atlas.solver.models import SolverOptions
from atlas.timing import generate_datetimes


@dataclass
class StorageOptimizationResult:
    """
    This class stores the storage optimization results without the unpicklable solver object,
    making it suitable for multiprocessing with ProcessPoolExecutor.

    :param storage_name: The name of the storage unit
    :type storage_name: str
    :param orders: List of orders generated for this storage unit
    :type orders: list[OrderDAO]
    :param order_couplings: List of order couplings for this storage unit
    :type order_couplings: list[OrderCouplingDAO]
    :param buy_submitted_volumes: Timeseries of buy submitted volumes
    :type buy_submitted_volumes: Timeseries
    :param sell_submitted_volumes: Timeseries of sell submitted volumes
    :type sell_submitted_volumes: Timeseries
    :param variable_cost: Updated variable cost timeseries
    :type variable_cost: Timeseries | None
    :param success: Whether the optimization was successful
    :type success: bool
    """

    storage_name: str
    orders: list[OrderDAO] = field(default_factory=list)
    order_couplings: list[OrderCouplingDAO] = field(default_factory=list)
    buy_submitted_volumes: Timeseries | None = None
    sell_submitted_volumes: Timeseries | None = None
    variable_cost: Timeseries | None = None
    success: bool = True


def optimize_single_storage(
    storage: StorageDAO,
    parameters: DayAheadOrdersParameters,
) -> StorageOptimizationResult:
    """
    Worker function for storage optimization (works for both multiprocessing and sequential).

    Builds and solves the optimization model for a single storage unit, then extracts results
    into a picklable StorageOptimizationResult object (avoiding SWIG solver objects).

    :param storage: Storage unit to optimize
    :type storage: StorageDAO
    :param parameters: Optimization parameters
    :type parameters: DayAheadOrdersParameters
    :return: Storage optimization result
    :rtype: StorageOptimizationResult
    """
    try:
        local_index = generate_datetimes(
            parameters.temporal.start_date,
            parameters.penultimate_date,
            parameters.temporal.timestep,
        )

        local_max_energy = (
            storage.maximum_energy.set_frequency(parameters.temporal.timestep, False)
            .filter(item=local_index, inplace=False)
            .max()
        )

        if local_max_energy <= 0:
            cfg.logger.debug(f"Equipment {str(storage.name)} avoided, as its maximum_energy is 0")
            return StorageOptimizationResult(storage_name=storage.name, success=False)

        cfg.logger.debug(f"Optimizing storage equipment {str(storage.name)}")

        # Get initial stock
        initial_stock = _initiate_stock(storage, parameters)

        # Run optimization
        solver_options = SolverOptions(
            presolve=parameters.solver.use_presolve,
            duality_gap=parameters.solver.duality_gap,
            time_limit=parameters.solver.timeout,
        )

        if storage.storage_type == StorageType.ELECTRIC_VEHICLE:
            Qv, Qa = _optimize_ev(storage, initial_stock, solver_options, parameters)
        else:
            Qv, Qa = _optimize_battery(storage, initial_stock, solver_options, parameters)

        buy_submitted_volumes = Timeseries.from_values(
            parameters.temporal.start_date, parameters.temporal.timestep, list(Qa.values())
        )
        sell_submitted_volumes = Timeseries.from_values(
            parameters.temporal.start_date, parameters.temporal.timestep, list(Qv.values())
        )

        # Calculate prices
        Psale, Ppurchase = _price_calculation(storage, Qv, Qa, parameters)

        # Update variable cost
        if Ppurchase != 0:
            variable_cost = round(Ppurchase, 2)
        elif storage.discharge_efficiency != 0 and storage.charge_efficiency != 0:
            variable_cost = round(Psale * storage.discharge_efficiency * storage.charge_efficiency, 2)
        else:
            variable_cost = round(Psale, 2)
            cfg.logger.warning(
                f"ChargeEfficiency or DischargeEfficiency is null for equipment {storage.name}. "
                "This is not supposed to be the case, as the default value for these is 1 and not 0"
            )
        variable_cost = Timeseries.from_values(
            parameters.temporal.start_date,
            parameters.temporal.timestep,
            [variable_cost] * len(local_index),
        )

        # Create orders and couplings
        orders, order_couplings = _create_orders_with_couplings(
            storage, Qa, Qv, Ppurchase, Psale, buy_submitted_volumes, sell_submitted_volumes, parameters
        )

        return StorageOptimizationResult(
            storage_name=storage.name,
            orders=orders,
            order_couplings=order_couplings,
            buy_submitted_volumes=buy_submitted_volumes,
            sell_submitted_volumes=sell_submitted_volumes,
            variable_cost=variable_cost,
            success=True,
        )

    except Exception as e:
        cfg.logger.error(f"Optimization failed for storage {storage.name}: {e}")
        return StorageOptimizationResult(storage_name=storage.name, success=False)


def _initiate_stock(storage: StorageDAO, parameters: DayAheadOrdersParameters) -> float | None:
    """
    Initialize stock for storage unit. If stored_energy is available, use it to determine initial stock.
    Otherwise, use storage_initial_level. The 'availability' of stored_energy is defined as follow:
    - If stored_energy is completely empty, then it is not available.
    - If stored_energy is not empty, but it does not contain data shortly before start_date (shortly being
      arbitrarily defined as two days before start_date), then it is also not available.
    """
    if storage.stored_energy is None:
        initial_stock = storage.storage_initial_level * storage.maximum_energy.get_value(parameters.temporal.start_date)
    else:
        energy_forecast = storage.stored_energy.get_forecast(
            parameters.temporal.execution_date,
            parameters.temporal.start_date.subtract(days=2),
            parameters.temporal.start_date - parameters.temporal.timestep,
            parameters.temporal.timestep,
        )
        if len(energy_forecast) == 0:
            initial_stock = storage.storage_initial_level * storage.maximum_energy.get_value(
                parameters.temporal.start_date
            )
        else:
            initial_stock = energy_forecast.get_value(parameters.temporal.start_date - parameters.temporal.timestep)
    return initial_stock


def _optimize_ev(
    storage: StorageDAO,
    initial_stock: float | None,
    solvers_options: SolverOptions,
    parameters: DayAheadOrdersParameters,
) -> tuple[dict[DateTime, float], dict[DateTime, float]]:
    """Optimization function for ElectricVehicle units."""
    model = ElectricVehicleModel(
        parameters,
        parameters.solver.solver_name,
        "Optimization of the storage unit " + storage.name,
        storage,
        solvers_options,
    )
    model.create_decision_variables(parameters.ev_nb_fragments)
    model.create_objective_function(parameters.ev_nb_fragments, parameters.ev_smoothing_factor, "maximize")
    model.create_constraints(initial_stock)

    if parameters.solver.export_lp:
        output_path = parameters.get_output_dir() / "lp_export"
        output_path.mkdir(parents=True, exist_ok=True)
        lp_file_path = output_path / f"storage_{model.storage.name}.lp"
        model.export_model(lp_file_path)

    model.solve()

    Qvv: dict[DateTime, float] = {}
    Qaa: dict[DateTime, float] = {}
    for t in model.time_frame:
        if t >= parameters.temporal.end_date:
            break
        Qvv[t] = round(model.get_variable(StorageModel.sold_at_key(t)).solution_value(), 2)
        Qaa[t] = round(model.get_variable(StorageModel.purchased_at_key(t)).solution_value(), 2)

    return Qvv, Qaa


def _optimize_battery(
    storage: StorageDAO,
    initial_stock: float | None,
    solvers_options: SolverOptions,
    parameters: DayAheadOrdersParameters,
) -> tuple[dict[DateTime, float], dict[DateTime, float]]:
    """Optimization function for Battery and PHS units."""
    if storage.storage_type == StorageType.BATTERY:
        smoothing_factor = parameters.battery_smoothing_factor
        power_fragments = parameters.battery_nb_fragments
    elif storage.storage_type == StorageType.PUMPED_HYDRAULIC_STORAGE:
        smoothing_factor = parameters.phs_smoothing_factor
        power_fragments = parameters.phs_nb_fragments
    else:
        cfg.logger.error(
            f"equipment {storage.name} isn't {StorageType.BATTERY} nor {StorageType.PUMPED_HYDRAULIC_STORAGE}"
        )
        return {}, {}

    model = BatteryModel(
        parameters,
        parameters.solver.solver_name,
        "Optimization of the storage unit " + storage.name,
        storage,
        solvers_options,
    )
    model.create_decision_variables(power_fragments)
    model.create_objective_function(power_fragments, smoothing_factor, "maximize")
    model.create_constraints(initial_stock, power_fragments)

    if parameters.solver.export_lp:
        output_path = parameters.get_output_dir() / "lp_export"
        output_path.mkdir(parents=True, exist_ok=True)
        lp_file_path = output_path / f"storage_{model.storage.name}.lp"
        model.export_model(str(lp_file_path))

    model.solve()

    Qvv: dict[DateTime, float] = {}
    Qaa: dict[DateTime, float] = {}
    for t in model.time_frame:
        if t >= parameters.temporal.end_date:
            break
        Qvv[t] = round(model.get_variable(StorageModel.sold_at_key(t)).solution_value(), 2)
        Qaa[t] = round(model.get_variable(StorageModel.purchased_at_key(t)).solution_value(), 2)

    return Qvv, Qaa


def _price_calculation(
    storage: StorageDAO, Qv: dict[DateTime, float], Qa: dict[DateTime, float], parameters: DayAheadOrdersParameters
) -> tuple[float, float]:
    """Price computation."""
    P_a_max = 0.0
    P_v_min = 0.0
    if storage.portfolio.market_area.price_forecast_medium is not None:
        price_forecast = storage.portfolio.market_area.price_forecast_medium.get_forecast(
            parameters.temporal.execution_date,
            parameters.temporal.start_date,
            parameters.temporal.end_date,
            parameters.temporal.timestep,
        )
    else:
        raise AttributeError(f"{storage.portfolio.market_area.name} has no attribute 'price_forecast_medium'")

    Qv_empty = all(qv_value == 0 for qv_value in Qv.values())
    Qa_empty = all(qa_value == 0 for qa_value in Qa.values())

    nonzero_qv = [t for t, v in Qv.items() if v != 0]
    if nonzero_qv:
        P_v_min = min(price_forecast.get_value(t) for t in nonzero_qv)
    nonzero_qa = [t for t, v in Qa.items() if v != 0]
    if nonzero_qa:
        P_a_max = max(price_forecast.get_value(t) for t in nonzero_qa)

    if (storage.storage_type in [StorageType.BATTERY, StorageType.PUMPED_HYDRAULIC_STORAGE]) or (storage.is_v2g):
        if P_a_max <= 0:
            P_a_max = 0.0
        if P_v_min <= 0:
            P_v_min = 0.0

        if Qa_empty:
            Psale = P_v_min
            Ppurchase = 0.0
        elif Qv_empty:
            Psale = 0.0
            Ppurchase = P_a_max
        elif P_a_max == 0 and P_v_min == 0:
            Psale = 0.0
            Ppurchase = 0.0
        else:
            a = (storage.discharge_efficiency * storage.charge_efficiency * P_v_min - P_a_max) / (
                storage.discharge_efficiency * storage.charge_efficiency * P_v_min + P_a_max
            )
            Psale = P_v_min * (1 - a)
            Ppurchase = P_a_max * (1 + a)
    else:
        Psale = 0.0
        Ppurchase = P_a_max

    return Psale, Ppurchase


def _create_orders_with_couplings(
    storage: StorageDAO,
    Qa: dict[DateTime, float],
    Qv: dict[DateTime, float],
    Ppurchase: float,
    Psale: float,
    buy_submitted_volumes: Timeseries,
    sell_submitted_volumes: Timeseries,
    parameters: DayAheadOrdersParameters,
) -> tuple[list[OrderDAO], list[OrderCouplingDAO]]:
    """Create orders and order couplings for the storage unit."""

    orders: list[OrderDAO] = []
    order_couplings: list[OrderCouplingDAO] = []

    daily_buy_volume = sum(buy_volume * parameters.temporal.timestep.total_hours() for buy_volume in Qa.values())

    coupling_orders: list[OrderDAO] = []

    for t, qa_val in Qa.items():
        order = _create_spot_order(OrderType.Buy, storage, t, qa_val, Ppurchase, parameters)
        orders.append(order)
        coupling_orders.append(order)

    for t, qv_val in Qv.items():
        order = _create_spot_order(OrderType.Sell, storage, t, qv_val, Psale, parameters)
        orders.append(order)
        coupling_orders.append(order)

    if storage.storage_type == StorageType.ELECTRIC_VEHICLE and daily_buy_volume > 0:
        assert storage.displacement_energy is not None, "displacement_energy must be set for electric vehicles"

        energy_requirement = storage.displacement_energy.get_value(
            parameters.penultimate_date
        ) - storage.displacement_energy.get_value(parameters.temporal.start_date - parameters.temporal.timestep)

        complement_energy = daily_buy_volume if energy_requirement > daily_buy_volume else energy_requirement

        order_couplings.append(
            OrderCouplingDAO(
                name=f"COMPLEMENT_DA_{storage.name}_{parameters.temporal.execution_date}",
                coupling_type=CouplingType.COMPLEMENT,
                complement_direction=ComplementDirection.EqualTo,
                complement_energy=complement_energy,
                orders=coupling_orders,  # type: ignore [arg-type]
            )
        )
    else:
        order_couplings.append(
            OrderCouplingDAO(
                name=f"COMPLEMENT_DA_{storage.name}_{parameters.temporal.execution_date}",
                coupling_type=CouplingType.COMPLEMENT,
                complement_direction=ComplementDirection.EqualTo,
                complement_energy=buy_submitted_volumes.sum() - sell_submitted_volumes.sum(),
                orders=coupling_orders,  # type: ignore [arg-type]
            )
        )

    return orders, order_couplings


def _create_spot_order(
    order_type: OrderType,  # type: ignore[name-defined]
    storage: StorageDAO,
    start_date: DateTime,
    qmax: float,
    price: float,
    parameters: DayAheadOrdersParameters,
) -> OrderDAO:
    """Create a single spot order."""

    return OrderDAO(
        name=f"storage_order_type_{order_type}_at_{start_date}_for_unit_{storage.name}",
        equipment=storage,
        portfolio=storage.portfolio,
        market_area=storage.portfolio.market_area,
        execution_date=parameters.temporal.execution_date,
        start_date=start_date,
        end_date=start_date + parameters.temporal.timestep,
        order_type=order_type,
        product=Product.DayAhead,
        qmax=qmax,
        qmin=0.0,
        price=price,
    )
