"""
Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Structure tests for antares_to_atlas: Converter base class, ConverterRegistry,
AntaresToAtlas orchestrator, and AntaresToAtlasParameters.
"""

import pytest
from unittest.mock import MagicMock

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.antares_to_atlas.antares_to_atlas import AntaresToAtlas
from atlas.modules.antares_to_atlas.converters.base import Converter
from atlas.modules.antares_to_atlas.converters.registry import ConverterRegistry
from atlas.modules.antares_to_atlas.converters.standard import SystemStructureConverter
from atlas.modules.antares_to_atlas.parameters import (
    AntaresToAtlasParameters,
    ConvertersTags,
    HypothesisEnum,
)

from tests.test_unit.test_antares_to_atlas.conftest import make_params

# ── Minimal concrete converters used across multiple test classes ──────────────


class _ThermalConverter(Converter):
    name = "_thermal"
    description = "Thermal Test Converter"
    tags = [ConvertersTags.THERMAL]

    def convert(self, study, parameters, atlas_dataset):
        return atlas_dataset


class _StorageConverter(Converter):
    name = "_storage"
    description = "Storage Test Converter"
    tags = [ConvertersTags.STORAGE]
    required_market_areas = ["fr"]

    def convert(self, study, parameters, atlas_dataset):
        return atlas_dataset


class _FrOnlyConverter(Converter):
    name = "_fr_only"
    description = "FR-only Test Converter"
    tags = [ConvertersTags.SYSTEM]
    required_market_areas = ["fr"]

    def convert(self, study, parameters, atlas_dataset):
        return atlas_dataset


# ── TestConverterBase ──────────────────────────────────────────────────────────


class TestConverterBase:
    def test_missing_name_raises_type_error(self):
        with pytest.raises(TypeError, match="must declare class attribute 'name'"):

            class _Unnamed(Converter):
                def convert(self, study, params, ds):
                    return ds

    def test_default_description_filled_from_name(self):
        class _C(Converter):
            name = "myconv"

            def convert(self, s, p, d):
                return d

        assert _C.description == "myconv converter"

    def test_explicit_description_kept(self):
        class _Explicit(Converter):
            name = "exp"
            description = "Explicit description"

            def convert(self, s, p, d):
                return d

        assert _Explicit.description == "Explicit description"

    def test_should_run_default_true(self):
        assert _ThermalConverter().should_run(make_params()) is True

    def test_should_run_conversion_steps_excludes_unlisted(self):
        params = make_params(conversion_steps=["other_step"])
        assert _ThermalConverter().should_run(params) is False

    def test_should_run_conversion_steps_includes_listed(self):
        params = make_params(conversion_steps=["_thermal"])
        assert _ThermalConverter().should_run(params) is True

    def test_should_run_only_tags_no_match_excluded(self):
        params = make_params(only_tags=[ConvertersTags.STORAGE])
        assert _ThermalConverter().should_run(params) is False

    def test_should_run_only_tags_match_included(self):
        params = make_params(only_tags=[ConvertersTags.THERMAL])
        assert _ThermalConverter().should_run(params) is True

    def test_should_run_skip_tags_match_excluded(self):
        params = make_params(skip_tags=[ConvertersTags.THERMAL])
        assert _ThermalConverter().should_run(params) is False

    def test_should_run_skip_tags_no_match_included(self):
        params = make_params(skip_tags=[ConvertersTags.STORAGE])
        assert _ThermalConverter().should_run(params) is True

    def test_should_run_required_area_absent_excluded(self):
        params = make_params(market_areas=["de"])
        assert _FrOnlyConverter().should_run(params) is False

    def test_should_run_required_area_present_included(self):
        params = make_params(market_areas=["fr", "de"])
        assert _FrOnlyConverter().should_run(params) is True

    def test_should_run_market_areas_all_bypasses_area_check(self):
        params = make_params(market_areas="all")
        assert _FrOnlyConverter().should_run(params) is True

    def test_run_returns_dataset_unchanged_when_skipped(self):
        params = make_params(conversion_steps=["other"])
        dataset = AtlasDataset()
        result = _ThermalConverter().run(MagicMock(), params, dataset)
        assert result is dataset

    def test_run_calls_convert_and_returns_result(self):
        params = make_params()
        dataset = AtlasDataset()
        result = _ThermalConverter().run(MagicMock(), params, dataset)
        assert result is dataset

    def test_always_run_bypasses_only_tags_filter(self):
        class _AlwaysOn(Converter):
            name = "_always_on"
            tags = [ConvertersTags.THERMAL]
            always_run = True

            def convert(self, s, p, d):
                return d

        # only_tags restricts to STORAGE — but always_run overrides that
        params = make_params(only_tags=[ConvertersTags.STORAGE])
        assert _AlwaysOn().should_run(params) is True

    def test_always_run_bypasses_skip_tags_filter(self):
        class _AlwaysOn(Converter):
            name = "_always_on2"
            tags = [ConvertersTags.THERMAL]
            always_run = True

            def convert(self, s, p, d):
                return d

        params = make_params(skip_tags=[ConvertersTags.THERMAL])
        assert _AlwaysOn().should_run(params) is True

    def test_always_run_still_respects_conversion_steps(self):
        class _AlwaysOn(Converter):
            name = "_always_on3"
            tags = [ConvertersTags.THERMAL]
            always_run = True

            def convert(self, s, p, d):
                return d

        # conversion_steps is an explicit override — always_run doesn't bypass it
        params = make_params(conversion_steps=["other"])
        assert _AlwaysOn().should_run(params) is False


