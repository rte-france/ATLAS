"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
import pytest

from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.common.optimal_dispatch.dispatch.storage import StorageDispatch
from atlas.common.optimal_dispatch.input_objects.storage import StorageDispatchInput
from atlas.enums import SolverStatus, StorageType
from atlas.io_utils.parameters import DateParameters
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.objects.market.market_area import MarketArea
from atlas.objects.market_operator.portfolio import Portfolio
from atlas.objects.network.node import Node
from atlas.objects.network_operator.control_block import ControlBlock
from atlas.solver.solver_interface import OptimisationModel


@pytest.fixture
def start_date():
    return pendulum.datetime(2024, 1, 1)


@pytest.fixture
def timestep():
    return pendulum.duration(hours=1)


@pytest.fixture
def control_block():
    return ControlBlock(name="cb")


@pytest.fixture
def market_area(control_block):
    return MarketArea(name="ma", control_block=control_block)


@pytest.fixture
def node(control_block, market_area):
    return Node(name="node", control_block=control_block, market_area=market_area)


@pytest.fixture
def portfolio(control_block, market_area):
    return Portfolio(name="portfolio", control_block=control_block, market_area=market_area)


@pytest.fixture
def power_ts(start_date, timestep):
    return Timeseries.from_index(
        start_date=start_date.subtract(days=1),
        frequency=timestep,
        end_date=start_date.add(days=2),
        default_value=100.0,
    )


@pytest.fixture
def soc_ts(start_date, timestep):
    return Timeseries.from_index(
        start_date=start_date.subtract(days=1),
        frequency=timestep,
        end_date=start_date.add(days=2),
        default_value=0.1,
    )


@pytest.fixture
def battery_equipment(node, portfolio, power_ts, soc_ts):
    return StorageDispatchInput(
        name="bat_1",
        node=node,
        portfolio=portfolio,
        storage_type=StorageType.BATTERY,
        maximum_energy=power_ts,
        minimum_power=Timeseries.from_index(
            start_date=power_ts.first_date(),
            frequency=pendulum.duration(hours=1),
            end_date=power_ts.last_date(),
            default_value=-50.0,
        ),
        maximum_power=power_ts,
        minimum_state_of_charge=soc_ts,
        charge_efficiency=0.9,
        discharge_efficiency=0.9,
        storage_initial_level=0.5,
        additional_hours=pendulum.duration(hours=2),
    )


@pytest.fixture
def ev_equipment(node, portfolio, power_ts, soc_ts):
    return StorageDispatchInput(
        name="ev_1",
        node=node,
        portfolio=portfolio,
        storage_type=StorageType.ELECTRIC_VEHICLE,
        maximum_energy=power_ts,
        minimum_power=Timeseries.from_index(
            start_date=power_ts.first_date(),
            frequency=pendulum.duration(hours=1),
            end_date=power_ts.last_date(),
            default_value=-50.0,
        ),
        maximum_power=power_ts,
        minimum_state_of_charge=soc_ts,
        charge_efficiency=0.95,
        discharge_efficiency=1.0,
        storage_initial_level=0.3,
        additional_hours=pendulum.duration(hours=0),
        is_v2g=False,
    )


@pytest.fixture
def parameters(start_date, timestep):
    return AbstractModuleParameters(
        temporal=DateParameters(
            start_date=start_date,
            end_date=start_date.add(hours=4),
            execution_date=start_date.subtract(days=1),
            timestep=timestep,
        )
    )


@pytest.fixture
def model():
    return OptimisationModel("SCIP", "test_storage_dispatch")


@pytest.fixture
def time_window(start_date, timestep):
    return [start_date.add(hours=h) for h in range(4)]


