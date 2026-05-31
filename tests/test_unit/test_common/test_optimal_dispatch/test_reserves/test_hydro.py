"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
import pytest

from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.common.optimal_dispatch.dispatch.hydro import HydroDispatch
from atlas.common.optimal_dispatch.input_objects.hydro import HydroDispatchInput
from atlas.common.optimal_dispatch.reserves.hydro import HydroReserveHandler
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
def min_power_ts(start_date, timestep):
    return Timeseries.from_index(
        start_date=start_date.subtract(days=1),
        frequency=timestep,
        end_date=start_date.add(days=2),
        default_value=0.0,
    )


@pytest.fixture
def energy_ts(start_date, timestep):
    return Timeseries.from_index(
        start_date=start_date.subtract(days=1),
        frequency=timestep,
        end_date=start_date.add(days=2),
        default_value=500.0,
    )


@pytest.fixture
def initial_level_ts(start_date, timestep):
    return Timeseries.from_index(
        start_date=start_date.subtract(days=2),
        frequency=timestep,
        end_date=start_date.add(days=2),
        default_value=250.0,
    )


@pytest.fixture
def hydro_equipment(node, portfolio, power_ts, min_power_ts, energy_ts, initial_level_ts):
    return HydroDispatchInput(
        name="hydro_1",
        node=node,
        portfolio=portfolio,
        maximum_energy=energy_ts,
        minimum_energy=energy_ts,
        maximum_power=power_ts,
        minimum_power=min_power_ts,
        initial_level=initial_level_ts,
        additional_hours=pendulum.duration(hours=0),
        fragment_prices=[10.0, 20.0],
        fragment_volumes=[0.5, 0.5],
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
    return OptimisationModel("SCIP", "test_hydro_reserves")


@pytest.fixture
def time_window(start_date):
    return [start_date.add(hours=h) for h in range(4)]


@pytest.fixture
def dispatch(hydro_equipment, model, parameters, time_window):
    d = HydroDispatch(hydro_equipment)
    d.setup(model, parameters)
    for t in time_window:
        d.add_variables(t)
    return d


@pytest.fixture
def handler(dispatch):
    return HydroReserveHandler(name="hydro_1", dispatch=dispatch, maximum_automated=15.0)


class TestHydroReserveHandlerVariables:
    def test_add_variables_creates_all_reserve_vars_including_relaxed(self, handler, model, time_window):
        handler.setup(model)
        t = time_window[0]
        handler.add_variables(t, max_power=100.0, min_power=0.0)

        assert f"reserves_up_hydro_1_{t}" in model.variables
        assert f"reserves_down_hydro_1_{t}" in model.variables
        assert f"unprovided_reserves_up_hydro_1_{t}" in model.variables
        assert f"unprovided_reserves_down_hydro_1_{t}" in model.variables
        assert f"automated_reserves_up_hydro_1_{t}" in model.variables
        assert f"automated_reserves_down_hydro_1_{t}" in model.variables
        assert f"relaxed_reserves_hydro_1_{t}" in model.variables

    def test_relaxed_reserves_bounds(self, handler, model, time_window):
        """relaxed_reserves for hydro is bounded ``[min_power, 0]`` (mirroring the legacy formulation)."""
        handler.setup(model)
        t = time_window[0]
        handler.add_variables(t, max_power=100.0, min_power=0.0)
        var = model.get_variable(f"relaxed_reserves_hydro_1_{t}")
        assert var.lb() == 0
        assert var.ub() == 0


class TestHydroReserveHandlerConstraints:
    def test_capacity_constraints_names(self, handler, model, time_window):
        handler.setup(model)
        t = time_window[0]
        handler.add_variables(t, max_power=100.0, min_power=0.0)
        handler.add_capacity_constraints(t, max_power=100.0)
        assert f"reserves_up_max_{t}_hydro_1" in model.constraints
        assert f"reserves_down_max_{t}_hydro_1" in model.constraints

    def test_automated_capacity_constraints_names(self, handler, model, time_window):
        handler.setup(model)
        t = time_window[0]
        handler.add_variables(t, max_power=100.0, min_power=0.0)
        handler.add_automated_capacity_constraints(t)
        assert f"automated_reserves_up_max_{t}_hydro_1" in model.constraints
        assert f"automated_reserves_down_max_{t}_hydro_1" in model.constraints

    def test_relaxed_constraint_name(self, handler, model, time_window):
        handler.setup(model)
        t = time_window[0]
        handler.add_variables(t, max_power=100.0, min_power=0.0)
        handler.add_relaxed_reserve_constraint(t, min_power=0.0)
        assert f"relaxed_reserves_{t}_hydro_1" in model.constraints

    def test_storage_level_constraints_couple_reserves(self, handler, model, time_window):
        handler.setup(model)
        t = time_window[0]
        handler.add_variables(t, max_power=100.0, min_power=0.0)
        handler.add_storage_level_constraints(t, min_energy=10.0, max_energy=500.0)
        assert f"min_storage_level_{t}_hydro_1" in model.constraints
        assert f"max_storage_level_{t}_hydro_1" in model.constraints
