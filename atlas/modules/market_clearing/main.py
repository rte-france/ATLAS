"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import argparse

import yaml

from atlas.io_utils.input_loader import InputLoader
from atlas.modules.market_clearing.marker_clearing_module import MarketClearingModule

if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--parameters", type=str, required=True, help="Path to the yaml parameters file")
    parser.add_argument("--data", type=str, required=True, help="Path to the data directory")

    args = parser.parse_args()

    raw_data_path = args.data
    raw_params_path = args.parameters
    with open(raw_params_path) as r:
        raw_params = yaml.safe_load(r)

    mc_module = MarketClearingModule()
    raw_data = InputLoader.from_directory(raw_data_path)
    mc_module.run(raw_data, raw_params)