class TestStorageDispatchVariables:
    def test_setup_creates_model_vars(self, battery_equipment, model, parameters):
        d = StorageDispatch(battery_equipment)
        d.setup(model, parameters)
        assert d.power_level_sell_var is not None
        assert d.power_level_buy_var is not None
        assert d.is_sell_var is not None
        assert d.stored_energy_var is not None

    def test_add_variables_creates_correct_names(self, battery_equipment, model, parameters, time_window):
        d = StorageDispatch(battery_equipment)
        d.setup(model, parameters)
        n = battery_equipment.name
        t = time_window[0]

        d.add_variables(t)

        assert f"{n}_power_level_sell_{t}" in model.variables
        assert f"{n}_power_level_buy_{t}" in model.variables
        assert f"{n}_is_sell_{t}" in model.variables
        assert f"{n}_stored_energy_{t}" in model.variables

    def test_power_level_sell_bounds(self, battery_equipment, model, parameters, time_window):
        d = StorageDispatch(battery_equipment)
        d.setup(model, parameters)
        t = time_window[0]
        d.add_variables(t)

        var = model.get_variable(f"{battery_equipment.name}_power_level_sell_{t}")
        assert var.lb() == 0
        assert var.ub() == pytest.approx(100.0)

    def test_power_level_buy_bounds(self, battery_equipment, model, parameters, time_window):
        d = StorageDispatch(battery_equipment)
        d.setup(model, parameters)
        t = time_window[0]
        d.add_variables(t)

        var = model.get_variable(f"{battery_equipment.name}_power_level_buy_{t}")
        assert var.lb() == pytest.approx(-50.0)
        assert var.ub() == 0

    def test_stored_energy_bounds(self, battery_equipment, model, parameters, time_window):
        d = StorageDispatch(battery_equipment)
        d.setup(model, parameters)
        t = time_window[0]
        d.add_variables(t)

        var = model.get_variable(f"{battery_equipment.name}_stored_energy_{t}")
        # lower bound = min_soc * max_energy = 0.1 * 100 = 10
        assert var.lb() == pytest.approx(10.0)
        assert var.ub() == pytest.approx(100.0)

    def test_initial_stock_no_stored_energy(self, battery_equipment, parameters):
        d = StorageDispatch(battery_equipment)
        d._compute_initial_stock(parameters)
        # initial_stock = storage_initial_level * max_energy[start - timestep] = 0.5 * 100
        assert d._initial_stock == pytest.approx(50.0)


class TestStorageDispatchAccessors:
    def test_effective_max_sell_battery(self, battery_equipment, model, parameters):
        d = StorageDispatch(battery_equipment)
        d.setup(model, parameters)
        t = pendulum.datetime(2024, 1, 1)
        # max_power=100, discharge_efficiency=0.9
        assert d.effective_max_sell(t) == pytest.approx(90.0)

    def test_effective_max_sell_ev_no_v2g(self, ev_equipment, model, parameters):
        d = StorageDispatch(ev_equipment)
        d.setup(model, parameters)
        t = pendulum.datetime(2024, 1, 1)
        # is_v2g=False → 0 * max_power * discharge_efficiency = 0
        assert d.effective_max_sell(t) == pytest.approx(0.0)

    def test_effective_max_sell_ev_with_v2g(self, node, portfolio, power_ts, soc_ts, model, parameters):
        ev_v2g = StorageDispatchInput(
            name="ev_v2g",
            node=node,
            portfolio=portfolio,
            storage_type=StorageType.ELECTRIC_VEHICLE,
            maximum_energy=power_ts,
            minimum_power=Timeseries.from_index(
                start_date=power_ts.first_date(),
                frequency=pendulum.duration(hours=1),
                end_date=power_ts.last_date(),
                default_value=-50.0,
            ),
            maximum_power=power_ts,
            minimum_state_of_charge=soc_ts,
            charge_efficiency=0.95,
            discharge_efficiency=0.8,
            storage_initial_level=0.3,
            additional_hours=pendulum.duration(hours=0),
            is_v2g=True,
        )
        d = StorageDispatch(ev_v2g)
        d.setup(model, parameters)
        t = pendulum.datetime(2024, 1, 1)
        # is_v2g=True → 1.0 * 100 * 0.8 = 80
        assert d.effective_max_sell(t) == pytest.approx(80.0)

    def test_effective_min_buy_battery(self, battery_equipment, model, parameters):
        d = StorageDispatch(battery_equipment)
        d.setup(model, parameters)
        t = pendulum.datetime(2024, 1, 1)
        # min_power=-50, charge_efficiency=0.9 → -50 / 0.9
        assert d.effective_min_buy(t) == pytest.approx(-50.0 / 0.9)


