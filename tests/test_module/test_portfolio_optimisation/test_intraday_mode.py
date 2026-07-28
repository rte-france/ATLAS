"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Light unit tests for Portfolio Optimisation in Intraday mode.

These tests exercise the intraday-specific branches of the module without
building or solving any optimisation model:

- ``MarketAreaPO`` validation of the intraday price attributes
- ``PortfolioPO.get_price_forecast`` price source selection
- ``PortfolioPO._get_upstream_energy`` (day-ahead + cumulated intraday)
- imbalance reference price lookup
- manual activation power computation
- output routing towards ``id_po_for_orders``

Day-ahead counterparts are asserted alongside a few cases so that the
intraday-specific behaviour is pinned rather than merely exercised.
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
from atlas.modules.portfolio_optimisation.utils.imbalance_price import (
    _get_actual_price,
    _get_forecast_price,
    estimate_imbalance_prices,
)
from atlas.modules.portfolio_optimisation.utils.manual_activation import (
    _calculate_activated_power,
    _calculate_new_power,
)
from atlas.modules.portfolio_optimisation.utils.orchestration import PortfolioOptimisationResult
from atlas.objects.network_operator.control_block import ControlBlock

# ── Test horizon ──────────────────────────────────────────────────────────────
# 24 hourly target times (2024-01-01 00:00 → 23:00); the execution date is the
# day before, as in an intraday session preparing the next delivery day.

START = pendulum.datetime(2024, 1, 1)
END = pendulum.datetime(2024, 1, 2)
EXECUTION = pendulum.datetime(2023, 12, 31, 22)
TIMESTEP = pendulum.duration(hours=1)
NB_STEPS = 24

# ── Helpers ───────────────────────────────────────────────────────────────────


def _ts(value: float, nb_steps: int = NB_STEPS + 1) -> Timeseries:
    """Flat Timeseries covering the target times (plus the closing bound)."""
    return Timeseries.from_values(start_date=START, frequency=TIMESTEP, values=[value] * nb_steps)


def _fm(value: float, nb_steps: int = NB_STEPS + 1) -> ForecastingMatrix:
    """ForecastingMatrix holding a single flat forecast issued at ``EXECUTION``."""
    return ForecastingMatrix().add(_ts(value, nb_steps), EXECUTION)


def _parameters(*, market: MarketType = MarketType.intraday, use_forecast: bool = True, **kwargs):
    return PortfolioOptimisationParameters(
        temporal={
            "start_date": START,
            "end_date": END,
            "execution_date": EXECUTION,
            "timestep": TIMESTEP,
        },
        market=market,
        use_forecast=use_forecast,
        **kwargs,
    )


def _market_area(**kwargs) -> MarketAreaPO:
    """MarketAreaPO with only ``price_forecast_medium`` set by default."""
    kwargs.setdefault("price_forecast_medium", _fm(500.0))
    return MarketAreaPO(name="test_market", control_block=ControlBlock(name="test_control_block"), **kwargs)


def _portfolio(market_area: MarketAreaPO) -> PortfolioPO:
    return PortfolioPO(
        name="test_portfolio",
        control_block=market_area.control_block,
        market_area=market_area,
        equipments=PortfolioEquipments(),
    )


# ── MarketAreaPO validation ───────────────────────────────────────────────────


class TestMarketAreaIntradayValidation:
    """``set_market_context`` enforces the price attributes required in intraday."""

    def test_id_price_forecast_required_when_use_forecast(self):
        market_area = _market_area(id_price=_fm(30.0))
        with pytest.raises(ValidationError, match="id_price_forecast is required"):
            market_area.set_market_context(MarketType.intraday, use_forecast=True)

    def test_id_price_required_when_not_use_forecast(self):
        market_area = _market_area(id_price_forecast=_fm(30.0))
        with pytest.raises(ValidationError, match="id_price is required"):
            market_area.set_market_context(MarketType.intraday, use_forecast=False)

    def test_valid_with_id_price_forecast_and_use_forecast(self):
        market_area = _market_area(id_price_forecast=_fm(30.0))
        assert market_area.set_market_context(MarketType.intraday, use_forecast=True) is not None

    def test_valid_with_id_price_and_no_forecast(self):
        market_area = _market_area(id_price=_fm(30.0))
        assert market_area.set_market_context(MarketType.intraday, use_forecast=False) is not None

    def test_no_validation_without_market_context(self):
        """Building the object directly (no context) must not require intraday prices."""
        assert _market_area().id_price is None

    def test_day_ahead_context_does_not_require_intraday_prices(self):
        market_area = _market_area(da_price=_ts(40.0))
        assert market_area.set_market_context(MarketType.dayahead, use_forecast=False) is not None


