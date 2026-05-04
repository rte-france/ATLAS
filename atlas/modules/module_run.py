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


class ModuleRun:
    def __init__(
        self,
        module: AbstractModule,
        dataset: AtlasDataset,
        parameters: AbstractModuleParameters | dict[str, Any] | str | Path,
    ):
        self.module = module
        self.dataset = dataset
        self.parameters = parameters

    def run(self) -> AtlasDataset:
        cis = CurrentInputState(self.dataset)
        output_dataset = self.module.run(cis.get_data(), self.parameters)
        CISHandler.apply(output_dataset.change_sets, cis)
        return cis.get_data(copy=False)
