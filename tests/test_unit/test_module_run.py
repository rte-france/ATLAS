"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
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


class TestModuleRunRun:
    def test_returns_atlas_dataset(self):
        module = _make_module()
        mr = ModuleRun(module, _make_dataset(), {})
        with patch("atlas.modules.module_run.CurrentInputState"), \
             patch("atlas.modules.module_run.CISHandler"):
            result = mr.run()
        assert result is not None

    def test_module_run_called_with_cis_data_and_parameters(self):
        module = _make_module()
        dataset = _make_dataset()
        params = {"k": "v"}
        module_run = ModuleRun(module, dataset, params)

        cis_instance = MagicMock()
        cis_data = MagicMock()
        cis_instance.get_data.return_value = cis_data

        with patch("atlas.modules.module_run.CurrentInputState", return_value=cis_instance), \
             patch("atlas.modules.module_run.CISHandler"):
            module_run.run()

        module.run.assert_called_once_with(cis_data, params)

    def test_cis_created_with_dataset(self):
        module = _make_module()
        dataset = _make_dataset()
        mr = ModuleRun(module, dataset, {})

        with patch("atlas.modules.module_run.CurrentInputState") as mock_cis_cls, \
             patch("atlas.modules.module_run.CISHandler"):
            mr.run()

        mock_cis_cls.assert_called_once_with(dataset)

    def test_cis_handler_apply_called_with_change_sets(self):
        change_sets = [MagicMock(), MagicMock()]
        module = _make_module(change_sets=change_sets)
        mr = ModuleRun(module, _make_dataset(), {})

        cis_instance = MagicMock()
        cis_instance.get_data.return_value = MagicMock()

        with patch("atlas.modules.module_run.CurrentInputState", return_value=cis_instance), \
             patch("atlas.modules.module_run.CISHandler") as mock_handler:
            mr.run()

        mock_handler.apply.assert_called_once_with(change_sets, cis_instance)

    def test_returns_cis_data_without_copy(self):
        module = _make_module()
        mr = ModuleRun(module, _make_dataset(), {})

        cis_instance = MagicMock()
        final_data = MagicMock()
        cis_instance.get_data.side_effect = lambda copy=True: MagicMock() if copy else final_data

        with patch("atlas.modules.module_run.CurrentInputState", return_value=cis_instance), \
             patch("atlas.modules.module_run.CISHandler"):
            result = mr.run()

        assert result is final_data

    def test_module_run_exception_propagates(self):
        module = _make_module()
        module.run.side_effect = AssertionError("validation failed")
        mr = ModuleRun(module, _make_dataset(), {})

        with patch("atlas.modules.module_run.CurrentInputState"), \
             patch("atlas.modules.module_run.CISHandler"):
            with pytest.raises(AssertionError, match="validation failed"):
                mr.run()

    def test_cis_handler_exception_propagates(self):
        module = _make_module()
        mr = ModuleRun(module, _make_dataset(), {})

        cis_instance = MagicMock()
        cis_instance.get_data.return_value = MagicMock()

        with patch("atlas.modules.module_run.CurrentInputState", return_value=cis_instance), \
             patch("atlas.modules.module_run.CISHandler") as mock_handler:
            mock_handler.apply.side_effect = RuntimeError("apply failed")
            with pytest.raises(RuntimeError, match="apply failed"):
                mr.run()
