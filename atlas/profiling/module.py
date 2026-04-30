"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import cProfile
import pstats
from pathlib import Path
from typing import cast

from pyinstrument import Profiler

from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.module_run import ModuleRun
from atlas.orchestrator.module_registry import ModuleRegistry


def run(config_path: Path, module_name: str, dataset_path: Path, output: Path | None = None) -> None:
    output = output or Path(f"profile_{module_name}.html")

    module_class = ModuleRegistry.get(module_name)
    module = module_class()
    parameters = cast(AbstractModuleParameters, module.get_parameters_class()).from_file(config_path)
    dataset = AtlasDataset.from_directory(dataset_path)
    module_run = ModuleRun(module, dataset, parameters)

    profiler = Profiler()
    c_profile = cProfile.Profile()

    profiler.start()
    c_profile.enable()

    module_run.run()

    c_profile.disable()
    profiler.stop()
    profiler.write_html(output)

    with open("profile_stats.txt", "w") as f:
        print("Profile saved to: profile_stats.txt")
        ps = pstats.Stats(c_profile, stream=f).sort_stats("cumtime")
        ps.print_stats(100)

    print(f"Profile saved to: {output.resolve()}")
