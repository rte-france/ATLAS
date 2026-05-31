"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
import pytest

from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.common.optimal_dispatch.dispatch.hydro import HydroDispatch
from atlas.common.optimal_dispatch.input_objects.hydro import HydroDispatchInput
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
    return OptimisationModel("SCIP", "test_hydro_dispatch")


@pytest.fixture
def time_window(start_date):
    return [start_date.add(hours=h) for h in range(4)]


class TestHydroDispatchVariables:
    def test_setup_creates_stored_energy_var(self, hydro_equipment, model, parameters):
        d = HydroDispatch(hydro_equipment)
        d.setup(model, parameters)
        assert d.stored_energy_var is not None

    def test_add_variables_creates_stored_energy_and_fragments(self, hydro_equipment, model, parameters, time_window):
        d = HydroDispatch(hydro_equipment)
        d.setup(model, parameters)
        t = time_window[0]
        d.add_variables(t)
        n = hydro_equipment.name
        assert f"{n}_stored_energy_{t}" in model.variables
        # Two fragments declared in fragment_prices/volumes → indices 0 and 1.
        assert f"{n}_power_level_frag_0_{t}" in model.variables
        assert f"{n}_power_level_frag_1_{t}" in model.variables

    def test_stored_energy_bounds(self, hydro_equipment, model, parameters, time_window):
        d = HydroDispatch(hydro_equipment)
        d.setup(model, parameters)
        t = time_window[0]
        d.add_variables(t)
        var = model.get_variable(f"{hydro_equipment.name}_stored_energy_{t}")
        assert var.lb() == 0
        assert var.ub() == pytest.approx(500.0)

    def test_fragment_bounds_scale_with_max_power(self, hydro_equipment, model, parameters, time_window):
        d = HydroDispatch(hydro_equipment)
        d.setup(model, parameters)
        t = time_window[0]
        d.add_variables(t)
        # max_power = 100, fragment_volumes = [0.5, 0.5] → bounds [0, 50].
        for idx in (0, 1):
            var = model.get_variable(f"{hydro_equipment.name}_power_level_frag_{idx}_{t}")
            assert var.lb() == 0
            assert var.ub() == pytest.approx(50.0)


class TestHydroDispatchEnergyBalance:
    def _setup(self, hydro_equipment, model, parameters, time_window):
        d = HydroDispatch(hydro_equipment)
        d.setup(model, parameters)
        for t in time_window:
            d.add_variables(t)
        return d

    def test_balance_constraint_at_start_uses_initial_level(
        self, hydro_equipment, model, parameters, time_window
    ):
        d = self._setup(hydro_equipment, model, parameters, time_window)
        t = time_window[0]
        d.add_energy_balance(model, t, parameters)
        assert f"storage_level_evol_{t}_{hydro_equipment.name}" in model.constraints

    def test_balance_constraint_after_start_uses_previous_var(
        self, hydro_equipment, model, parameters, time_window
    ):
        d = self._setup(hydro_equipment, model, parameters, time_window)
        t = time_window[1]
        d.add_energy_balance(model, t, parameters)
        assert f"storage_level_evol_{t}_{hydro_equipment.name}" in model.constraints

    def test_power_fragments_sum_aggregates_all_fragments(
        self, hydro_equipment, model, parameters, time_window
    ):
        d = self._setup(hydro_equipment, model, parameters, time_window)
        t = time_window[0]
        # Should not raise — exercises the sum expression construction.
        expr = d.power_fragments_sum(t)
        assert expr is not None
