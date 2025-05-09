"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import argparse

from atlas.modules.market_clearing.marker_clearing_module import MarketClearingModule

if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--parameters", type=str, required=True, help="Path to the yaml parameters file")
    parser.add_argument("--data", type=str, required=True, help="Path to the data directory")

    args = parser.parse_args()

    raw_data = args.get("data")
    raw_params = args.get("parameters")

    mc_module = MarketClearingModule()
    mc_module.run(raw_data, raw_params)
