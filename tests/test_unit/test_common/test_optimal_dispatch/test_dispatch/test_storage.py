"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
import pytest

from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.common.optimal_dispatch.dispatch.storage import StorageDispatch
from atlas.common.optimal_dispatch.input_objects.storage import StorageDispatchInput
from atlas.enums import StorageType
from atlas.io_utils.parameters import DateParameters
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
