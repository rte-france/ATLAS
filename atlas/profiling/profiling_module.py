"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
import argparse
import cProfile
import pstats
from pathlib import Path

from pyinstrument import Profiler

from atlas.orchestrator.module_registry import ModuleRegistry
from atlas.orchestrator.current_input_state import CurrentInputState
from atlas.orchestrator.handler.cis_handler import CISHandler
from atlas.abstract_class.parameters import AbstractModuleParameters
from typing import cast


def main():
    parser = argparse.ArgumentParser(
        description="Profile a single Atlas module with pyinstrument."
    )
    parser.add_argument("config_path", type=Path)
    parser.add_argument("--module", "-m", required=True)
    parser.add_argument("--dataset", "-d", type=Path, required=True)
    parser.add_argument("--output", "-o", type=Path, default=None)
    args = parser.parse_args()

    output = args.output or Path(f"profile_{args.module}.html")

    module_class = ModuleRegistry.get(args.module)
    module = module_class()
    parameters = cast(AbstractModuleParameters, module.get_parameters_class()).from_file(args.config_path)
    cis = CurrentInputState.from_directory(args.dataset)

    profiler = Profiler()
    c_profile = cProfile.Profile()

    profiler.start()
    c_profile.enable()

    output_dataset = module.run(cis.get_data(copy=False), parameters)
    if parameters.output.export_output_dataset:
        CISHandler.apply(output_dataset.change_sets, cis)

    c_profile.disable()
    profiler.stop()
    profiler.write_html(output)


    with open("profile_stats.txt", "w") as f:
        print(f"Profile saved to: profile_stats.txt")
        ps = pstats.Stats(c_profile, stream=f).sort_stats("cumtime")
        ps.print_stats(100)

    print(f"Profile saved to: {output.resolve()}")


if __name__ == "__main__":
    main()