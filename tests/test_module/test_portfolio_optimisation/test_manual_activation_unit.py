"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Unit tests for the public functions in manual_activation.py:
  - is_excluded_technology
  - is_excluded_thermal_strategy
  - is_excluded_market_area
  - should_manually_activate
  - _should_skip_equipment
"""

from unittest.mock import Mock

import pendulum
import pytest

from atlas.enums import ThermalStrategy
from atlas.math.timeseries import Timeseries
from atlas.modules.portfolio_optimisation.input_objects.hydro import HydroPO
from atlas.modules.portfolio_optimisation.input_objects.load import LoadPO
from atlas.modules.portfolio_optimisation.input_objects.other_non_dispatchable import OtherNonDispatchablePO
from atlas.modules.portfolio_optimisation.input_objects.solar import SolarPO
from atlas.modules.portfolio_optimisation.input_objects.storage import StoragePO
from atlas.modules.portfolio_optimisation.input_objects.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.input_objects.wind import WindPO
from atlas.modules.portfolio_optimisation.utils.manual_activation import (
    _should_skip_equipment,
    is_excluded_market_area,
    is_excluded_technology,
    is_excluded_thermal_strategy,
    should_manually_activate,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _mock(cls) -> Mock:
    """Return a Mock that passes isinstance checks for cls."""
    return Mock(spec=cls)


def _ts(values: list[float]) -> Timeseries:
    return Timeseries.from_values(
        start_date=pendulum.datetime(2024, 1, 1),
        frequency=pendulum.duration(hours=1),
        values=values,
    )


def _mock_params(*, use_forecast: bool = False, allowed_round_off_error: float = 0.01) -> Mock:
    params = Mock()
    params.use_forecast = use_forecast
    params.allowed_round_off_error = allowed_round_off_error
    return params


class TestIsExcludedTechnology:
    @pytest.mark.parametrize(
        "cls, key",
        [
            (ThermalPO, "thermal"),
            (WindPO, "wind"),
            (SolarPO, "solar"),
            (StoragePO, "storage"),
            (HydroPO, "hydro"),
            (LoadPO, "load"),
            (OtherNonDispatchablePO, "other_non_dispatchable"),
        ],
    )
    def test_excluded_when_matching_technology(self, cls, key):
        assert is_excluded_technology([key], _mock(cls)) is True

    @pytest.mark.parametrize(
        "cls, key",
        [
            (ThermalPO, "thermal"),
            (WindPO, "wind"),
            (SolarPO, "solar"),
            (StoragePO, "storage"),
            (HydroPO, "hydro"),
            (LoadPO, "load"),
            (OtherNonDispatchablePO, "other_non_dispatchable"),
        ],
    )
    def test_not_excluded_when_different_technology(self, cls, key):
        other_keys = ["thermal", "wind", "solar", "storage", "hydro", "load", "other_non_dispatchable"]
        for other in other_keys:
            if other != key:
                assert is_excluded_technology([other], _mock(cls)) is False

    def test_all_excludes_every_type(self):
        for cls in (ThermalPO, WindPO, SolarPO, StoragePO, HydroPO, LoadPO, OtherNonDispatchablePO):
            assert is_excluded_technology(["all"], _mock(cls)) is True

    def test_empty_list_excludes_nothing(self):
        for cls in (ThermalPO, WindPO, SolarPO):
            assert is_excluded_technology([], _mock(cls)) is False

    def test_unknown_key_is_ignored(self):
        assert is_excluded_technology(["unknown_tech"], _mock(ThermalPO)) is False

    def test_case_insensitive_matching(self):
        assert is_excluded_technology(["Thermal"], _mock(ThermalPO)) is True
        assert is_excluded_technology(["WIND"], _mock(WindPO)) is True
        assert is_excluded_technology(["Solar"], _mock(SolarPO)) is True

    def test_multiple_exclusions_match_first_found(self):
        assert is_excluded_technology(["wind", "solar"], _mock(WindPO)) is True
        assert is_excluded_technology(["wind", "solar"], _mock(SolarPO)) is True
        assert is_excluded_technology(["wind", "solar"], _mock(ThermalPO)) is False


class TestIsExcludedThermalStrategy:
    def _thermal(self, strategy: ThermalStrategy | None) -> Mock:
        t = _mock(ThermalPO)
        t.strategy = strategy
        return t

    @pytest.mark.parametrize("strategy", list(ThermalStrategy))
    def test_excluded_when_strategy_matches(self, strategy):
        assert is_excluded_thermal_strategy([strategy], self._thermal(strategy)) is True

    @pytest.mark.parametrize("strategy", list(ThermalStrategy))
    def test_not_excluded_when_strategy_differs(self, strategy):
        other_strategies = [s for s in ThermalStrategy if s != strategy]
        assert is_excluded_thermal_strategy(other_strategies, self._thermal(strategy)) is False

    def test_all_strategies_excluded_together(self):
        for strategy in ThermalStrategy:
            assert is_excluded_thermal_strategy(list(ThermalStrategy), self._thermal(strategy)) is True

    def test_empty_list_excludes_nothing(self):
        assert is_excluded_thermal_strategy([], self._thermal(ThermalStrategy.BASE)) is False

    def test_none_strategy_never_excluded(self):
        assert is_excluded_thermal_strategy(list(ThermalStrategy), self._thermal(None)) is False

    def test_non_thermal_equipment_never_excluded(self):
        assert is_excluded_thermal_strategy(list(ThermalStrategy), _mock(WindPO)) is False


class TestIsExcludedMarketArea:
    def test_excluded_when_market_area_in_list_and_no_forecast(self):
        assert is_excluded_market_area(False, ["ma_a", "ma_b"], "ma_a") is True

    def test_not_excluded_when_use_forecast_true(self):
        assert is_excluded_market_area(True, ["ma_a"], "ma_a") is False

    def test_not_excluded_when_market_area_not_in_list(self):
        assert is_excluded_market_area(False, ["ma_b"], "ma_a") is False

    def test_all_excludes_regardless_of_use_forecast(self):
        assert is_excluded_market_area(False, ["all"], "ma_a") is True
        assert is_excluded_market_area(True, ["all"], "ma_a") is True

    def test_empty_list_excludes_nothing(self):
        assert is_excluded_market_area(False, [], "ma_a") is False

    def test_unknown_market_area_not_excluded(self):
        assert is_excluded_market_area(False, ["ma_a"], "ma_unknown") is False


class TestShouldManuallyActivate:
    def _thermal(self, strategy: ThermalStrategy) -> Mock:
        t = _mock(ThermalPO)
        t.strategy = strategy
        return t

    # Non-thermal: routing purely through is_excluded_technology
    def test_non_thermal_excluded_via_technology_list(self):
        assert should_manually_activate(_mock(WindPO), ["wind"], []) is True

    def test_non_thermal_not_excluded_when_not_in_list(self):
        assert should_manually_activate(_mock(WindPO), ["solar"], []) is False

    def test_non_thermal_excluded_via_all(self):
        assert should_manually_activate(_mock(SolarPO), ["all"], []) is True

    # Thermal: excluded by technology OR by strategy
    def test_thermal_excluded_via_technology(self):
        t = self._thermal(ThermalStrategy.PEAK)
        assert should_manually_activate(t, ["thermal"], []) is True

    def test_thermal_excluded_via_strategy(self):
        t = self._thermal(ThermalStrategy.BASE)
        assert should_manually_activate(t, [], [ThermalStrategy.BASE]) is True

    def test_thermal_excluded_via_both(self):
        t = self._thermal(ThermalStrategy.BASE)
        assert should_manually_activate(t, ["thermal"], [ThermalStrategy.BASE]) is True

    def test_thermal_not_excluded_when_neither_matches(self):
        t = self._thermal(ThermalStrategy.PEAK)
        assert should_manually_activate(t, [], [ThermalStrategy.BASE]) is False

    def test_thermal_not_excluded_with_empty_lists(self):
        t = self._thermal(ThermalStrategy.BASE)
        assert should_manually_activate(t, [], []) is False

    @pytest.mark.parametrize("strategy", list(ThermalStrategy))
    def test_all_thermal_strategies_excluded_via_technology_all(self, strategy):
        t = self._thermal(strategy)
        assert should_manually_activate(t, ["all"], []) is True


class TestShouldSkipEquipment:
    def test_never_skips_when_use_forecast_true(self):
        params = _mock_params(use_forecast=True)
        # Even if power is zero, should not skip in forecast mode
        zero_power = _ts([0.0, 0.0, 0.0])
        for cls in (HydroPO, StoragePO, LoadPO):
            assert _should_skip_equipment(_mock(cls), zero_power, params) is False

    def test_thermal_never_skipped_even_with_zero_power(self):
        params = _mock_params(use_forecast=False)
        zero_power = _ts([0.0, 0.0, 0.0])
        assert _should_skip_equipment(_mock(ThermalPO), zero_power, params) is False

    def test_wind_never_skipped_even_with_zero_power(self):
        params = _mock_params(use_forecast=False)
        zero_power = _ts([0.0, 0.0, 0.0])
        assert _should_skip_equipment(_mock(WindPO), zero_power, params) is False

    def test_solar_never_skipped_even_with_zero_power(self):
        params = _mock_params(use_forecast=False)
        zero_power = _ts([0.0, 0.0, 0.0])
        assert _should_skip_equipment(_mock(SolarPO), zero_power, params) is False

    def test_other_equipment_skipped_when_power_is_zero(self):
        params = _mock_params(use_forecast=False, allowed_round_off_error=0.01)
        zero_power = _ts([0.0, 0.0, 0.0])
        for cls in (StoragePO, HydroPO, LoadPO, OtherNonDispatchablePO):
            assert _should_skip_equipment(_mock(cls), zero_power, params) is True

    def test_other_equipment_not_skipped_when_power_is_nonzero(self):
        params = _mock_params(use_forecast=False, allowed_round_off_error=0.01)
        nonzero_power = _ts([0.0, 5.0, 0.0])
        for cls in (StoragePO, HydroPO, LoadPO):
            assert _should_skip_equipment(_mock(cls), nonzero_power, params) is False

    def test_skip_threshold_respected(self):
        params = _mock_params(use_forecast=False, allowed_round_off_error=1.0)
        # power within threshold → skip
        within = _ts([0.5, 0.5, 0.5])
        assert _should_skip_equipment(_mock(StoragePO), within, params) is True
        # power above threshold → don't skip
        above = _ts([0.0, 2.0, 0.0])
        assert _should_skip_equipment(_mock(StoragePO), above, params) is False

    def test_negative_power_treated_as_nonzero_for_skip(self):
        params = _mock_params(use_forecast=False, allowed_round_off_error=0.01)
        # abs().min() > threshold → non-zero → don't skip
        negative_power = _ts([-5.0, -5.0, -5.0])
        assert _should_skip_equipment(_mock(StoragePO), negative_power, params) is False
