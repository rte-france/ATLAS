"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Unit tests for the reading of solved optimisation variables in result_extraction.py:
  - extract_equipment_schedule dispatch per equipment type
  - thermal state sequence decoding
  - hydro fragment summing and storage sell/buy netting
  - round-off snapping
"""

from unittest.mock import Mock

import pendulum
import pytest

from atlas.enums import ThermalDispatchState
from atlas.modules.portfolio_optimisation.input_objects.hydro import HydroPO
from atlas.modules.portfolio_optimisation.input_objects.solar import SolarPO
from atlas.modules.portfolio_optimisation.input_objects.storage import StoragePO
from atlas.modules.portfolio_optimisation.input_objects.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.utils.result_extraction import extract_equipment_schedule

TARGET_TIMES = [pendulum.datetime(2024, 1, 1).add(hours=h) for h in range(3)]
ROUND_OFF = 0.01

# ── Helpers ───────────────────────────────────────────────────────────────────


def _equipment(cls, name: str = "eq", **attributes) -> Mock:
    """Return a Mock that passes isinstance checks for cls."""
    equipment = Mock(spec=cls)
    equipment.name = name
    for attribute, value in attributes.items():
        setattr(equipment, attribute, value)
    return equipment


def _result(variable_values: dict[str, float]) -> Mock:
    """Return a stand-in optimisation result serving the given variable values, 0.0 elsewhere."""
    result = Mock()
    result.get_variable_value.side_effect = lambda name: variable_values.get(name, 0.0)
    return result


def _extract(equipment, variable_values: dict[str, float]):
    return extract_equipment_schedule(equipment, _result(variable_values), TARGET_TIMES, ROUND_OFF)


# ── Power-only equipments ─────────────────────────────────────────────────────


class TestPowerOnlyExtraction:
    def test_reads_power_level_per_target_time(self):
        solar = _equipment(SolarPO, "solar_a")
        values = {f"solar_a_power_level_{time}": 10.0 + index for index, time in enumerate(TARGET_TIMES)}

        schedule = _extract(solar, values)

        assert schedule.power == [10.0, 11.0, 12.0]

    def test_carries_no_stock_nor_state(self):
        schedule = _extract(_equipment(SolarPO, "solar_a"), {})

        assert schedule.stored_energy == []
        assert schedule.state_sequence == []

    def test_missing_variables_default_to_zero(self):
        schedule = _extract(_equipment(SolarPO, "solar_a"), {})

        assert schedule.power == [0.0, 0.0, 0.0]

    @pytest.mark.parametrize(
        ("raw_power", "expected"),
        [
            (0.005, 0.0),
            (-0.005, 0.0),
            (ROUND_OFF, 0.0),
            (-ROUND_OFF, 0.0),
            (0.02, 0.02),
            (-0.02, -0.02),
        ],
    )
    def test_snaps_round_off_errors_to_zero(self, raw_power, expected):
        solar = _equipment(SolarPO, "solar_a")
        values = {f"solar_a_power_level_{TARGET_TIMES[0]}": raw_power}

        schedule = _extract(solar, values)

        assert schedule.power[0] == expected


# ── Thermal ───────────────────────────────────────────────────────────────────


class TestThermalExtraction:
    @pytest.mark.parametrize(
        ("variable_prefix", "expected_state"),
        [
            ("on_up", ThermalDispatchState.ON_UP),
            ("on_down", ThermalDispatchState.ON_DOWN),
            ("off", ThermalDispatchState.OFF),
            ("on_start", ThermalDispatchState.START),
            ("stop", ThermalDispatchState.STOP),
            ("on_flat", ThermalDispatchState.ON_FLAT),
        ],
    )
    def test_decodes_each_state_indicator(self, variable_prefix, expected_state):
        thermal = _equipment(ThermalPO, "th_a")
        values = {f"{variable_prefix}_th_a_{time}": 1 for time in TARGET_TIMES}

        schedule = _extract(thermal, values)

        assert schedule.state_sequence == [expected_state] * len(TARGET_TIMES)

    def test_reports_undefined_when_no_indicator_is_set(self):
        schedule = _extract(_equipment(ThermalPO, "th_a"), {})

        assert schedule.state_sequence == [ThermalDispatchState.UNKNOWN] * len(TARGET_TIMES)

    def test_state_sequence_always_aligns_with_power(self):
        """A timestep with no indicator must still produce an entry, keeping both lists aligned."""
        thermal = _equipment(ThermalPO, "th_a")
        values = {f"on_flat_th_a_{TARGET_TIMES[1]}": 1}

        schedule = _extract(thermal, values)

        assert len(schedule.state_sequence) == len(schedule.power) == len(TARGET_TIMES)
        assert schedule.state_sequence == [
            ThermalDispatchState.UNKNOWN,
            ThermalDispatchState.ON_FLAT,
            ThermalDispatchState.UNKNOWN,
        ]

    def test_resolution_order_prefers_the_first_matching_indicator(self):
        thermal = _equipment(ThermalPO, "th_a")
        values = {f"on_up_th_a_{TARGET_TIMES[0]}": 1, f"off_th_a_{TARGET_TIMES[0]}": 1}

        schedule = _extract(thermal, values)

        assert schedule.state_sequence[0] == ThermalDispatchState.ON_UP

    def test_reads_power_and_carries_no_stock(self):
        thermal = _equipment(ThermalPO, "th_a")
        values = {f"th_a_power_level_{TARGET_TIMES[0]}": 42.0}

        schedule = _extract(thermal, values)

        assert schedule.power == [42.0, 0.0, 0.0]
        assert schedule.stored_energy == []


# ── Hydro ─────────────────────────────────────────────────────────────────────


class TestHydroExtraction:
    def test_sums_power_over_fragments(self):
        hydro = _equipment(HydroPO, "hy_a", fragment_data={0: Mock(), 1: Mock()})
        time = TARGET_TIMES[0]
        values = {f"hy_a_power_level_frag_0_{time}": 5.0, f"hy_a_power_level_frag_1_{time}": 7.0}

        schedule = _extract(hydro, values)

        assert schedule.power[0] == 12.0

    def test_reads_stored_energy(self):
        hydro = _equipment(HydroPO, "hy_a", fragment_data={0: Mock()})
        values = {f"hy_a_stored_energy_{time}": 100.0 + index for index, time in enumerate(TARGET_TIMES)}

        schedule = _extract(hydro, values)

        assert schedule.stored_energy == [100.0, 101.0, 102.0]

    def test_negative_sum_is_treated_as_round_off_noise(self):
        """Hydro fragments are generation-only, so a negative total is snapped to zero."""
        hydro = _equipment(HydroPO, "hy_a", fragment_data={0: Mock()})
        values = {f"hy_a_power_level_frag_0_{TARGET_TIMES[0]}": -50.0}

        schedule = _extract(hydro, values)

        assert schedule.power[0] == 0.0

    def test_carries_no_state_sequence(self):
        hydro = _equipment(HydroPO, "hy_a", fragment_data={0: Mock()})

        assert _extract(hydro, {}).state_sequence == []


# ── Storage ───────────────────────────────────────────────────────────────────


class TestStorageExtraction:
    def test_nets_sell_and_buy_power(self):
        storage = _equipment(StoragePO, "st_a")
        time = TARGET_TIMES[0]
        values = {f"st_a_power_level_sell_{time}": 20.0, f"st_a_power_level_buy_{time}": -8.0}

        schedule = _extract(storage, values)

        assert schedule.power[0] == 12.0

    def test_keeps_negative_net_power_when_charging(self):
        storage = _equipment(StoragePO, "st_a")
        values = {f"st_a_power_level_buy_{TARGET_TIMES[0]}": -30.0}

        schedule = _extract(storage, values)

        assert schedule.power[0] == -30.0

    def test_reads_stored_energy(self):
        storage = _equipment(StoragePO, "st_a")
        values = {f"st_a_stored_energy_{time}": 5.0 for time in TARGET_TIMES}

        schedule = _extract(storage, values)

        assert schedule.stored_energy == [5.0, 5.0, 5.0]
