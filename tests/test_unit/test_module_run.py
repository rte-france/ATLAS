"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atlas.modules.module_run import ModuleRun


def _make_module(change_sets=None, run_return=None):
    """Return a mock AbstractModule whose run() returns an output_dataset with change_sets."""
    output_dataset = MagicMock()
    output_dataset.change_sets = change_sets or []
    if run_return is not None:
        output_dataset = run_return
    module = MagicMock()
    module.run.return_value = output_dataset
    return module


def _make_dataset():
    return MagicMock()


def _make_mr(module=None, cis=None, params=None):
    """Build a ModuleRun bypassing __init__, with a pre-resolved module and CIS."""
    mr = ModuleRun.__new__(ModuleRun)
    mr.module = module if module is not None else _make_module()
    mr.dataset = cis if cis is not None else MagicMock()
    mr.parameters = params if params is not None else {}
    return mr


class TestModuleRunResolve:
    def test_module_instance_used_as_is(self):
        module = _make_module()
        with patch("atlas.modules.module_run.CurrentInputState"):
            mr = ModuleRun(module, _make_dataset(), {})
        assert mr.module is module

    def test_module_class_is_instantiated(self):
        module_instance = MagicMock()

        class FakeModule:
            def __new__(cls):
                return module_instance

        result = ModuleRun._resolve_module(FakeModule)
        assert result is module_instance

    def test_module_string_resolved_via_registry(self):
        module_instance = _make_module()
        module_cls = MagicMock(return_value=module_instance)
        with patch("atlas.modules.module_run.ModuleRegistry") as mock_registry:
            mock_registry.get.return_value = module_cls
            result = ModuleRun._resolve_module("MarketClearing")
        mock_registry.get.assert_called_once_with("MarketClearing")
        assert result is module_instance

    def test_module_unknown_string_raises(self):
        with pytest.raises(ValueError, match="Unknown module"):
            ModuleRun._resolve_module("NonExistentModule")

    def test_dataset_instance_wraps_in_cis(self):
        dataset = _make_dataset()
        cis = MagicMock()
        with patch("atlas.modules.module_run.CurrentInputState", return_value=cis) as mock_cis_cls:
            result = ModuleRun._resolve_dataset(dataset)
        mock_cis_cls.assert_called_once_with(dataset)
        assert result is cis

    def test_dataset_path_calls_from_directory(self):
        path = Path("/some/dir")
        fake_cis = MagicMock()
        with patch("atlas.modules.module_run.CurrentInputState") as mock_cis:
            mock_cis.from_directory.return_value = fake_cis
            result = ModuleRun._resolve_dataset(path)
        mock_cis.from_directory.assert_called_once_with(path)
        assert result is fake_cis

    def test_dataset_str_calls_from_directory(self):
        fake_cis = MagicMock()
        with patch("atlas.modules.module_run.CurrentInputState") as mock_cis:
            mock_cis.from_directory.return_value = fake_cis
            result = ModuleRun._resolve_dataset("/some/dir")
        mock_cis.from_directory.assert_called_once_with("/some/dir")
        assert result is fake_cis

    def test_cis_stored_at_init(self):
        dataset = _make_dataset()
        cis_instance = MagicMock()
        with patch("atlas.modules.module_run.CurrentInputState", return_value=cis_instance) as mock_cis_cls:
            mr = ModuleRun(_make_module(), dataset, {})
        mock_cis_cls.assert_called_once_with(dataset)
        assert mr.dataset is cis_instance


class TestModuleRunRun:
    def test_returns_atlas_dataset(self):
        mr = _make_mr()
        with patch("atlas.modules.module_run.CISHandler"):
            result = mr.run()
        assert result is not None

    def test_module_run_called_with_cis_data_and_parameters(self):
        cis_instance = MagicMock()
        cis_data = MagicMock()
        cis_instance.get_data.return_value = cis_data
        module = _make_module()
        params = {"k": "v"}
        mr = _make_mr(module=module, cis=cis_instance, params=params)

        with patch("atlas.modules.module_run.CISHandler"):
            mr.run()

        module.run.assert_called_once_with(cis_data, params)

    def test_cis_handler_apply_called_with_change_sets(self):
        change_sets = [MagicMock(), MagicMock()]
        module = _make_module(change_sets=change_sets)
        cis_instance = MagicMock()
        cis_instance.get_data.return_value = MagicMock()
        mr = _make_mr(module=module, cis=cis_instance)

        with patch("atlas.modules.module_run.CISHandler") as mock_handler:
            mr.run()

        mock_handler.apply.assert_called_once_with(change_sets, cis_instance)

    def test_returns_cis_data_without_copy(self):
        module = _make_module()
        cis_instance = MagicMock()
        final_data = MagicMock()
        cis_instance.get_data.side_effect = lambda copy=True: MagicMock() if copy else final_data
        mr = _make_mr(module=module, cis=cis_instance)

        with patch("atlas.modules.module_run.CISHandler"):
            result = mr.run()

        assert result is final_data

    def test_module_run_exception_propagates(self):
        module = _make_module()
        module.run.side_effect = AssertionError("validation failed")
        mr = _make_mr(module=module)

        with patch("atlas.modules.module_run.CISHandler"):
            with pytest.raises(AssertionError, match="validation failed"):
                mr.run()

    def test_cis_handler_exception_propagates(self):
        module = _make_module()
        cis_instance = MagicMock()
        cis_instance.get_data.return_value = MagicMock()
        mr = _make_mr(module=module, cis=cis_instance)

        with patch("atlas.modules.module_run.CISHandler") as mock_handler:
            mock_handler.apply.side_effect = RuntimeError("apply failed")
            with pytest.raises(RuntimeError, match="apply failed"):
                mr.run()