class TestStorageDispatchCycleBalance:
    def test_cycle_balance_constraint_added(self, battery_equipment, model, parameters, time_window):
        d = StorageDispatch(battery_equipment)
        d.setup(model, parameters)
        for t in time_window:
            d.add_variables(t)

        d.add_cycle_balance_constraint(model, time_window)

        assert f"cycle_balance_{battery_equipment.name}" in model.constraints

    def test_cycle_balance_added_for_ev(self, ev_equipment, model, parameters, time_window):
        """EV can have cycle balance in PO context (DA uses fill-up instead — caller's responsibility)."""
        d = StorageDispatch(ev_equipment)
        d.setup(model, parameters)
        for t in time_window:
            d.add_variables(t)

        d.add_cycle_balance_constraint(model, time_window)

        assert f"cycle_balance_{ev_equipment.name}" in model.constraints


class TestStorageDispatchConstraints:
    def test_level_evolution_at_start(self, battery_equipment, model, parameters, time_window):
        d = StorageDispatch(battery_equipment)
        d.setup(model, parameters)
        for t in time_window:
            d.add_variables(t)

        t0 = time_window[0]
        d.add_constraints(model, t0, parameters)

        constraint_name = f"storage_level_evol_{t0}_{battery_equipment.name}"
        assert constraint_name in model.constraints

    def test_level_evolution_after_start(self, battery_equipment, model, parameters, time_window):
        d = StorageDispatch(battery_equipment)
        d.setup(model, parameters)
        for t in time_window:
            d.add_variables(t)

        t1 = time_window[1]
        d.add_constraints(model, t1, parameters)

        constraint_name = f"storage_level_evol_{t1}_{battery_equipment.name}"
        assert constraint_name in model.constraints

    def test_sell_buy_separation_added_for_battery(self, battery_equipment, model, parameters, time_window):
        d = StorageDispatch(battery_equipment)
        d.setup(model, parameters)
        for t in time_window:
            d.add_variables(t)

        t0 = time_window[0]
        d.add_constraints(model, t0, parameters)

        assert f"relative_power_max_{t0}_{battery_equipment.name}" in model.constraints
        assert f"relative_power_min_{t0}_{battery_equipment.name}" in model.constraints

    def test_sell_buy_separation_skipped_for_ev(self, ev_equipment, model, parameters, time_window):
        """Sell/buy separation for EV is left to the calling module."""
        d = StorageDispatch(ev_equipment)
        d.setup(model, parameters)
        for t in time_window:
            d.add_variables(t)

        t0 = time_window[0]
        d.add_constraints(model, t0, parameters)

        assert f"relative_power_max_{t0}_{ev_equipment.name}" not in model.constraints
        assert f"relative_power_min_{t0}_{ev_equipment.name}" not in model.constraints


class TestStorageDispatchLevelEvolutionSolved:
    """
    Solve the LP and read the stored energy back, so the *content* of the level
    evolution constraint is checked — not just that a constraint of that name exists.

    Guards the sign convention introduced by the optimal-dispatch migration:
    ``power_level_buy`` is negative (charging), where the previous formulation used a
    positive ``Amount_purchased``. A sign flip here is invisible to name-only assertions.
    """

    def _solved_stock(self, equipment, model, parameters, time_window, sell: float, buy: float) -> float:
        d = StorageDispatch(equipment)
        d.setup(model, parameters)
        for t in time_window:
            d.add_variables(t)

        t0 = time_window[0]
        d.add_constraints(model, t0, parameters)

        # pin the dispatch so the level evolution has a single feasible solution
        model.add_constraint(d.power_level_sell_var.get_value(t0) == sell, "pin_sell")
        model.add_constraint(d.power_level_buy_var.get_value(t0) == buy, "pin_buy")

        model.set_direction("minimize")
        model.set_objective(d.stored_energy_var.get_value(t0) * 0)
        assert model.solve().status == SolverStatus.OPTIMAL

        return model.get_variable(f"{equipment.name}_stored_energy_{t0}").solution_value()

    def test_discharging_divides_by_discharge_efficiency(
        self, battery_equipment, model, parameters, time_window
    ):
        # initial stock 50 (= 0.5 * 100); selling 9 MW for 1 h draws 9 / 0.9 = 10 MWh
        stock = self._solved_stock(battery_equipment, model, parameters, time_window, sell=9.0, buy=0.0)
        assert stock == pytest.approx(40.0)

    def test_charging_multiplies_by_charge_efficiency_with_negative_buy(
        self, battery_equipment, model, parameters, time_window
    ):
        # buy is negative by convention; charging 9 MW for 1 h stores 9 * 0.9 = 8.1 MWh
        stock = self._solved_stock(battery_equipment, model, parameters, time_window, sell=0.0, buy=-9.0)
        assert stock == pytest.approx(58.1)

    def test_idle_keeps_initial_stock(self, battery_equipment, model, parameters, time_window):
        stock = self._solved_stock(battery_equipment, model, parameters, time_window, sell=0.0, buy=0.0)
        assert stock == pytest.approx(50.0)


