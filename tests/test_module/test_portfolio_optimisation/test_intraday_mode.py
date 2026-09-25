"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Light unit tests for Portfolio Optimisation in Intraday mode.

They exercise the intraday-specific branches of the module — price source
selection, upstream energy, imbalance price, manual activation and output
routing — without building or solving any optimisation model. Day-ahead
counterparts are asserted alongside so the intraday behaviour is pinned
rather than merely exercised.
"""

from unittest.mock import Mock

import pendulum
import pytest
from pydantic import ValidationError

from atlas.enums import MarketType
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.portfolio_optimisation.input_objects.market_area import MarketAreaPO
from atlas.modules.portfolio_optimisation.input_objects.portfolio import PortfolioPO
from atlas.modules.portfolio_optimisation.input_objects.portfolio_equipments import PortfolioEquipments
from atlas.modules.portfolio_optimisation.input_objects.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.input_objects.wind import WindPO
from atlas.modules.portfolio_optimisation.output_dataset import PortfolioOptimisationOutputDataset
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.imbalance_price import estimate_imbalance_prices
from atlas.modules.portfolio_optimisation.utils.manual_activation import (
    _calculate_activated_power,
    _calculate_new_power,
)
from atlas.modules.portfolio_optimisation.utils.orchestration import PortfolioOptimisationResult
from atlas.objects.network.node import Node
from atlas.objects.network_operator.control_block import ControlBlock

# 24 hourly target times (2024-01-01 00:00 → 23:00), issued the day before as in
# an intraday session preparing the next delivery day.
START = pendulum.datetime(2024, 1, 1)
END = pendulum.datetime(2024, 1, 2)
EXECUTION = pendulum.datetime(2023, 12, 31, 22)
TIMESTEP = pendulum.duration(hours=1)
NB_STEPS = 24
TIME = START.add(hours=3)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _ts(value: float) -> Timeseries:
    """Flat Timeseries covering the target times plus the closing bound."""
    return Timeseries.from_values(start_date=START, frequency=TIMESTEP, values=[value] * (NB_STEPS + 1))


def _fm(value: float) -> ForecastingMatrix:
    """ForecastingMatrix holding a single flat forecast issued at ``EXECUTION``."""
    return ForecastingMatrix().add(_ts(value), EXECUTION)


def _parameters(*, market: MarketType = MarketType.intraday, use_forecast: bool = True, **kwargs):
    return PortfolioOptimisationParameters(
        temporal={"start_date": START, "end_date": END, "execution_date": EXECUTION, "timestep": TIMESTEP},
        market=market,
        use_forecast=use_forecast,
        **kwargs,
    )


def _market_area(**prices) -> MarketAreaPO:
    prices.setdefault("price_forecast_medium", _fm(500.0))
    return MarketAreaPO(name="test_market", control_block=ControlBlock(name="test_control_block"), **prices)


def _portfolio(**prices) -> PortfolioPO:
    market_area = _market_area(**prices)
    return PortfolioPO(
        name="test_portfolio",
        control_block=market_area.control_block,
        market_area=market_area,
        equipments=PortfolioEquipments(),
    )


def _equipment(da: float | None = None, total_id: float | None = None, id_cleared: float | None = None) -> Mock:
    """Equipment stub exposing only the cleared-quantity attributes read by the module."""
    return Mock(
        da_cleared_quantity=_ts(da) if da is not None else None,
        total_id_cleared_quantity=_ts(total_id) if total_id is not None else None,
        id_cleared_quantity=_fm(id_cleared) if id_cleared is not None else None,
    )


def _node(portfolio: PortfolioPO) -> Node:
    return Node(name="test_node", control_block=portfolio.control_block, market_area=portfolio.market_area)


def _wind_equipment() -> WindPO:
    """Wind unit attached to a fresh portfolio, with empty output attributes."""
    portfolio = _portfolio()
    equipment = WindPO(
        name="unit_1",
        node=_node(portfolio),
        portfolio=portfolio,
        maximum_fcr=0.0,
        maximum_afrr=0.0,
        maximum_power_forecast=_fm(100.0),
        maximum_curtailment_ratio=_ts(1.0),
        additional_hours=pendulum.duration(hours=0),
    )
    portfolio.equipments.add("wind", equipment)
    return equipment


def _thermal_equipment() -> ThermalPO:
    """Thermal unit attached to a fresh portfolio, with empty output attributes."""
    portfolio = _portfolio()
    equipment = ThermalPO(
        name="unit_1",
        node=_node(portfolio),
        portfolio=portfolio,
        maximum_fcr=0.0,
        maximum_afrr=0.0,
        maximum_power=_ts(100.0),
        variable_cost=_ts(50.0),
    )
    portfolio.equipments.add("thermal", equipment)
    return equipment


# ── Intraday price attributes ─────────────────────────────────────────────────


class TestMarketAreaIntradayValidation:
    """``set_market_context`` enforces the price attributes required in intraday."""

    @pytest.mark.parametrize(
        "use_forecast, required, provided",
        [(True, "id_price_forecast", "id_price"), (False, "id_price", "id_price_forecast")],
    )
    def test_missing_intraday_price_is_rejected(self, use_forecast, required, provided):
        market_area = _market_area(**{provided: _fm(30.0)})
        with pytest.raises(ValidationError, match=f"{required} is required"):
            market_area.set_market_context(MarketType.intraday, use_forecast)

    @pytest.mark.parametrize("use_forecast, required", [(True, "id_price_forecast"), (False, "id_price")])
    def test_expected_intraday_price_is_accepted(self, use_forecast, required):
        market_area = _market_area(**{required: _fm(30.0)})
        assert market_area.set_market_context(MarketType.intraday, use_forecast) is not None


# ── Price source selection ────────────────────────────────────────────────────


class TestGetPriceForecastIntraday:
    """``PortfolioPO.get_price_forecast`` reads the intraday price sources."""

    @pytest.mark.parametrize(
        "market, use_forecast, expected",
        [
            (MarketType.intraday, True, 35.0),  # id_price_forecast
            (MarketType.intraday, False, 60.0),  # id_price
            (MarketType.dayahead, False, 40.0),  # da_price
        ],
    )
    def test_price_source_per_market(self, market, use_forecast, expected):
        portfolio = _portfolio(id_price_forecast=_fm(35.0), id_price=_fm(60.0), da_price=_ts(40.0))

        assert portfolio.get_price_forecast(TIME, _parameters(market=market, use_forecast=use_forecast)) == expected

    def test_returns_none_when_id_price_forecast_missing(self):
        assert _portfolio().get_price_forecast(TIME, _parameters()) is None

    def test_falls_back_to_medium_forecast_outside_target_times(self):
        """Times outside the optimisation window always use ``price_forecast_medium``."""
        parameters = _parameters()

        assert END not in parameters.target_times
        assert _portfolio(id_price_forecast=_fm(35.0)).get_price_forecast(END, parameters) == 500.0


# ── Upstream energy ───────────────────────────────────────────────────────────


class TestUpstreamEnergyIntraday:
    """In intraday, upstream energy cumulates the day-ahead and intraday clearings."""

    @pytest.mark.parametrize(
        "da, total_id, expected",
        [(10.0, 2.5, 12.5), (None, 3.0, 3.0), (7.0, None, 7.0), (None, None, 0.0)],
    )
    def test_cumulates_day_ahead_and_intraday(self, da, total_id, expected):
        assert PortfolioPO._get_upstream_energy(_equipment(da, total_id), TIME, _parameters()) == expected

    def test_day_ahead_ignores_cumulated_intraday(self):
        parameters = _parameters(market=MarketType.dayahead, use_forecast=False)

        assert PortfolioPO._get_upstream_energy(_equipment(da=10.0, total_id=2.5), TIME, parameters) == 10.0


# ── Imbalance prices ──────────────────────────────────────────────────────────


class TestImbalancePriceIntraday:
    """The imbalance settlement price is anchored on the intraday price."""

    @staticmethod
    def _estimate(price: float, **kwargs) -> tuple[float, float, float, float]:
        """Return (down, up, large_down, large_up) for an intraday price of ``price``."""
        market_area = _market_area(id_price_forecast=_fm(price), id_price=_fm(price))
        parameters = _parameters(
            small_imbalance_penalty=0.1, large_imbalance_penalty=0.2, isp_forecast_lower_bound=10, **kwargs
        )
        return estimate_imbalance_prices(TIME, market_area, ControlBlock(name="test_control_block"), parameters)

    @pytest.mark.parametrize("use_forecast", [True, False])
    def test_reference_price_read_from_intraday_prices(self, use_forecast):
        """``id_price_forecast`` and ``id_price`` are both valid anchors."""
        assert self._estimate(100.0, use_forecast=use_forecast) == pytest.approx((90.0, 110.0, 80.0, 120.0))

    @pytest.mark.parametrize(
        "price, expected",
        [
            (100.0, (90.0, 110.0, 80.0, 120.0)),
            (2.0, (9.0, 11.0, 8.0, 12.0)),  # floored at isp_forecast_lower_bound
            (-50.0, (-55.0, -45.0, -60.0, -40.0)),  # penalties reversed on negative prices
        ],
    )
    def test_penalties_applied_around_intraday_price(self, price, expected):
        assert self._estimate(price) == pytest.approx(expected)


# ── Manual activation ─────────────────────────────────────────────────────────


class TestManualActivationPowerIntraday:
    """Manual activation in intraday works on day-ahead plus cumulated intraday power."""

    @pytest.mark.parametrize("da, total_id, expected", [(10.0, 2.0, 12.0), (10.0, None, 10.0), (None, 2.0, 2.0)])
    def test_new_power_sums_day_ahead_and_cumulated_intraday(self, da, total_id, expected):
        new_power = _calculate_new_power(_equipment(da, total_id), _parameters())

        assert new_power.values == [expected] * NB_STEPS

    def test_day_ahead_new_power_ignores_cumulated_intraday(self):
        parameters = _parameters(market=MarketType.dayahead, use_forecast=False)
        new_power = _calculate_new_power(_equipment(da=10.0, total_id=2.0), parameters)

        assert new_power.values == [10.0] * NB_STEPS

    @pytest.mark.parametrize("id_cleared, expected", [(3.0, 3.0), (None, 0.0)])
    def test_activated_power_reads_id_cleared_quantity(self, id_cleared, expected):
        activated = _calculate_activated_power(_equipment(da=10.0, id_cleared=id_cleared), _parameters())

        assert set(activated.values) == {expected}


# ── Output routing ────────────────────────────────────────────────────────────


class TestOutputRoutingIntraday:
    """In intraday (``use_forecast=True``) results land in ``id_po_for_orders``."""

    @staticmethod
    def _update(parameters, equipment: WindPO | ThermalPO, power: float = 7.0) -> None:
        """Write the schedules of the portfolio holding ``equipment``, every solver value being ``power``."""
        result = Mock(spec=PortfolioOptimisationResult)
        result.get_variable_value.return_value = power
        result.portfolio = equipment.portfolio
        result.is_manual_activation = False
        PortfolioOptimisationOutputDataset(parameters=parameters, optimisation_results=[result]).update_equipments()

    @pytest.mark.parametrize(
        "use_forecast, written, untouched",
        [(True, "id_po_for_orders", "power"), (False, "power", "id_po_for_orders")],
    )
    def test_result_attribute_depends_on_forecast_mode(self, use_forecast, written, untouched):
        equipment = _wind_equipment()
        self._update(_parameters(use_forecast=use_forecast), equipment)

        assert getattr(equipment, untouched) is None
        assert getattr(equipment, written).get_forecast(EXECUTION, START, END - TIMESTEP).values == [7.0] * NB_STEPS

    def test_thermal_state_sequence_still_written_in_intraday(self):
        equipment = _thermal_equipment()
        # A solver value of 1.0 also sets a thermal state indicator, which is read as an operating state.
        self._update(_parameters(), equipment, power=1.0)

        assert equipment.power is None
        assert equipment.id_po_for_orders is not None
        assert equipment.state_sequence is not None