# ── Price forecast selection ──────────────────────────────────────────────────


class TestGetPriceForecastIntraday:
    """``PortfolioPO.get_price_forecast`` reads the intraday price sources."""

    def test_uses_id_price_forecast_when_use_forecast(self):
        portfolio = _portfolio(_market_area(id_price_forecast=_fm(35.0), id_price=_fm(60.0)))
        parameters = _parameters(use_forecast=True)

        assert portfolio.get_price_forecast(START.add(hours=3), parameters) == 35.0

    def test_uses_id_price_when_not_use_forecast(self):
        portfolio = _portfolio(_market_area(id_price_forecast=_fm(35.0), id_price=_fm(60.0)))
        parameters = _parameters(use_forecast=False)

        assert portfolio.get_price_forecast(START.add(hours=3), parameters) == 60.0

    def test_returns_none_when_id_price_forecast_missing(self):
        portfolio = _portfolio(_market_area())
        parameters = _parameters(use_forecast=True)

        assert portfolio.get_price_forecast(START.add(hours=3), parameters) is None

    def test_falls_back_to_medium_forecast_outside_target_times(self):
        """Times outside the optimisation window always use ``price_forecast_medium``."""
        portfolio = _portfolio(_market_area(id_price_forecast=_fm(35.0)))
        parameters = _parameters(use_forecast=True)

        assert END not in parameters.target_times
        assert portfolio.get_price_forecast(END, parameters) == 500.0

    def test_day_ahead_ignores_intraday_prices(self):
        portfolio = _portfolio(_market_area(id_price=_fm(60.0), da_price=_ts(40.0)))
        parameters = _parameters(market=MarketType.dayahead, use_forecast=False)

        assert portfolio.get_price_forecast(START.add(hours=3), parameters) == 40.0


# ── Upstream energy ───────────────────────────────────────────────────────────


class TestUpstreamEnergyIntraday:
    """In intraday, upstream energy cumulates the day-ahead and intraday clearings."""

    @staticmethod
    def _equipment(da: float | None, total_id: float | None) -> Mock:
        equipment = Mock()
        equipment.da_cleared_quantity = _ts(da) if da is not None else None
        equipment.total_id_cleared_quantity = _ts(total_id) if total_id is not None else None
        return equipment

    def test_sums_day_ahead_and_cumulated_intraday(self):
        parameters = _parameters()
        equipment = self._equipment(da=10.0, total_id=2.5)

        assert PortfolioPO._get_upstream_energy(equipment, START.add(hours=5), parameters) == 12.5

    def test_negative_intraday_reduces_upstream_energy(self):
        parameters = _parameters()
        equipment = self._equipment(da=10.0, total_id=-4.0)

        assert PortfolioPO._get_upstream_energy(equipment, START.add(hours=5), parameters) == 6.0

    @pytest.mark.parametrize(
        "da, total_id, expected",
        [(None, 3.0, 3.0), (7.0, None, 7.0), (None, None, 0.0)],
    )
    def test_missing_quantities_treated_as_zero(self, da, total_id, expected):
        parameters = _parameters()
        equipment = self._equipment(da=da, total_id=total_id)

        assert PortfolioPO._get_upstream_energy(equipment, START.add(hours=5), parameters) == expected

    def test_day_ahead_ignores_cumulated_intraday(self):
        parameters = _parameters(market=MarketType.dayahead, use_forecast=False)
        equipment = self._equipment(da=10.0, total_id=2.5)

        assert PortfolioPO._get_upstream_energy(equipment, START.add(hours=5), parameters) == 10.0


