"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Unit tests for PortfolioOptimisationOutputDataset: writing of the optimised schedules onto
portfolio and equipment objects, and emission of the resulting changesets.
"""

from unittest.mock import Mock

import pendulum
import pytest

from atlas.abstract_class.dataset import AbstractModuleOutput
from atlas.enums import BusinessModelName, ThermalDispatchState
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.portfolio_optimisation.input_objects.market_area import MarketAreaPO
from atlas.modules.portfolio_optimisation.input_objects.portfolio import PortfolioPO
from atlas.modules.portfolio_optimisation.input_objects.portfolio_equipments import PortfolioEquipments
from atlas.modules.portfolio_optimisation.input_objects.solar import SolarPO
from atlas.modules.portfolio_optimisation.input_objects.storage import StoragePO
from atlas.modules.portfolio_optimisation.input_objects.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.output_dataset import PortfolioOptimisationOutputDataset
from atlas.objects.network.node import Node
from atlas.objects.network_operator.control_block import ControlBlock

EXECUTION_DATE = pendulum.datetime(2024, 1, 1)
TIMESTEP = pendulum.duration(hours=1)
TARGET_TIMES = [EXECUTION_DATE.add(hours=h) for h in range(3)]

# ── Helpers ───────────────────────────────────────────────────────────────────


def _timeseries(values: list[float]) -> Timeseries:
    return Timeseries.from_values(start_date=TARGET_TIMES[0], frequency=TIMESTEP, values=values)


def _parameters(*, is_portfolio_bidding: bool = True, use_forecast: bool = False) -> Mock:
    parameters = Mock()
    parameters.is_portfolio_bidding = is_portfolio_bidding
    parameters.use_forecast = use_forecast
    parameters.allowed_round_off_error = 0.01
    parameters.target_times = TARGET_TIMES
    parameters.temporal.timestep = TIMESTEP
    parameters.temporal.execution_date = EXECUTION_DATE
    return parameters


def _result(portfolio: PortfolioPO, variable_values: dict[str, float], is_manual_activation: bool = False) -> Mock:
    result = Mock()
    result.portfolio = portfolio
    result.is_manual_activation = is_manual_activation
    result.get_variable_value.side_effect = lambda name: variable_values.get(name, 0.0)
    return result


@pytest.fixture(autouse=True)
def _isolate_change_sets():
    """AbstractModuleOutput.change_sets is a class-level list shared by every output instance."""
    AbstractModuleOutput.change_sets = []
    yield
    AbstractModuleOutput.change_sets = []


@pytest.fixture
def portfolio() -> PortfolioPO:
    """A portfolio holding one thermal, one storage and one solar unit."""
    control_block = ControlBlock(name="cb")
    market_area = MarketAreaPO(name="ma", control_block=control_block, price_forecast_medium=ForecastingMatrix())
    node = Node(name="node", control_block=control_block, market_area=market_area)
    portfolio = PortfolioPO(
        name="pf", control_block=control_block, market_area=market_area, equipments=PortfolioEquipments()
    )

    power_curve = _timeseries([100.0, 100.0, 100.0])
    portfolio.equipments.add(
        "thermal",
        ThermalPO(
            name="th",
            node=node,
            portfolio=portfolio,
            maximum_fcr=0.0,
            maximum_afrr=0.0,
            maximum_power=power_curve,
            variable_cost=power_curve,
        ),
    )
    portfolio.equipments.add(
        "storage",
        StoragePO(
            name="st",
            node=node,
            portfolio=portfolio,
            storage_type="Battery",
            maximum_fcr=0.0,
            maximum_afrr=0.0,
            minimum_power=power_curve,
            maximum_power=power_curve,
            minimum_state_of_charge=power_curve,
            discharge_efficiency=1.0,
            charge_efficiency=1.0,
            maximum_energy=power_curve,
            additional_hours=pendulum.duration(hours=0),
        ),
    )
    portfolio.equipments.add(
        "solar",
        SolarPO(
            name="so",
            node=node,
            portfolio=portfolio,
            maximum_fcr=0.0,
            maximum_afrr=0.0,
            maximum_curtailment_ratio=power_curve,
            maximum_power_forecast=ForecastingMatrix().add(power_curve, EXECUTION_DATE),
            additional_hours=pendulum.duration(hours=0),
        ),
    )
    return portfolio


def _equipment_by_name(portfolio: PortfolioPO, name: str):
    return next(equipment for equipment in portfolio.equipments.get_all_equipment() if equipment.name == name)


def _forecast_values(matrix: ForecastingMatrix) -> list[float]:
    return matrix.get_forecast(EXECUTION_DATE, TARGET_TIMES[0], TARGET_TIMES[-1]).values


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestEquipmentSchedules:
    def test_writes_thermal_power_and_state_sequence(self, portfolio):
        values = {f"th_power_level_{time}": 50.0 for time in TARGET_TIMES}
        values |= {f"on_flat_th_{time}": 1 for time in TARGET_TIMES}
        dataset = PortfolioOptimisationOutputDataset(_parameters(), [_result(portfolio, values)])

        dataset.update_equipments()

        thermal = _equipment_by_name(portfolio, "th")
        assert _forecast_values(thermal.power) == [50.0, 50.0, 50.0]
        assert (
            thermal.state_sequence[EXECUTION_DATE.to_datetime_string()].values
            == [float(ThermalDispatchState.ON_FLAT)] * 3
        )

    def test_writes_storage_power_and_stored_energy(self, portfolio):
        values = {f"st_power_level_sell_{time}": 20.0 for time in TARGET_TIMES}
        values |= {f"st_stored_energy_{time}": 80.0 for time in TARGET_TIMES}
        dataset = PortfolioOptimisationOutputDataset(_parameters(), [_result(portfolio, values)])

        dataset.update_equipments()

        storage = _equipment_by_name(portfolio, "st")
        assert _forecast_values(storage.power) == [20.0, 20.0, 20.0]
        assert _forecast_values(storage.stored_energy) == [80.0, 80.0, 80.0]

    def test_overwrites_an_execution_date_already_present(self, portfolio):
        solar = _equipment_by_name(portfolio, "so")
        solar.power = ForecastingMatrix().add(_timeseries([1.0, 1.0, 1.0]), EXECUTION_DATE)
        values = {f"so_power_level_{time}": 9.0 for time in TARGET_TIMES}
        dataset = PortfolioOptimisationOutputDataset(_parameters(), [_result(portfolio, values)])

        dataset.update_equipments()

        assert _forecast_values(solar.power) == [9.0, 9.0, 9.0]
        assert len(solar.power.index) == 1


class TestForecastMode:
    def test_routes_power_to_id_po_for_orders_and_spares_the_committed_schedules(self, portfolio):
        values = {f"so_power_level_{time}": 7.0 for time in TARGET_TIMES}
        values |= {f"st_stored_energy_{time}": 80.0 for time in TARGET_TIMES}
        values |= {f"on_up_th_{time}": 1 for time in TARGET_TIMES}
        dataset = PortfolioOptimisationOutputDataset(_parameters(use_forecast=True), [_result(portfolio, values)])

        dataset.update_equipments()

        solar = _equipment_by_name(portfolio, "so")
        assert _forecast_values(solar.id_po_for_orders) == [7.0, 7.0, 7.0]
        assert solar.power is None
        assert _equipment_by_name(portfolio, "st").stored_energy is None
        assert _equipment_by_name(portfolio, "th").state_sequence is not None


class TestPortfolioLevel:
    def test_imbalance_is_positive_when_short(self, portfolio):
        values = {f"pf_large_imbalance_down_{time}": 10.0 for time in TARGET_TIMES}
        values |= {f"pf_small_imbalance_up_{time}": 4.0 for time in TARGET_TIMES}
        dataset = PortfolioOptimisationOutputDataset(_parameters(), [_result(portfolio, values)])

        dataset.update_portfolios()

        assert _forecast_values(portfolio.imbalance) == [6.0, 6.0, 6.0]

    def test_power_sums_the_equipment_schedules(self, portfolio):
        values = {f"th_power_level_{time}": 50.0 for time in TARGET_TIMES}
        values |= {f"so_power_level_{time}": 5.0 for time in TARGET_TIMES}
        values |= {f"st_power_level_sell_{time}": 20.0 for time in TARGET_TIMES}
        dataset = PortfolioOptimisationOutputDataset(_parameters(), [_result(portfolio, values)])

        dataset.update_equipments()
        dataset.update_portfolios()

        assert _forecast_values(portfolio.power) == [75.0, 75.0, 75.0]


class TestIndividualEquipmentMode:
    def test_writes_equipment_schedules_but_nothing_at_portfolio_level(self, portfolio):
        """Individual mode optimises one equipment per synthetic portfolio; results must land."""
        values = {f"so_power_level_{time}": 12.0 for time in TARGET_TIMES}
        dataset = PortfolioOptimisationOutputDataset(
            _parameters(is_portfolio_bidding=False), [_result(portfolio, values)]
        )

        dataset.build_change_sets()

        assert _forecast_values(_equipment_by_name(portfolio, "so").power) == [12.0, 12.0, 12.0]
        assert portfolio.imbalance is None
        assert portfolio.power is None
        model_types = [change_set.model_type for change_set in dataset.change_sets]
        assert BusinessModelName.PORTFOLIO not in model_types
        assert BusinessModelName.SOLAR in model_types


class TestManualActivation:
    def test_leaves_schedules_alone_and_emits_no_portfolio_changeset(self, portfolio):
        values = {f"so_power_level_{time}": 12.0 for time in TARGET_TIMES}
        dataset = PortfolioOptimisationOutputDataset(
            _parameters(), [_result(portfolio, values, is_manual_activation=True)]
        )

        dataset.build_change_sets()

        assert _equipment_by_name(portfolio, "so").power is None
        model_types = [change_set.model_type for change_set in dataset.change_sets]
        assert BusinessModelName.PORTFOLIO not in model_types
        assert BusinessModelName.THERMAL in model_types


class TestChangeSets:
    def test_emits_one_changeset_per_object(self, portfolio):
        dataset = PortfolioOptimisationOutputDataset(_parameters(), [_result(portfolio, {})])

        dataset.build_change_sets()

        assert len(dataset.change_sets) == 4  # one portfolio + three equipments

    def test_payload_carries_the_optimised_attributes(self, portfolio):
        values = {f"st_power_level_sell_{time}": 20.0 for time in TARGET_TIMES}
        dataset = PortfolioOptimisationOutputDataset(_parameters(), [_result(portfolio, values)])

        dataset.build_change_sets()

        storage_change_set = next(
            change_set for change_set in dataset.change_sets if change_set.model_type == BusinessModelName.STORAGE
        )
        assert storage_change_set.data["name"] == "st"
        assert _forecast_values(storage_change_set.data["power"]) == [20.0, 20.0, 20.0]
        assert "stored_energy" in storage_change_set.data
