"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import argparse

from atlas import InputLoader
from atlas.modules.day_ahead_orders.module import DayAheadOrdersModule

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--parameters", type=str, required=True, help="Path to the yaml parameters file")
    parser.add_argument("--data", type=str, required=True, help="Path to the data directory")
    args = parser.parse_args()

    raw_data_path = args.data
    raw_params_path = args.parameters

    mc_module = DayAheadOrdersModule()
    raw_data = InputLoader.from_directory(raw_data_path)
    mc_module.run(raw_data, raw_params_path)  # type:ignore [arg-type]
