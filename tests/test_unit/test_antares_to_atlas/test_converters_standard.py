"""
Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Unit tests for standard converters: thermal, solar, wind, load, links.
Each test exercises the model conversion function directly with a mocked Study.
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from antares.craft.model.st_storage import STStorageGroup

from atlas.math.timeseries import Timeseries
from atlas.modules.antares_to_atlas.models.load.load import convert_load_units
from atlas.modules.antares_to_atlas.models.res.solar import convert_solar_units
from atlas.modules.antares_to_atlas.models.res.wind import convert_wind_units
from atlas.modules.antares_to_atlas.models.storage.battery import convert_battery_units
from atlas.modules.antares_to_atlas.models.storage.phs_closed import convert_phs_closed_units
from atlas.modules.antares_to_atlas.models.system_structure.link import convert_links
from atlas.modules.antares_to_atlas.models.thermal.thermal import convert_thermal_units

from tests.test_unit.test_antares_to_atlas.conftest import make_area_dataset, make_params

_THERMAL_MODULE = "atlas.modules.antares_to_atlas.models.thermal.thermal"
_STORAGE_HELPERS = "atlas.modules.antares_to_atlas.models.storage._helpers"
_START = "2025-01-01T00:00:00"

# ── Helpers ───────────────────────────────────────────────────────────────────


def _ts(params, value: float = 100.0) -> Timeseries:
    """Create a minimal one-year daily timeseries for use as a mock return value."""
    end = params.start_date.add(years=1)
    return Timeseries.from_index(params.start_date, "365d", end, value)


def _make_prepro_df() -> pd.DataFrame:
    """Return a 365-row DataFrame mimicking Antares prepro data columns."""
    return pd.DataFrame(
        {
            0: [1.0] * 365,   # FODuration
            1: [1.0] * 365,   # PODuration
            2: [0.05] * 365,  # FORate
            3: [0.03] * 365,  # PORate
        }
    )


def _make_thermal_mock(
    thermal_id: str = "gas_ccgt_1",
    group: str = "gas",
    nominal_capacity: float = 500.0,
    unit_count: int = 1,
    min_stable_power: float = 100.0,
    startup_cost: float = 5000.0,
    co2: float = 0.5,
    market_bid_cost: float = 0.0,
    marginal_cost: float = 50.0,
    min_down_time: int = 4,
    min_up_time: int = 2,
) -> MagicMock:
    thermal = MagicMock()
    thermal.id = thermal_id
    thermal.properties.group = group
    thermal.properties.nominal_capacity = nominal_capacity
    thermal.properties.unit_count = unit_count
    thermal.properties.min_stable_power = min_stable_power
    thermal.properties.startup_cost = startup_cost
    thermal.properties.co2 = co2
    thermal.properties.market_bid_cost = market_bid_cost
    thermal.properties.marginal_cost = marginal_cost
    thermal.properties.min_down_time = min_down_time
    thermal.properties.min_up_time = min_up_time
    thermal.get_prepro_data_matrix.return_value = _make_prepro_df()
    return thermal


def _make_study_for_thermal(areas: dict) -> MagicMock:
    study = MagicMock()
    study.get_areas.return_value = areas
    # Force fallback path: scenario not found in output
    study.get_output.return_value.get_thermal_ts_numbers.return_value.get.return_value = None
    return study


def _make_cluster_mock(
    group: str = "solar pv",
    enabled: bool = True,
    max_value: float = 100.0,
    nominal_capacity: float = 1000.0,
) -> MagicMock:
    cluster = MagicMock()
    cluster.properties.group = group
    cluster.properties.enabled = enabled
    cluster.properties.nominal_capacity = nominal_capacity
    cluster.get_timeseries.return_value.abs.return_value.max.return_value.max.return_value = max_value
    return cluster


def _make_study_cluster_mode(area_id: str, renewables: dict, ts_scenario: int | None = 1) -> MagicMock:
    area = MagicMock()
    area.id = area_id
    area.get_renewables.return_value = renewables

    study = MagicMock()
    study.get_areas.return_value = {area_id: area}
    study.get_settings.return_value.advanced_parameters.renewable_generation_modelling.value = "clusters"
    study.get_output.return_value.get_solar_ts_numbers.return_value.get.return_value = ts_scenario
    study.get_output.return_value.get_wind_ts_numbers.return_value.get.return_value = ts_scenario
    return study


# ── TestConvertThermalUnits ────────────────────────────────────────────────────


class TestConvertThermalUnits:
    def test_converts_thermal_unit_and_adds_to_dataset(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        thermal = _make_thermal_mock()
        area = MagicMock()
        area.id = "fr"
        area.get_thermals.return_value = {"gas_ccgt_1": thermal}
        study = _make_study_for_thermal({"fr": area})

        with (
            patch(f"{_THERMAL_MODULE}.get_maximum_power", return_value=_ts(params)),
            patch(f"{_THERMAL_MODULE}.get_variable_cost", return_value=_ts(params)),
        ):
            result = convert_thermal_units(study, params, fr_dataset)

        assert len(result.thermal) == 1
        assert result.thermal.get("fr_gas_ccgt_1") is not None

    def test_thermal_unit_name_follows_area_cluster_pattern(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        thermal = _make_thermal_mock(thermal_id="nuclear_unit")
        area = MagicMock()
        area.id = "fr"
        area.get_thermals.return_value = {"nuclear_unit": thermal}
        study = _make_study_for_thermal({"fr": area})

        with (
            patch(f"{_THERMAL_MODULE}.get_maximum_power", return_value=_ts(params)),
            patch(f"{_THERMAL_MODULE}.get_variable_cost", return_value=_ts(params, 30.0)),
        ):
            result = convert_thermal_units(study, params, fr_dataset)

        assert result.thermal.get("fr_nuclear_unit").name == "fr_nuclear_unit"

    def test_skips_area_absent_from_study(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        # Study only has "de", not "fr"
        study = _make_study_for_thermal({"de": MagicMock()})

        result = convert_thermal_units(study, params, fr_dataset)

        assert len(result.thermal) == 0

    def test_skips_cluster_in_excluded_thermic_group(self, fr_dataset):
        params = make_params(market_areas=["fr"], excluded_thermic_groups=["nuclear"])
        thermal = _make_thermal_mock(group="nuclear")
        area = MagicMock()
        area.id = "fr"
        area.get_thermals.return_value = {"nuclear_1": thermal}
        study = _make_study_for_thermal({"fr": area})

        # get_maximum_power is never reached when the group is excluded
        result = convert_thermal_units(study, params, fr_dataset)

        assert len(result.thermal) == 0

    def test_skips_cluster_when_maximum_power_is_none(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        thermal = _make_thermal_mock()
        area = MagicMock()
        area.id = "fr"
        area.get_thermals.return_value = {"gas_1": thermal}
        study = _make_study_for_thermal({"fr": area})

        with patch(f"{_THERMAL_MODULE}.get_maximum_power", return_value=None):
            result = convert_thermal_units(study, params, fr_dataset)

        assert len(result.thermal) == 0

    def test_skips_cluster_with_zero_installed_capacity(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        # nominal_capacity * unit_count = 500 * 0 = 0
        thermal = _make_thermal_mock(nominal_capacity=500.0, unit_count=0)
        area = MagicMock()
        area.id = "fr"
        area.get_thermals.return_value = {"gas_1": thermal}
        study = _make_study_for_thermal({"fr": area})

        with (
            patch(f"{_THERMAL_MODULE}.get_maximum_power", return_value=_ts(params)),
            patch(f"{_THERMAL_MODULE}.get_variable_cost", return_value=_ts(params)),
        ):
            result = convert_thermal_units(study, params, fr_dataset)

        assert len(result.thermal) == 0

    def test_skips_cluster_with_unknown_thermal_group(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        thermal = _make_thermal_mock(group="mystery_fuel")
        area = MagicMock()
        area.id = "fr"
        area.get_thermals.return_value = {"mystery_1": thermal}
        study = _make_study_for_thermal({"fr": area})

        with (
            patch(f"{_THERMAL_MODULE}.get_maximum_power", return_value=_ts(params)),
            patch(f"{_THERMAL_MODULE}.get_variable_cost", return_value=_ts(params)),
        ):
            result = convert_thermal_units(study, params, fr_dataset)

        assert len(result.thermal) == 0

    def test_refines_gas_cluster_to_ccgt_when_id_contains_ccgt(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        # "gas" group with "ccgt" in the cluster ID → refined to "ccgt" config
        thermal = _make_thermal_mock(thermal_id="fr_ccgt_unit", group="gas")
        area = MagicMock()
        area.id = "fr"
        area.get_thermals.return_value = {"fr_ccgt_unit": thermal}
        study = _make_study_for_thermal({"fr": area})

        with (
            patch(f"{_THERMAL_MODULE}.get_maximum_power", return_value=_ts(params)),
            patch(f"{_THERMAL_MODULE}.get_variable_cost", return_value=_ts(params)),
        ):
            result = convert_thermal_units(study, params, fr_dataset)

        # ccgt is a known thermal group, so the unit should be created
        assert len(result.thermal) == 1

    def test_refines_gas_cluster_to_ocgt_when_id_contains_ocgt(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        thermal = _make_thermal_mock(thermal_id="fr_ocgt_peak", group="gas")
        area = MagicMock()
        area.id = "fr"
        area.get_thermals.return_value = {"fr_ocgt_peak": thermal}
        study = _make_study_for_thermal({"fr": area})

        with (
            patch(f"{_THERMAL_MODULE}.get_maximum_power", return_value=_ts(params)),
            patch(f"{_THERMAL_MODULE}.get_variable_cost", return_value=_ts(params)),
        ):
            result = convert_thermal_units(study, params, fr_dataset)

        assert len(result.thermal) == 1

    def test_converts_multiple_clusters_in_same_area(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        thermal1 = _make_thermal_mock(thermal_id="gas_ccgt_1", group="gas")
        thermal2 = _make_thermal_mock(thermal_id="coal_1", group="hard_coal")
        area = MagicMock()
        area.id = "fr"
        area.get_thermals.return_value = {
            "gas_ccgt_1": thermal1,
            "coal_1": thermal2,
        }
        study = _make_study_for_thermal({"fr": area})

        with (
            patch(f"{_THERMAL_MODULE}.get_maximum_power", return_value=_ts(params)),
            patch(f"{_THERMAL_MODULE}.get_variable_cost", return_value=_ts(params)),
        ):
            result = convert_thermal_units(study, params, fr_dataset)

        assert len(result.thermal) == 2

    def test_only_converts_clusters_for_listed_market_areas(self):
        params = make_params(market_areas=["fr"])
        dataset = make_area_dataset("fr", "de")

        thermal_fr = _make_thermal_mock(thermal_id="gas_1", group="gas")
        thermal_de = _make_thermal_mock(thermal_id="coal_1", group="hard_coal")

        area_fr = MagicMock()
        area_fr.id = "fr"
        area_fr.get_thermals.return_value = {"gas_1": thermal_fr}

        area_de = MagicMock()
        area_de.id = "de"
        area_de.get_thermals.return_value = {"coal_1": thermal_de}

        study = _make_study_for_thermal({"fr": area_fr, "de": area_de})

        with (
            patch(f"{_THERMAL_MODULE}.get_maximum_power", return_value=_ts(params)),
            patch(f"{_THERMAL_MODULE}.get_variable_cost", return_value=_ts(params)),
        ):
            result = convert_thermal_units(study, params, dataset)

        assert len(result.thermal) == 1
        assert result.thermal.get("fr_gas_1") is not None


# ── TestConvertSolarUnits ──────────────────────────────────────────────────────


class TestConvertSolarUnits:
    def test_converts_solar_pv_cluster(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        cluster = _make_cluster_mock(group="solar pv", enabled=True, max_value=100.0)
        study = _make_study_cluster_mode("fr", {"fr_solar_pv": cluster})

        result = convert_solar_units(study, params, fr_dataset)

        assert len(result.solar) == 1
        assert result.solar.get("fr_pv") is not None

    def test_solar_unit_name_follows_area_pv_pattern(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        cluster = _make_cluster_mock(group="solar pv")
        study = _make_study_cluster_mode("fr", {"fr_solar_pv": cluster})

        result = convert_solar_units(study, params, fr_dataset)

        assert result.solar.get("fr_pv").name == "fr_pv"

    def test_skips_disabled_solar_cluster(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        cluster = _make_cluster_mock(group="solar pv", enabled=False)
        study = _make_study_cluster_mode("fr", {"fr_solar_pv": cluster})

        result = convert_solar_units(study, params, fr_dataset)

        assert len(result.solar) == 0

    def test_skips_all_zero_solar_cluster(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        cluster = _make_cluster_mock(group="solar pv", enabled=True, max_value=0.0)
        study = _make_study_cluster_mode("fr", {"fr_solar_pv": cluster})

        result = convert_solar_units(study, params, fr_dataset)

        assert len(result.solar) == 0

    def test_skips_non_solar_pv_cluster_group(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        cluster = _make_cluster_mock(group="wind onshore", enabled=True)
        study = _make_study_cluster_mode("fr", {"fr_wind": cluster})

        result = convert_solar_units(study, params, fr_dataset)

        assert len(result.solar) == 0

    def test_skips_area_absent_from_study(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        study = MagicMock()
        study.get_areas.return_value = {}
        study.get_settings.return_value.advanced_parameters.renewable_generation_modelling.value = "clusters"

        result = convert_solar_units(study, params, fr_dataset)

        assert len(result.solar) == 0

    def test_converts_solar_in_aggregated_mode_when_scenario_found(self, fr_dataset):
        params = make_params(market_areas=["fr"])

        area = MagicMock()
        area.id = "fr"
        solar_matrix = MagicMock()
        solar_matrix.abs.return_value.max.return_value.item.return_value = 200.0
        area.get_solar_matrix.return_value = [solar_matrix]

        study = MagicMock()
        study.get_areas.return_value = {"fr": area}
        study.get_settings.return_value.advanced_parameters.renewable_generation_modelling.value = "aggregated"
        study.get_output.return_value.get_solar_ts_numbers.return_value.get.return_value = 1

        result = convert_solar_units(study, params, fr_dataset)

        assert len(result.solar) == 1

    def test_skips_solar_in_aggregated_mode_when_no_scenario(self, fr_dataset):
        params = make_params(market_areas=["fr"])

        area = MagicMock()
        area.id = "fr"

        study = MagicMock()
        study.get_areas.return_value = {"fr": area}
        study.get_settings.return_value.advanced_parameters.renewable_generation_modelling.value = "aggregated"
        # No scenario found for this area
        study.get_output.return_value.get_solar_ts_numbers.return_value.get.return_value = None

        result = convert_solar_units(study, params, fr_dataset)

        assert len(result.solar) == 0

    def test_solar_thermo_capacity_merged_into_pv(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        pv_cluster = _make_cluster_mock(group="solar pv", nominal_capacity=1000.0)
        thermo_cluster = MagicMock()
        thermo_cluster.properties.enabled = True
        thermo_cluster.properties.nominal_capacity = 200.0

        # solar thermo suffix is "_solar_thermo" → cluster key "fr_solar_thermo"
        renewables = {
            "fr_pv": pv_cluster,
            "fr_solar_thermo": thermo_cluster,
        }
        study = _make_study_cluster_mode("fr", renewables)

        result = convert_solar_units(study, params, fr_dataset)

        assert len(result.solar) == 1
        solar_unit = result.solar.get("fr_pv")
        assert solar_unit.installed_capacity == 1200.0


# ── TestConvertWindUnits ───────────────────────────────────────────────────────


class TestConvertWindUnits:
    def test_converts_wind_onshore_cluster(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        cluster = _make_cluster_mock(group="wind onshore", enabled=True, max_value=100.0)
        study = _make_study_cluster_mode("fr", {"fr_wind_onshore": cluster})

        result = convert_wind_units(study, params, fr_dataset)

        assert len(result.wind) == 1
        assert result.wind.get("fr_wind") is not None

    def test_wind_unit_name_follows_area_wind_pattern(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        cluster = _make_cluster_mock(group="wind onshore")
        study = _make_study_cluster_mode("fr", {"fr_wind_onshore": cluster})

        result = convert_wind_units(study, params, fr_dataset)

        assert result.wind.get("fr_wind").name == "fr_wind"

    def test_skips_disabled_wind_cluster(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        cluster = _make_cluster_mock(group="wind onshore", enabled=False)
        study = _make_study_cluster_mode("fr", {"fr_wind_onshore": cluster})

        result = convert_wind_units(study, params, fr_dataset)

        assert len(result.wind) == 0

    def test_skips_all_zero_wind_cluster(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        cluster = _make_cluster_mock(group="wind onshore", enabled=True, max_value=0.0)
        study = _make_study_cluster_mode("fr", {"fr_wind_onshore": cluster})

        result = convert_wind_units(study, params, fr_dataset)

        assert len(result.wind) == 0

    def test_skips_non_wind_onshore_cluster_group(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        cluster = _make_cluster_mock(group="solar pv", enabled=True)
        study = _make_study_cluster_mode("fr", {"fr_pv": cluster})

        result = convert_wind_units(study, params, fr_dataset)

        assert len(result.wind) == 0

    def test_offshore_capacity_merged_into_onshore_unit(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        onshore = _make_cluster_mock(group="wind onshore", nominal_capacity=3000.0)
        offshore = MagicMock()
        offshore.properties.enabled = True
        offshore.properties.nominal_capacity = 500.0

        # offshore suffix is "_wind_offshore" → "fr_wind_offshore"
        renewables = {
            "fr_wind_onshore": onshore,
            "fr_wind_offshore": offshore,
        }
        study = _make_study_cluster_mode("fr", renewables)

        result = convert_wind_units(study, params, fr_dataset)

        assert len(result.wind) == 1
        assert result.wind.get("fr_wind").installed_capacity == 3500.0

    def test_offshore_not_merged_for_excluded_area(self, fr_dataset):
        # "dekf" is in wind_offshore_excluded_areas by default
        params = make_params(market_areas=["dekf"])
        dataset = make_area_dataset("dekf")

        onshore = _make_cluster_mock(group="wind onshore", nominal_capacity=2000.0)
        offshore = MagicMock()
        offshore.properties.enabled = True
        offshore.properties.nominal_capacity = 400.0

        renewables = {
            "dekf_wind_onshore": onshore,
            "dekf_wind_offshore": offshore,
        }
        area = MagicMock()
        area.id = "dekf"
        area.get_renewables.return_value = renewables

        study = MagicMock()
        study.get_areas.return_value = {"dekf": area}
        study.get_settings.return_value.advanced_parameters.renewable_generation_modelling.value = "clusters"
        study.get_output.return_value.get_wind_ts_numbers.return_value.get.return_value = 1

        result = convert_wind_units(study, params, dataset)

        assert len(result.wind) == 1
        # offshore not merged because "dekf" is excluded
        assert result.wind.get("dekf_wind").installed_capacity == 2000.0

    def test_converts_wind_in_aggregated_mode_when_scenario_found(self, fr_dataset):
        params = make_params(market_areas=["fr"])

        area = MagicMock()
        area.id = "fr"
        wind_matrix = MagicMock()
        wind_matrix.abs.return_value.max.return_value.item.return_value = 500.0
        area.get_wind_matrix.return_value = [wind_matrix]

        study = MagicMock()
        study.get_areas.return_value = {"fr": area}
        study.get_settings.return_value.advanced_parameters.renewable_generation_modelling.value = "aggregated"
        study.get_output.return_value.get_wind_ts_numbers.return_value.get.return_value = 1

        result = convert_wind_units(study, params, fr_dataset)

        assert len(result.wind) == 1

    def test_skips_area_absent_from_study(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        study = MagicMock()
        study.get_areas.return_value = {}
        study.get_settings.return_value.advanced_parameters.renewable_generation_modelling.value = "clusters"

        result = convert_wind_units(study, params, fr_dataset)

        assert len(result.wind) == 0


# ── TestConvertLoadUnits ───────────────────────────────────────────────────────


class TestConvertLoadUnits:
    def test_converts_load_unit_when_scenario_found(self, fr_dataset):
        params = make_params(market_areas=["fr"])

        area = MagicMock()
        study = MagicMock()
        study.get_areas.return_value = {"fr": area}
        study.get_output.return_value.get_load_ts_numbers.return_value.get.return_value = 1

        result = convert_load_units(study, params, fr_dataset)

        assert len(result.load) == 1
        assert result.load.get("fr_l") is not None

    def test_load_unit_name_follows_area_l_pattern(self, fr_dataset):
        params = make_params(market_areas=["fr"])

        study = MagicMock()
        study.get_areas.return_value = {"fr": MagicMock()}
        study.get_output.return_value.get_load_ts_numbers.return_value.get.return_value = 1

        result = convert_load_units(study, params, fr_dataset)

        assert result.load.get("fr_l").name == "fr_l"

    def test_skips_load_when_no_scenario(self, fr_dataset):
        params = make_params(market_areas=["fr"])

        study = MagicMock()
        study.get_areas.return_value = {"fr": MagicMock()}
        study.get_output.return_value.get_load_ts_numbers.return_value.get.return_value = None

        result = convert_load_units(study, params, fr_dataset)

        assert len(result.load) == 0

    def test_skips_area_absent_from_study(self, fr_dataset):
        params = make_params(market_areas=["fr"])

        study = MagicMock()
        study.get_areas.return_value = {}

        result = convert_load_units(study, params, fr_dataset)

        assert len(result.load) == 0

    def test_converts_multiple_areas(self):
        params = make_params(market_areas=["fr", "de"])
        dataset = make_area_dataset("fr", "de")

        study = MagicMock()
        study.get_areas.return_value = {"fr": MagicMock(), "de": MagicMock()}
        study.get_output.return_value.get_load_ts_numbers.return_value.get.return_value = 1

        result = convert_load_units(study, params, dataset)

        assert len(result.load) == 2
        assert result.load.get("fr_l") is not None
        assert result.load.get("de_l") is not None

    def test_only_converts_areas_in_market_areas(self):
        params = make_params(market_areas=["fr"])
        dataset = make_area_dataset("fr", "de")

        area_fr = MagicMock()
        area_de = MagicMock()
        study = MagicMock()
        study.get_areas.return_value = {"fr": area_fr, "de": area_de}
        study.get_output.return_value.get_load_ts_numbers.return_value.get.return_value = 1

        result = convert_load_units(study, params, dataset)

        assert len(result.load) == 1
        assert result.load.get("fr_l") is not None


# ── TestConvertLinks ───────────────────────────────────────────────────────────


def _make_link_mock(
    from_id: str,
    to_id: str,
    direct_values: list[float] | None = None,
    indirect_values: list[float] | None = None,
) -> MagicMock:
    """Build a mock Link with configurable capacity series (8760 hourly values)."""
    if direct_values is None:
        direct_values = [100.0] * 8760
    if indirect_values is None:
        indirect_values = [80.0] * 8760

    direct = pd.Series(direct_values)
    indirect = pd.Series(indirect_values)

    link = MagicMock()
    link.area_from_id = from_id
    link.area_to_id = to_id
    link.get_capacity_direct.return_value = [direct]
    link.get_capacity_indirect.return_value = [indirect]
    return link


class TestConvertLinks:
    def test_converts_link_between_two_market_areas(self, fr_de_dataset):
        params = make_params(market_areas=["fr", "de"])
        link = _make_link_mock("fr", "de")

        study = MagicMock()
        study.get_links.return_value = {"fr / de": link}

        result = convert_links(study, params, fr_de_dataset)

        assert len(result.market_border) == 1

    def test_link_name_replaces_slash_separator(self, fr_de_dataset):
        params = make_params(market_areas=["fr", "de"])
        link = _make_link_mock("fr", "de")

        study = MagicMock()
        study.get_links.return_value = {"fr / de": link}

        result = convert_links(study, params, fr_de_dataset)

        assert result.market_border.get("fr_de") is not None

    def test_skips_link_when_one_area_absent_from_market_areas(self, fr_de_dataset):
        # "be" is not in market_areas
        params = make_params(market_areas=["fr", "de"])
        link = _make_link_mock("fr", "be")

        study = MagicMock()
        study.get_links.return_value = {"fr / be": link}

        result = convert_links(study, params, fr_de_dataset)

        assert len(result.market_border) == 0

    def test_skips_link_with_zero_capacity_in_both_directions(self, fr_de_dataset):
        params = make_params(market_areas=["fr", "de"])
        link = _make_link_mock("fr", "de", direct_values=[0.0] * 8760, indirect_values=[0.0] * 8760)

        study = MagicMock()
        study.get_links.return_value = {"fr / de": link}

        result = convert_links(study, params, fr_de_dataset)

        assert len(result.market_border) == 0

    def test_includes_link_with_nonzero_direct_only(self, fr_de_dataset):
        params = make_params(market_areas=["fr", "de"])
        link = _make_link_mock("fr", "de", direct_values=[100.0] * 8760, indirect_values=[0.0] * 8760)

        study = MagicMock()
        study.get_links.return_value = {"fr / de": link}

        result = convert_links(study, params, fr_de_dataset)

        assert len(result.market_border) == 1

    def test_includes_link_with_nonzero_indirect_only(self, fr_de_dataset):
        params = make_params(market_areas=["fr", "de"])
        link = _make_link_mock("fr", "de", direct_values=[0.0] * 8760, indirect_values=[50.0] * 8760)

        study = MagicMock()
        study.get_links.return_value = {"fr / de": link}

        result = convert_links(study, params, fr_de_dataset)

        assert len(result.market_border) == 1

    def test_converts_multiple_links(self, fr_de_dataset):
        dataset = make_area_dataset("fr", "de", "be")
        params = make_params(market_areas=["fr", "de", "be"])

        study = MagicMock()
        study.get_links.return_value = {
            "fr / de": _make_link_mock("fr", "de"),
            "fr / be": _make_link_mock("fr", "be"),
        }

        result = convert_links(study, params, dataset)

        assert len(result.market_border) == 2

    def test_returns_empty_when_no_links(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        study = MagicMock()
        study.get_links.return_value = {}

        result = convert_links(study, params, fr_dataset)

        assert len(result.market_border) == 0


# ── Storage helper ─────────────────────────────────────────────────────────────


def _make_st_storage_mock(
    storage_id: str = "fr_battery_1",
    group: str = "Battery",
    reservoir_capacity: float = 10.0,
    efficiency: float = 0.9,
    injection_nominal_capacity: float = 100.0,
    withdrawal_nominal_capacity: float = 100.0,
) -> MagicMock:
    storage = MagicMock()
    storage.id = storage_id
    storage.properties.group = group
    storage.properties.reservoir_capacity = reservoir_capacity
    storage.properties.efficiency = efficiency
    storage.properties.injection_nominal_capacity = injection_nominal_capacity
    storage.properties.withdrawal_nominal_capacity = withdrawal_nominal_capacity
    return storage


# ── TestConvertBatteryUnits ────────────────────────────────────────────────────


class TestConvertBatteryUnits:
    def test_converts_battery_unit(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        storage = _make_st_storage_mock(storage_id="fr_battery_1", group="Battery")

        area = MagicMock()
        area.id = "fr"
        area.get_st_storages.return_value = {"fr_battery_1": storage}

        study = MagicMock()
        study.get_areas.return_value = {"fr": area}
        study.get_output.return_value.get_st_storage_inflows_numbers.return_value.get.return_value = None

        with (
            patch(f"{_STORAGE_HELPERS}.get_power_bounds", return_value=(_ts(params, 100.0), _ts(params, 100.0))),
            patch(f"{_STORAGE_HELPERS}.get_minimum_soc", return_value=_ts(params, 0.0)),
        ):
            result = convert_battery_units(study, params, fr_dataset)

        assert len(result.storage) == 1
        assert result.storage.get("fr_battery_1") is not None

    def test_battery_unit_name_matches_storage_id(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        storage = _make_st_storage_mock(storage_id="fr_bess_big")

        area = MagicMock()
        area.id = "fr"
        area.get_st_storages.return_value = {"fr_bess_big": storage}

        study = MagicMock()
        study.get_areas.return_value = {"fr": area}
        study.get_output.return_value.get_st_storage_inflows_numbers.return_value.get.return_value = None

        with (
            patch(f"{_STORAGE_HELPERS}.get_power_bounds", return_value=(_ts(params), _ts(params))),
            patch(f"{_STORAGE_HELPERS}.get_minimum_soc", return_value=_ts(params, 0.0)),
        ):
            result = convert_battery_units(study, params, fr_dataset)

        assert result.storage.get("fr_bess_big").name == "fr_bess_big"

    def test_skips_psp_open_group(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        storage = _make_st_storage_mock(group=STStorageGroup.PSP_OPEN.value)

        area = MagicMock()
        area.id = "fr"
        area.get_st_storages.return_value = {"phs_open_1": storage}

        study = MagicMock()
        study.get_areas.return_value = {"fr": area}

        result = convert_battery_units(study, params, fr_dataset)

        assert len(result.storage) == 0

    def test_skips_psp_closed_group(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        storage = _make_st_storage_mock(group=STStorageGroup.PSP_CLOSED.value)

        area = MagicMock()
        area.id = "fr"
        area.get_st_storages.return_value = {"phs_closed_1": storage}

        study = MagicMock()
        study.get_areas.return_value = {"fr": area}

        result = convert_battery_units(study, params, fr_dataset)

        assert len(result.storage) == 0

    def test_skips_pondage_group(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        storage = _make_st_storage_mock(group=STStorageGroup.PONDAGE.value)

        area = MagicMock()
        area.id = "fr"
        area.get_st_storages.return_value = {"pondage_1": storage}

        study = MagicMock()
        study.get_areas.return_value = {"fr": area}

        result = convert_battery_units(study, params, fr_dataset)

        assert len(result.storage) == 0

    def test_skips_area_absent_from_study(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        study = MagicMock()
        study.get_areas.return_value = {}

        result = convert_battery_units(study, params, fr_dataset)

        assert len(result.storage) == 0

    def test_converts_multiple_batteries_in_same_area(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        bat1 = _make_st_storage_mock(storage_id="fr_batt_1", group="Battery")
        bat2 = _make_st_storage_mock(storage_id="fr_batt_2", group="Battery")

        area = MagicMock()
        area.id = "fr"
        area.get_st_storages.return_value = {"fr_batt_1": bat1, "fr_batt_2": bat2}

        study = MagicMock()
        study.get_areas.return_value = {"fr": area}
        study.get_output.return_value.get_st_storage_inflows_numbers.return_value.get.return_value = None

        with (
            patch(f"{_STORAGE_HELPERS}.get_power_bounds", return_value=(_ts(params), _ts(params))),
            patch(f"{_STORAGE_HELPERS}.get_minimum_soc", return_value=_ts(params, 0.0)),
        ):
            result = convert_battery_units(study, params, fr_dataset)

        assert len(result.storage) == 2

    def test_only_converts_areas_in_market_areas(self):
        params = make_params(market_areas=["fr"])
        dataset = make_area_dataset("fr", "de")

        bat_fr = _make_st_storage_mock(storage_id="fr_batt", group="Battery")
        bat_de = _make_st_storage_mock(storage_id="de_batt", group="Battery")

        area_fr = MagicMock()
        area_fr.id = "fr"
        area_fr.get_st_storages.return_value = {"fr_batt": bat_fr}

        area_de = MagicMock()
        area_de.id = "de"
        area_de.get_st_storages.return_value = {"de_batt": bat_de}

        study = MagicMock()
        study.get_areas.return_value = {"fr": area_fr, "de": area_de}
        study.get_output.return_value.get_st_storage_inflows_numbers.return_value.get.return_value = None

        with (
            patch(f"{_STORAGE_HELPERS}.get_power_bounds", return_value=(_ts(params), _ts(params))),
            patch(f"{_STORAGE_HELPERS}.get_minimum_soc", return_value=_ts(params, 0.0)),
        ):
            result = convert_battery_units(study, params, dataset)

        assert len(result.storage) == 1
        assert result.storage.get("fr_batt") is not None


# ── TestConvertPHSClosedUnits ──────────────────────────────────────────────────


class TestConvertPHSClosedUnits:
    def test_converts_phs_closed_unit(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        storage = _make_st_storage_mock(
            storage_id="fr_phs_closed_1",
            group=STStorageGroup.PSP_CLOSED.value,
            reservoir_capacity=50.0,
        )

        area = MagicMock()
        area.id = "fr"
        area.get_st_storages.return_value = {"fr_phs_closed_1": storage}

        study = MagicMock()
        study.get_areas.return_value = {"fr": area}
        study.get_output.return_value.get_st_storage_inflows_numbers.return_value.get.return_value = None

        with (
            patch(f"{_STORAGE_HELPERS}.get_power_bounds", return_value=(_ts(params, 200.0), _ts(params, 200.0))),
            patch(f"{_STORAGE_HELPERS}.get_minimum_soc", return_value=_ts(params, 0.0)),
        ):
            result = convert_phs_closed_units(study, params, fr_dataset)

        assert len(result.storage) == 1
        assert result.storage.get("fr_phs_closed_1") is not None

    def test_phs_closed_unit_name_matches_storage_id(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        storage = _make_st_storage_mock(
            storage_id="fr_phs_c",
            group=STStorageGroup.PSP_CLOSED.value,
            reservoir_capacity=10.0,
        )

        area = MagicMock()
        area.id = "fr"
        area.get_st_storages.return_value = {"fr_phs_c": storage}

        study = MagicMock()
        study.get_areas.return_value = {"fr": area}
        study.get_output.return_value.get_st_storage_inflows_numbers.return_value.get.return_value = None

        with (
            patch(f"{_STORAGE_HELPERS}.get_power_bounds", return_value=(_ts(params), _ts(params))),
            patch(f"{_STORAGE_HELPERS}.get_minimum_soc", return_value=_ts(params, 0.0)),
        ):
            result = convert_phs_closed_units(study, params, fr_dataset)

        assert result.storage.get("fr_phs_c").name == "fr_phs_c"

    def test_skips_zero_reservoir_capacity(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        storage = _make_st_storage_mock(
            storage_id="fr_phs_empty",
            group=STStorageGroup.PSP_CLOSED.value,
            reservoir_capacity=0.0,
        )

        area = MagicMock()
        area.id = "fr"
        area.get_st_storages.return_value = {"fr_phs_empty": storage}

        study = MagicMock()
        study.get_areas.return_value = {"fr": area}

        result = convert_phs_closed_units(study, params, fr_dataset)

        assert len(result.storage) == 0

    def test_skips_non_psp_closed_groups(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        # Battery group should not be picked up by PHS closed converter
        storage = _make_st_storage_mock(storage_id="fr_batt", group="Battery", reservoir_capacity=10.0)

        area = MagicMock()
        area.id = "fr"
        area.get_st_storages.return_value = {"fr_batt": storage}

        study = MagicMock()
        study.get_areas.return_value = {"fr": area}

        result = convert_phs_closed_units(study, params, fr_dataset)

        assert len(result.storage) == 0

    def test_skips_area_absent_from_study(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        study = MagicMock()
        study.get_areas.return_value = {}

        result = convert_phs_closed_units(study, params, fr_dataset)

        assert len(result.storage) == 0

    def test_converts_multiple_phs_in_same_area(self, fr_dataset):
        params = make_params(market_areas=["fr"])
        phs1 = _make_st_storage_mock("fr_phs_1", STStorageGroup.PSP_CLOSED.value, reservoir_capacity=20.0)
        phs2 = _make_st_storage_mock("fr_phs_2", STStorageGroup.PSP_CLOSED.value, reservoir_capacity=30.0)

        area = MagicMock()
        area.id = "fr"
        area.get_st_storages.return_value = {"fr_phs_1": phs1, "fr_phs_2": phs2}

        study = MagicMock()
        study.get_areas.return_value = {"fr": area}
        study.get_output.return_value.get_st_storage_inflows_numbers.return_value.get.return_value = None

        with (
            patch(f"{_STORAGE_HELPERS}.get_power_bounds", return_value=(_ts(params), _ts(params))),
            patch(f"{_STORAGE_HELPERS}.get_minimum_soc", return_value=_ts(params, 0.0)),
        ):
            result = convert_phs_closed_units(study, params, fr_dataset)

        assert len(result.storage) == 2

    def test_only_converts_areas_in_market_areas(self):
        params = make_params(market_areas=["fr"])
        dataset = make_area_dataset("fr", "de")

        phs_fr = _make_st_storage_mock("fr_phs", STStorageGroup.PSP_CLOSED.value, reservoir_capacity=10.0)
        phs_de = _make_st_storage_mock("de_phs", STStorageGroup.PSP_CLOSED.value, reservoir_capacity=10.0)

        area_fr = MagicMock()
        area_fr.id = "fr"
        area_fr.get_st_storages.return_value = {"fr_phs": phs_fr}

        area_de = MagicMock()
        area_de.id = "de"
        area_de.get_st_storages.return_value = {"de_phs": phs_de}

        study = MagicMock()
        study.get_areas.return_value = {"fr": area_fr, "de": area_de}
        study.get_output.return_value.get_st_storage_inflows_numbers.return_value.get.return_value = None

        with (
            patch(f"{_STORAGE_HELPERS}.get_power_bounds", return_value=(_ts(params), _ts(params))),
            patch(f"{_STORAGE_HELPERS}.get_minimum_soc", return_value=_ts(params, 0.0)),
        ):
            result = convert_phs_closed_units(study, params, dataset)

        assert len(result.storage) == 1
        assert result.storage.get("fr_phs") is not None