class TestStorageDispatchInitialStock:
    def test_initial_stock_from_stored_energy_forecast(self, battery_equipment, parameters, start_date, timestep):
        """When a stored_energy forecast is available it wins over the storage_initial_level default."""
        forecast = ForecastingMatrix()
        forecast.add(
            Timeseries.from_index(
                start_date=start_date.subtract(days=1),
                frequency=timestep,
                end_date=start_date.add(days=1),
                default_value=77.0,
            ),
            parameters.temporal.execution_date,
        )
        battery_equipment.stored_energy = forecast

        d = StorageDispatch(battery_equipment)
        d._compute_initial_stock(parameters)

        assert d._initial_stock == pytest.approx(77.0)

    def test_initial_stock_falls_back_when_matrix_is_empty(self, battery_equipment, parameters):
        """An empty matrix must be screened out — get_forecast raises on one."""
        battery_equipment.stored_energy = ForecastingMatrix()

        d = StorageDispatch(battery_equipment)
        d._compute_initial_stock(parameters)

        # falls back to storage_initial_level * max_energy = 0.5 * 100
        assert d._initial_stock == pytest.approx(50.0)

    def test_initial_stock_falls_back_when_forecast_misses_window(
        self, battery_equipment, parameters, start_date, timestep
    ):
        """Matrix holds data, but none covering the instant before start_date."""
        forecast = ForecastingMatrix()
        forecast.add(
            Timeseries.from_index(
                start_date=start_date.add(days=10),
                frequency=timestep,
                end_date=start_date.add(days=11),
                default_value=77.0,
            ),
            parameters.temporal.execution_date,
        )
        battery_equipment.stored_energy = forecast

        d = StorageDispatch(battery_equipment)
        d._compute_initial_stock(parameters)

        assert d._initial_stock == pytest.approx(50.0)


class TestStorageDispatchDisplacementEnergy:
    """Electric vehicles consume energy while driving — displacement is subtracted from the stock."""

    def test_displacement_reduces_stored_energy(self, ev_equipment, model, parameters, start_date, timestep):
        # displacement grows by 5 MWh between prev and t0
        ev_equipment.displacement_energy = Timeseries.from_index(
            start_date=start_date.subtract(days=1),
            frequency=timestep,
            end_date=start_date.add(days=1),
            default_value=0.0,
        )
        ev_equipment.displacement_energy.set_value(start_date, 5.0)

        d = StorageDispatch(ev_equipment)
        d.setup(model, parameters)
        time_window = [start_date.add(hours=h) for h in range(2)]
        for t in time_window:
            d.add_variables(t)

        t0 = time_window[0]
        d.add_constraints(model, t0, parameters)
        model.add_constraint(d.power_level_sell_var.get_value(t0) == 0.0, "pin_sell")
        model.add_constraint(d.power_level_buy_var.get_value(t0) == 0.0, "pin_buy")
        model.set_direction("minimize")
        model.set_objective(d.stored_energy_var.get_value(t0) * 0)
        assert model.solve().status == SolverStatus.OPTIMAL

        # initial stock 30 (= 0.3 * 100), displacement delta +5 → 35
        stock = model.get_variable(f"{ev_equipment.name}_stored_energy_{t0}").solution_value()
        assert stock == pytest.approx(35.0)


