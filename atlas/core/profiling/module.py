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

from atlas.core.abstract_class.parameters import AbstractModuleParameters
from atlas.core.io_utils.atlas_dataset import AtlasDataset
from atlas.core.orchestrator.module_registry import ModuleRegistry
from atlas.modules.module_run import ModuleRun


def run(config_path: Path, module_name: str, dataset_path: Path, output: Path | None = None) -> None:
    stem = output.with_suffix("") if output else Path(f"profile_{module_name}")
    html_output = stem.with_suffix(".html")
    stats_output = stem.parent / (stem.name + "_stats.txt")

    module_class = ModuleRegistry.get(module_name)
    module = module_class()
    parameters = cast(AbstractModuleParameters, module.get_parameters_class()).from_file(config_path)
    dataset = AtlasDataset.from_directory(dataset_path)
    module_run = ModuleRun(module, dataset, parameters)

    profiler = Profiler()
    c_profile = cProfile.Profile()

    profiler.start()
    c_profile.enable()
    try:
        module_run.run()
    finally:
        c_profile.disable()
        profiler.stop()

    profiler.write_html(html_output)
    print(f"  pyinstrument saved: {html_output.resolve()}")

    with open(stats_output, "w") as f:
        ps = pstats.Stats(c_profile, stream=f).sort_stats("cumtime")
        ps.print_stats(100)
    print(f"  cProfile saved:     {stats_output.resolve()}")