# ── Imbalance prices ──────────────────────────────────────────────────────────


class TestImbalancePriceIntraday:
    """The imbalance settlement price is anchored on the intraday price."""

    def test_forecast_price_uses_id_price_forecast(self):
        market_area = _market_area(id_price_forecast=_fm(35.0))
        parameters = _parameters(use_forecast=True)

        assert _get_forecast_price(START.add(hours=2), market_area, parameters) == 35.0

    def test_actual_price_uses_id_price(self):
        market_area = _market_area(id_price=_fm(60.0))
        parameters = _parameters(use_forecast=False)

        assert _get_actual_price(START.add(hours=2), market_area, parameters) == 60.0

    def test_penalties_applied_around_intraday_price(self):
        market_area = _market_area(id_price_forecast=_fm(100.0))
        parameters = _parameters(
            use_forecast=True,
            small_imbalance_penalty=0.1,
            large_imbalance_penalty=0.2,
            isp_forecast_lower_bound=10,
        )

        down, up, large_down, large_up = estimate_imbalance_prices(
            START.add(hours=2), market_area, ControlBlock(name="test_control_block"), parameters
        )

        assert up == pytest.approx(110.0)
        assert large_up == pytest.approx(120.0)
        assert down == pytest.approx(90.0)
        assert large_down == pytest.approx(80.0)

    def test_lower_bound_applied_to_small_intraday_price(self):
        """A near-zero intraday price is floored at ``isp_forecast_lower_bound``."""
        market_area = _market_area(id_price_forecast=_fm(2.0))
        parameters = _parameters(
            use_forecast=True,
            small_imbalance_penalty=0.1,
            large_imbalance_penalty=0.2,
            isp_forecast_lower_bound=10,
        )

        down, up, large_down, large_up = estimate_imbalance_prices(
            START.add(hours=2), market_area, ControlBlock(name="test_control_block"), parameters
        )

        assert up == pytest.approx(11.0)
        assert large_up == pytest.approx(12.0)
        assert down == pytest.approx(9.0)
        assert large_down == pytest.approx(8.0)

    def test_negative_intraday_price_reverses_penalty_direction(self):
        market_area = _market_area(id_price_forecast=_fm(-50.0))
        parameters = _parameters(
            use_forecast=True,
            small_imbalance_penalty=0.1,
            large_imbalance_penalty=0.2,
            isp_forecast_lower_bound=10,
        )

        down, up, large_down, large_up = estimate_imbalance_prices(
            START.add(hours=2), market_area, ControlBlock(name="test_control_block"), parameters
        )

        assert up == pytest.approx(-45.0)
        assert large_up == pytest.approx(-40.0)
        assert down == pytest.approx(-55.0)
        assert large_down == pytest.approx(-60.0)

    def test_control_block_prices_take_precedence_over_intraday_price(self):
        market_area = _market_area(id_price_forecast=_fm(100.0))
        control_block = ControlBlock(
            name="test_control_block",
            negative_imbalance_price=_ts(200.0),
            positive_imbalance_price=_ts(20.0),
        )
        parameters = _parameters(use_forecast=True, small_imbalance_penalty=0.1, large_imbalance_penalty=0.2)

        down, up, large_down, large_up = estimate_imbalance_prices(
            START.add(hours=2), market_area, control_block, parameters
        )

        assert up == pytest.approx(220.0)
        assert large_up == pytest.approx(240.0)
        assert down == pytest.approx(18.0)
        assert large_down == pytest.approx(16.0)


# ── Manual activation ─────────────────────────────────────────────────────────