# ── TestConverterRegistry ──────────────────────────────────────────────────────


class _RegA(Converter):
    name = "_reg_a"
    description = "Reg A"
    tags = [ConvertersTags.THERMAL]

    def convert(self, s, p, d):
        return d


class _RegB(Converter):
    name = "_reg_b"
    description = "Reg B"
    tags = [ConvertersTags.STORAGE]

    def convert(self, s, p, d):
        return d


class TestConverterRegistry:
    def test_register_adds_converter(self):
        registry = ConverterRegistry()
        registry.register(_RegA)
        assert len(registry._converters) == 1

    def test_register_multiple_preserves_order(self):
        registry = ConverterRegistry()
        registry.register(_RegA)
        registry.register(_RegB)
        assert [c.name for c in registry._converters] == ["_reg_a", "_reg_b"]

    def test_get_converter_names_returns_all_when_no_filter(self):
        registry = ConverterRegistry()
        registry.register(_RegA)
        registry.register(_RegB)
        assert registry.get_converter_names() == ["_reg_a", "_reg_b"]

    def test_get_converter_names_filtered_by_only_tags(self):
        registry = ConverterRegistry()
        registry.register(_RegA)
        registry.register(_RegB)
        params = make_params(only_tags=[ConvertersTags.THERMAL])
        assert registry.get_converter_names(params) == ["_reg_a"]

    def test_get_converter_names_filtered_by_skip_tags(self):
        registry = ConverterRegistry()
        registry.register(_RegA)
        registry.register(_RegB)
        params = make_params(skip_tags=[ConvertersTags.STORAGE])
        assert registry.get_converter_names(params) == ["_reg_a"]

    def test_get_converter_details_returns_name_description_pairs(self):
        registry = ConverterRegistry()
        registry.register(_RegA)
        details = registry.get_converter_details()
        assert details == [("_reg_a", "Reg A")]

    def test_execute_all_runs_converters_in_registration_order(self):
        call_order: list[str] = []

        class _First(Converter):
            name = "_first"

            def convert(self, s, p, d):
                call_order.append("first")
                return d

        class _Second(Converter):
            name = "_second"

            def convert(self, s, p, d):
                call_order.append("second")
                return d

        registry = ConverterRegistry()
        registry.register(_First)
        registry.register(_Second)
        registry.execute_all(MagicMock(), make_params(), AtlasDataset())

        assert call_order == ["first", "second"]

    def test_execute_all_skips_converter_when_should_not_run(self):
        executed: list[str] = []

        class _Skip(Converter):
            name = "_skip"

            def convert(self, s, p, d):
                executed.append("ran")
                return d

        registry = ConverterRegistry()
        registry.register(_Skip)
        params = make_params(conversion_steps=["other"])
        registry.execute_all(MagicMock(), params, AtlasDataset())
        assert executed == []

    def test_execute_all_chains_dataset_across_converters(self):
        received_ids: list[int] = []

        class _C1(Converter):
            name = "_c1"

            def convert(self, s, p, d):
                received_ids.append(id(d))
                return d

        class _C2(Converter):
            name = "_c2"

            def convert(self, s, p, d):
                received_ids.append(id(d))
                return d

        registry = ConverterRegistry()
        registry.register(_C1)
        registry.register(_C2)
        original = AtlasDataset()
        registry.execute_all(MagicMock(), make_params(), original)

        assert len(received_ids) == 2
        assert received_ids[0] == received_ids[1]

    def test_execute_all_returns_final_dataset(self):
        registry = ConverterRegistry()
        registry.register(_RegA)
        result = registry.execute_all(MagicMock(), make_params(), AtlasDataset())
        assert isinstance(result, AtlasDataset)


