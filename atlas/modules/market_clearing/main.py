"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import argparse
import os
import pickle

import yaml

from atlas.io.input_loader import InputLoader
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
    pkl_path = os.path.join(raw_data_path, "..", "raw_data.pkl")
    if os.path.exists(pkl_path):
        print("Chargement rapide depuis un pickle...")
        with open(pkl_path, "rb") as f:
            raw_data = pickle.load(f)
    else:
        print("Chargement long des données...")
        raw_data = InputLoader.from_directory(raw_data_path)
        print("Création d'un pickle...")
        with open(pkl_path, "wb") as f:
            pickle.dump(raw_data, f)
    mc_module.run(raw_data, raw_params)
