"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pathlib import Path
from typing import Any

from atlas.abstract_class.module import AbstractModule
from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.orchestrator.current_input_state import CurrentInputState
from atlas.orchestrator.handler.cis_handler import CISHandler
from atlas.orchestrator.module_registry import ModuleRegistry


class ModuleRun:
    def __init__(
        self,
        module: type[AbstractModule] | str,
        dataset: AtlasDataset | Path | str,
        parameters: AbstractModuleParameters | dict[str, Any] | str | Path,
    ):
        self.module = self._resolve_module(module)
        self.dataset = self._resolve_dataset(dataset)
        self.parameters = parameters

    @staticmethod
    def _resolve_module(module: type[AbstractModule] | str) -> AbstractModule:
        if isinstance(module, str):
            return ModuleRegistry.get(module)()
        if isinstance(module, type):
            return module()
        return module

    @staticmethod
    def _resolve_dataset(dataset: AtlasDataset | Path | str) -> CurrentInputState:
        if isinstance(dataset, (Path, str)):
            return CurrentInputState.from_directory(dataset)
        return CurrentInputState(dataset)

    def run(self) -> AtlasDataset:
        cis = self.dataset
        output_dataset = self.module.run(cis.get_data(), self.parameters)
        CISHandler.apply(output_dataset.change_sets, cis)
        return cis.get_data(copy=False)