# ── Standard converter names for orchestrator assertions ──────────────────────

_STANDARD_NAMES = {"node", "load", "wind", "solar", "hydro", "link", "thermal", "non_dispatchable", "battery", "phs_closed"}
_BP23_NAMES = {
    "mixed_fuel",
    "electric_vehicle",
    "electric_vehicle_fr",
    "particular_mid_units",
    "particular_peak_units",
    "p2g",
    "multi_energy",
    "dsr",
    "dsr_fr",
    "phs_open",
    "phs_open_fr",
    "phs_fusion",
    "water_value",
    "initial_level",
    "nuclear_modulation",
}

_BASE_PARAMS = {
    "start_date": "2025-01-01T00:00:00",
    "execution_date": "2025-01-01T00:00:00",
    "output_name": "out",
    "market_areas": ["fr"],
}


# ── TestAntaresToAtlasOrchestrator ─────────────────────────────────────────────


class TestAntaresToAtlasOrchestrator:
    def test_from_dict_creates_instance(self):
        ata = AntaresToAtlas.from_dict(_BASE_PARAMS)
        assert isinstance(ata, AntaresToAtlas)

    def test_standard_converters_always_registered(self):
        ata = AntaresToAtlas.from_dict(_BASE_PARAMS)
        registered = set(ata.registry.get_converter_names())
        assert _STANDARD_NAMES.issubset(registered)

    def test_bp23_converters_absent_without_hypothesis(self):
        ata = AntaresToAtlas.from_dict(_BASE_PARAMS)
        registered = set(ata.registry.get_converter_names())
        assert registered.isdisjoint(_BP23_NAMES)

    def test_bp23_converters_registered_with_bp23_hypothesis(self):
        ata = AntaresToAtlas.from_dict({**_BASE_PARAMS, "hypothesis": "BP23"})
        registered = set(ata.registry.get_converter_names())
        assert _STANDARD_NAMES | _BP23_NAMES == registered

    def test_system_structure_converter_always_runs_despite_skip_tags(self):
        ata = AntaresToAtlas.from_dict(_BASE_PARAMS)
        params = ata.parameters.model_copy(update={"skip_tags": [ConvertersTags.SYSTEM]})
        # SystemStructureConverter has always_run=True — tag filter must not exclude it
        names = ata.registry.get_converter_names(params)
        assert "node" in names

    def test_system_structure_converter_always_runs_despite_only_tags(self):
        ata = AntaresToAtlas.from_dict(_BASE_PARAMS)
        params = ata.parameters.model_copy(update={"only_tags": [ConvertersTags.THERMAL]})
        names = ata.registry.get_converter_names(params)
        assert "node" in names

    def test_system_structure_converter_has_always_run_flag(self):
        assert SystemStructureConverter.always_run is True

    def test_total_standard_converter_count(self):
        ata = AntaresToAtlas.from_dict(_BASE_PARAMS)
        assert len(ata.registry.get_converter_names()) == len(_STANDARD_NAMES)

    def test_total_bp23_converter_count(self):
        ata = AntaresToAtlas.from_dict({**_BASE_PARAMS, "hypothesis": "BP23"})
        assert len(ata.registry.get_converter_names()) == len(_STANDARD_NAMES) + len(_BP23_NAMES)

    def test_list_converters_returns_names(self):
        ata = AntaresToAtlas.from_dict(_BASE_PARAMS)
        names = ata.list_converters()
        assert isinstance(names, list)
        assert all(isinstance(n, str) for n in names)
        assert set(names) == _STANDARD_NAMES

    def test_list_converter_details_returns_name_description_pairs(self):
        ata = AntaresToAtlas.from_dict(_BASE_PARAMS)
        details = ata.list_converter_details()
        assert all(isinstance(n, str) and isinstance(d, str) for n, d in details)
        assert len(details) == len(_STANDARD_NAMES)

    def test_resolve_parameters_explicit_areas_unchanged(self):
        ata = AntaresToAtlas.from_dict({**_BASE_PARAMS, "market_areas": ["fr", "de"]})
        study = MagicMock()
        resolved = ata._resolve_parameters(study)
        assert resolved.market_areas == ["fr", "de"]
        study.get_areas.assert_not_called()

    def test_resolve_parameters_expands_all_to_study_areas(self):
        ata = AntaresToAtlas.from_dict({**_BASE_PARAMS, "market_areas": "all"})
        study = MagicMock()
        study.get_areas.return_value = ["fr", "de", "be"]
        resolved = ata._resolve_parameters(study)
        assert set(resolved.market_areas) == {"fr", "de", "be"}

    def test_resolve_parameters_excludes_listed_areas(self):
        ata = AntaresToAtlas.from_dict(
            {**_BASE_PARAMS, "market_areas": "all", "excluded_market_areas": ["de"]}
        )
        study = MagicMock()
        study.get_areas.return_value = ["fr", "de", "be"]
        resolved = ata._resolve_parameters(study)
        assert "de" not in resolved.market_areas
        assert set(resolved.market_areas) == {"fr", "be"}