class TestManualActivationPowerIntraday:
    """Manual activation in intraday works on day-ahead plus cumulated intraday power."""

    @staticmethod
    def _equipment(da: float | None = None, total_id: float | None = None, id_cleared: float | None = None) -> Mock:
        equipment = Mock()
        equipment.da_cleared_quantity = _ts(da) if da is not None else None
        equipment.total_id_cleared_quantity = _ts(total_id) if total_id is not None else None
        equipment.id_cleared_quantity = _fm(id_cleared) if id_cleared is not None else None
        return equipment

    def test_new_power_sums_day_ahead_and_cumulated_intraday(self):
        parameters = _parameters()
        new_power = _calculate_new_power(self._equipment(da=10.0, total_id=2.0), parameters)

        assert len(new_power) == NB_STEPS
        assert new_power.values == [12.0] * NB_STEPS

    def test_new_power_defaults_missing_intraday_to_zero(self):
        parameters = _parameters()
        new_power = _calculate_new_power(self._equipment(da=10.0), parameters)

        assert new_power.values == [10.0] * NB_STEPS

    def test_new_power_defaults_missing_day_ahead_to_zero(self):
        parameters = _parameters()
        new_power = _calculate_new_power(self._equipment(total_id=2.0), parameters)

        assert new_power.values == [2.0] * NB_STEPS

    def test_day_ahead_new_power_ignores_cumulated_intraday(self):
        parameters = _parameters(market=MarketType.dayahead, use_forecast=False)
        new_power = _calculate_new_power(self._equipment(da=10.0, total_id=2.0), parameters)

        assert new_power.values == [10.0] * NB_STEPS

    def test_activated_power_reads_id_cleared_quantity(self):
        parameters = _parameters()
        activated = _calculate_activated_power(self._equipment(da=10.0, id_cleared=3.0), parameters)

        assert activated.values == [3.0] * NB_STEPS

    def test_activated_power_is_zero_without_id_cleared_quantity(self):
        parameters = _parameters()
        activated = _calculate_activated_power(self._equipment(da=10.0), parameters)

        assert set(activated.values) == {0.0}


# ── Output routing ────────────────────────────────────────────────────────────


class TestOutputRoutingIntraday:
    """In intraday (``use_forecast=True``) results land in ``id_po_for_orders``."""

    @staticmethod
    def _result(power_value: float) -> Mock:
        result = Mock(spec=PortfolioOptimisationResult)
        result.get_variable_value.return_value = power_value
        return result

    @staticmethod
    def _wind() -> Mock:
        equipment = Mock(spec=WindPO)
        equipment.name = "wind_1"
        equipment.power = None
        equipment.id_po_for_orders = None
        return equipment

    def test_intraday_writes_id_po_for_orders_and_leaves_power_untouched(self):
        parameters = _parameters(use_forecast=True)
        equipment = self._wind()

        PortfolioOptimisationOutputDataset(parameters=parameters, optimisation_results=[]).update_equipment(
            self._result(7.0), "wind", [equipment]
        )

        assert equipment.power is None
        assert equipment.id_po_for_orders is not None
        forecast = equipment.id_po_for_orders.get_forecast(EXECUTION, START, END - TIMESTEP)
        assert forecast.values == [7.0] * NB_STEPS

    def test_day_ahead_writes_power_and_leaves_id_po_for_orders_untouched(self):
        parameters = _parameters(market=MarketType.dayahead, use_forecast=False)
        equipment = self._wind()

        PortfolioOptimisationOutputDataset(parameters=parameters, optimisation_results=[]).update_equipment(
            self._result(7.0), "wind", [equipment]
        )

        assert equipment.id_po_for_orders is None
        assert equipment.power is not None
        forecast = equipment.power.get_forecast(EXECUTION, START, END - TIMESTEP)
        assert forecast.values == [7.0] * NB_STEPS

    def test_thermal_state_sequence_still_written_in_intraday(self):
        parameters = _parameters(use_forecast=True)
        equipment = Mock(spec=ThermalPO)
        equipment.name = "thermal_1"
        equipment.power = None
        equipment.id_po_for_orders = None
        equipment.state_sequence = None

        PortfolioOptimisationOutputDataset(parameters=parameters, optimisation_results=[]).update_equipment(
            self._result(1.0), "thermal", [equipment]
        )

        assert equipment.power is None
        assert equipment.id_po_for_orders is not None
        assert equipment.state_sequence is not None