class TestStorageDispatchFragments:
    def test_setup_stores_nb_fragments(self, battery_equipment, model, parameters):
        d = StorageDispatch(battery_equipment)
        d.setup(model, parameters, nb_fragments=3)
        assert d._nb_fragments == 3

    def test_add_fragment_variables_creates_correct_names(self, battery_equipment, model, parameters, time_window):
        d = StorageDispatch(battery_equipment)
        d.setup(model, parameters, nb_fragments=3)
        t = time_window[0]
        n = battery_equipment.name

        d.add_fragment_variables(t, max_power=100.0, min_power=-50.0)

        for i in range(3):
            assert f"{n}_power_level_sell_n_{i}_{t}" in model.variables
            assert f"{n}_power_level_buy_n_{i}_{t}" in model.variables

    def test_add_fragment_variables_sell_bounds(self, battery_equipment, model, parameters, time_window):
        d = StorageDispatch(battery_equipment)
        d.setup(model, parameters, nb_fragments=4)
        t = time_window[0]
        n = battery_equipment.name

        d.add_fragment_variables(t, max_power=100.0, min_power=-60.0)

        for i in range(4):
            var = model.get_variable(f"{n}_power_level_sell_n_{i}_{t}")
            assert var.lb() == pytest.approx(0.0)
            assert var.ub() == pytest.approx(25.0)  # 100 / 4

    def test_add_fragment_variables_buy_bounds(self, battery_equipment, model, parameters, time_window):
        d = StorageDispatch(battery_equipment)
        d.setup(model, parameters, nb_fragments=4)
        t = time_window[0]
        n = battery_equipment.name

        d.add_fragment_variables(t, max_power=100.0, min_power=-60.0)

        for i in range(4):
            var = model.get_variable(f"{n}_power_level_buy_n_{i}_{t}")
            assert var.lb() == pytest.approx(-15.0)  # -60 / 4
            assert var.ub() == pytest.approx(0.0)

    def test_add_fragment_variables_noop_when_zero(self, battery_equipment, model, parameters, time_window):
        d = StorageDispatch(battery_equipment)
        d.setup(model, parameters, nb_fragments=0)
        t = time_window[0]
        n = battery_equipment.name

        d.add_fragment_variables(t, max_power=100.0, min_power=-50.0)

        assert f"{n}_power_level_sell_n_0_{t}" not in model.variables
        assert f"{n}_power_level_buy_n_0_{t}" not in model.variables

    def test_add_fragment_sum_constraints(self, battery_equipment, model, parameters, time_window):
        d = StorageDispatch(battery_equipment)
        d.setup(model, parameters, nb_fragments=3)
        for t in time_window:
            d.add_variables(t)
            d.add_fragment_variables(t, max_power=100.0, min_power=-50.0)

        t0 = time_window[0]
        n = battery_equipment.name
        d.add_fragment_sum_constraints(
            t0,
            d.power_level_sell_var.get_value(t0),
            d.power_level_buy_var.get_value(t0),
        )

        assert f"sell_fragment_sum_{t0}_{n}" in model.constraints
        assert f"buy_fragment_sum_{t0}_{n}" in model.constraints

    def test_add_fragment_sum_constraints_noop_when_zero(self, battery_equipment, model, parameters, time_window):
        d = StorageDispatch(battery_equipment)
        d.setup(model, parameters, nb_fragments=0)
        for t in time_window:
            d.add_variables(t)

        t0 = time_window[0]
        n = battery_equipment.name
        d.add_fragment_sum_constraints(
            t0,
            d.power_level_sell_var.get_value(t0),
            d.power_level_buy_var.get_value(t0),
        )

        assert f"sell_fragment_sum_{t0}_{n}" not in model.constraints
        assert f"buy_fragment_sum_{t0}_{n}" not in model.constraints

    def test_get_fragment_sell_var_returns_correct_variable(self, battery_equipment, model, parameters, time_window):
        d = StorageDispatch(battery_equipment)
        d.setup(model, parameters, nb_fragments=2)
        t = time_window[0]
        n = battery_equipment.name
        d.add_fragment_variables(t, max_power=100.0, min_power=-50.0)

        var = d.get_fragment_sell_var(t, 1)

        assert var == model.get_variable(f"{n}_power_level_sell_n_1_{t}")

    def test_get_fragment_buy_var_returns_correct_variable(self, battery_equipment, model, parameters, time_window):
        d = StorageDispatch(battery_equipment)
        d.setup(model, parameters, nb_fragments=2)
        t = time_window[0]
        n = battery_equipment.name
        d.add_fragment_variables(t, max_power=100.0, min_power=-50.0)

        var = d.get_fragment_buy_var(t, 1)

        assert var == model.get_variable(f"{n}_power_level_buy_n_1_{t}")