# ── TestAntaresToAtlasParameters ──────────────────────────────────────────────


class TestAntaresToAtlasParameters:
    def test_minimal_valid_params_accepted(self):
        params = AntaresToAtlasParameters.model_validate(_BASE_PARAMS)
        assert params.market_areas == ["fr"]

    def test_empty_market_areas_rejected(self):
        with pytest.raises(Exception):
            AntaresToAtlasParameters.model_validate({**_BASE_PARAMS, "market_areas": []})

    def test_market_areas_all_string_accepted(self):
        params = AntaresToAtlasParameters.model_validate({**_BASE_PARAMS, "market_areas": "all"})
        assert params.market_areas == "all"

    def test_conversion_steps_defaults_to_empty(self):
        assert make_params().conversion_steps == []

    def test_skip_tags_defaults_to_empty(self):
        assert make_params().skip_tags == []

    def test_only_tags_defaults_to_empty(self):
        assert make_params().only_tags == []

    def test_hypothesis_none_by_default(self):
        assert make_params().hypothesis is None

    def test_hypothesis_bp23_parsed(self):
        params = make_params(hypothesis="BP23")
        assert params.hypothesis == HypothesisEnum.BP23

    def test_scenario_defaults_to_one(self):
        assert make_params().scenario == 1

    def test_minimum_price_defaults(self):
        assert make_params().minimum_price == -500.0

    def test_maximum_price_defaults(self):
        assert make_params().maximum_price == 3000.0

    def test_excluded_market_areas_defaults_to_empty(self):
        assert make_params().excluded_market_areas == []

    def test_excluded_thermic_groups_defaults_to_empty(self):
        assert make_params().excluded_thermic_groups == []
