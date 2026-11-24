"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Unit tests for the handling of non-dispatchable equipments (base loads and other
non-dispatchable units) by the portfolio optimisation: residual energy of the portfolio,
imbalance bounds and schedule written onto the equipments.
"""

from unittest.mock import Mock

import pendulum
import pytest

from atlas.enums import LoadType, MarketType
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.portfolio_optimisation.input_objects.load import LoadPO
from atlas.modules.portfolio_optimisation.input_objects.market_area import MarketAreaPO
from atlas.modules.portfolio_optimisation.input_objects.other_non_dispatchable import OtherNonDispatchablePO
from atlas.modules.portfolio_optimisation.input_objects.portfolio import PortfolioPO
from atlas.modules.portfolio_optimisation.input_objects.portfolio_equipments import PortfolioEquipments
from atlas.modules.portfolio_optimisation.result import PortfolioOptimisationResult
from atlas.modules.portfolio_optimisation.steps.portfolio import PortfolioStep
from atlas.modules.portfolio_optimisation.utils.orchestration import SinglePortfolioResult
from atlas.objects.network.node import Node
from atlas.objects.network_operator.control_block import ControlBlock

EXECUTION_DATE = pendulum.datetime(2024, 1, 1)
TIMESTEP = pendulum.duration(hours=1)
TARGET_TIMES = [EXECUTION_DATE.add(hours=h) for h in range(3)]
MAXIMUM_IMBALANCE = 5.0

# ── Helpers ───────────────────────────────────────────────────────────────────


def _timeseries(values: list[float]) -> Timeseries:
    return Timeseries.from_values(start_date=TARGET_TIMES[0], frequency=TIMESTEP, values=values)


def _parameters(*, use_forecast: bool = False) -> Mock:
    parameters = Mock()
    parameters.market = MarketType.dayahead
    parameters.use_forecast = use_forecast
    parameters.is_portfolio_bidding = True
    parameters.maximum_imbalance = MAXIMUM_IMBALANCE
    parameters.portfolio_time_window = TARGET_TIMES
    parameters.temporal.timestep = TIMESTEP
    parameters.temporal.execution_date = EXECUTION_DATE
    return parameters


@pytest.fixture
def portfolio() -> PortfolioPO:
    control_block = ControlBlock(name="cb")
    market_area = MarketAreaPO(name="ma", control_block=control_block, price_forecast_medium=ForecastingMatrix())
    return PortfolioPO(
        name="pf", control_block=control_block, market_area=market_area, equipments=PortfolioEquipments()
    )


def _add_load(portfolio: PortfolioPO, forecast: list[float], cleared: list[float]) -> LoadPO:
    """Add a base load forecast to consume *forecast* and having bought *cleared* (negative values)."""
    load = LoadPO(
        name="load",
        node=Node(name="node", control_block=portfolio.control_block, market_area=portfolio.market_area),
        portfolio=portfolio,
        maximum_fcr=0.0,
        maximum_afrr=0.0,
        load_type=LoadType.BASE_LOAD,
        maximum_power_forecast=ForecastingMatrix().add(_timeseries(forecast), EXECUTION_DATE),
        da_cleared_quantity=_timeseries(cleared),
        additional_hours=pendulum.duration(hours=0),
    )
    portfolio.equipments.add("non_dispatchable_load", load)
    return load


def _add_other_non_dispatchable(
    portfolio: PortfolioPO, forecast: list[float], cleared: list[float]
) -> OtherNonDispatchablePO:
    """Add an other non-dispatchable unit forecast to produce *forecast* and having sold *cleared*."""
    other = OtherNonDispatchablePO(
        name="ond",
        node=Node(name="node", control_block=portfolio.control_block, market_area=portfolio.market_area),
        portfolio=portfolio,
        maximum_fcr=0.0,
        maximum_afrr=0.0,
        maximum_power_forecast=ForecastingMatrix().add(_timeseries(forecast), EXECUTION_DATE),
        da_cleared_quantity=_timeseries(cleared),
        additional_hours=pendulum.duration(hours=0),
    )
    portfolio.equipments.add("other_non_dispatchable", other)
    return other


def _forecast_values(matrix: ForecastingMatrix) -> list[float]:
    return matrix.get_forecast(EXECUTION_DATE, TARGET_TIMES[0], TARGET_TIMES[-1]).values


# ── Residual energy ───────────────────────────────────────────────────────────


class TestResidualEnergy:
    def test_load_consuming_more_than_bought_makes_the_portfolio_short(self, portfolio):
        _add_load(portfolio, forecast=[-120.0] * 3, cleared=[-100.0] * 3)

        residual = portfolio.compute_residual_energy(_parameters())

        assert list(residual.values()) == [20.0, 20.0, 20.0]

    def test_load_consuming_less_than_bought_makes_the_portfolio_long(self, portfolio):
        _add_load(portfolio, forecast=[-80.0] * 3, cleared=[-100.0] * 3)

        residual = portfolio.compute_residual_energy(_parameters())

        assert list(residual.values()) == [-20.0, -20.0, -20.0]

    def test_load_reads_its_forecast_per_time(self, portfolio):
        _add_load(portfolio, forecast=[-100.0, -110.0, -90.0], cleared=[-100.0] * 3)

        residual = portfolio.compute_residual_energy(_parameters())

        assert residual == {TARGET_TIMES[0]: 0.0, TARGET_TIMES[1]: 10.0, TARGET_TIMES[2]: -10.0}

    def test_other_non_dispatchable_is_not_curtailed(self, portfolio):
        """Producing more than sold makes the portfolio long, producing less makes it short."""
        _add_other_non_dispatchable(portfolio, forecast=[120.0, 80.0, 100.0], cleared=[100.0] * 3)

        residual = portfolio.compute_residual_energy(_parameters())

        assert list(residual.values()) == [-20.0, 20.0, 0.0]

    def test_contributions_add_up(self, portfolio):
        _add_load(portfolio, forecast=[-80.0] * 3, cleared=[-100.0] * 3)
        _add_other_non_dispatchable(portfolio, forecast=[80.0] * 3, cleared=[100.0] * 3)

        residual = portfolio.compute_residual_energy(_parameters())

        assert list(residual.values()) == [0.0, 0.0, 0.0]


class TestImbalanceLimit:
    def test_covers_a_surplus_larger_than_the_maximum_imbalance(self, portfolio):
        _add_load(portfolio, forecast=[-80.0] * 3, cleared=[-100.0] * 3)

        limit = PortfolioStep(portfolio)._get_overall_imbalance_limit(_parameters())

        assert list(limit.values()) == [20.0, 20.0, 20.0]

    def test_falls_back_on_the_maximum_imbalance(self, portfolio):
        _add_load(portfolio, forecast=[-100.0, -102.0, -98.0], cleared=[-100.0] * 3)

        limit = PortfolioStep(portfolio)._get_overall_imbalance_limit(_parameters())

        assert list(limit.values()) == [MAXIMUM_IMBALANCE] * 3


# ── Results ───────────────────────────────────────────────────────────────────


def _result(portfolio: PortfolioPO) -> SinglePortfolioResult:
    imbalances = {
        f"pf_{size}_imbalance_{direction}": _timeseries([0.0] * 3)
        for size in ("small", "large")
        for direction in ("up", "down")
    }
    return SinglePortfolioResult(portfolio=portfolio, solution_info=None, solution=imbalances)


class TestLoadSchedule:
    def test_power_is_the_forecasted_consumption_not_the_bought_volume(self, portfolio):
        load = _add_load(portfolio, forecast=[-80.0, -90.0, -100.0], cleared=[-100.0] * 3)

        PortfolioOptimisationResult(_parameters(), [_result(portfolio)]).build_change_sets()

        assert _forecast_values(load.power) == [-80.0, -90.0, -100.0]
        assert load.id_po_for_orders is None

    def test_forecasted_consumption_enters_the_portfolio_power(self, portfolio):
        _add_load(portfolio, forecast=[-80.0] * 3, cleared=[-100.0] * 3)

        PortfolioOptimisationResult(_parameters(), [_result(portfolio)]).build_change_sets()

        assert _forecast_values(portfolio.power) == [-80.0, -80.0, -80.0]

    def test_load_changeset_carries_the_forecasted_consumption(self, portfolio):
        _add_load(portfolio, forecast=[-80.0] * 3, cleared=[-100.0] * 3)

        change_sets = PortfolioOptimisationResult(_parameters(), [_result(portfolio)]).build_change_sets()

        load_change_set = next(change_set for change_set in change_sets if change_set.data["name"] == "load")
        assert _forecast_values(load_change_set.data["power"]) == [-80.0, -80.0, -80.0]

    def test_forecast_mode_routes_the_consumption_to_id_po_for_orders(self, portfolio):
        load = _add_load(portfolio, forecast=[-80.0] * 3, cleared=[-100.0] * 3)

        PortfolioOptimisationResult(_parameters(use_forecast=True), [_result(portfolio)]).update_equipments()

        assert _forecast_values(load.id_po_for_orders) == [-80.0, -80.0, -80.0]
        assert load.power is None

    def test_other_non_dispatchable_power_is_the_forecasted_production_not_the_sold_volume(self, portfolio):
        other = _add_other_non_dispatchable(portfolio, forecast=[120.0, 80.0, 100.0], cleared=[100.0] * 3)

        change_sets = PortfolioOptimisationResult(_parameters(), [_result(portfolio)]).build_change_sets()

        assert _forecast_values(other.power) == [120.0, 80.0, 100.0]
        other_change_set = next(change_set for change_set in change_sets if change_set.data["name"] == "ond")
        assert _forecast_values(other_change_set.data["power"]) == [120.0, 80.0, 100.0]

    def test_portfolio_power_sums_the_non_dispatchable_forecasts(self, portfolio):
        _add_load(portfolio, forecast=[-80.0] * 3, cleared=[-100.0] * 3)
        _add_other_non_dispatchable(portfolio, forecast=[120.0] * 3, cleared=[100.0] * 3)

        PortfolioOptimisationResult(_parameters(), [_result(portfolio)]).build_change_sets()

        assert _forecast_values(portfolio.power) == [40.0, 40.0, 40.0]

    def test_forecast_mode_routes_the_other_non_dispatchable_production_to_id_po_for_orders(self, portfolio):
        other = _add_other_non_dispatchable(portfolio, forecast=[120.0] * 3, cleared=[100.0] * 3)

        PortfolioOptimisationResult(_parameters(use_forecast=True), [_result(portfolio)]).update_equipments()

        assert _forecast_values(other.id_po_for_orders) == [120.0, 120.0, 120.0]
        assert other.power is None

    def test_manual_activation_is_left_alone(self, portfolio):
        load = _add_load(portfolio, forecast=[-80.0] * 3, cleared=[-100.0] * 3)
        result = SinglePortfolioResult(portfolio=portfolio, solution_info=None, is_manual_activation=True)

        PortfolioOptimisationResult(_parameters(), [result]).update_equipments()

        assert load.power is None
