"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
import os
import pickle
import pandas as pd
import pytest

from atlas import InputLoader
from atlas.modules.market_clearing.marker_clearing_module import MarketClearingModule
from atlas.modules.market_clearing.phases.clearing import Clearing
from atlas.solver.solver_helper import SolverHelper
from tests.market_clearing_local.test_market_data_market_clearing import read_expected_data


def compare_lp(atlas_lp_path, prometheus_lp_path, lp_mapping_path, other_mapping=None):
    with open(atlas_lp_path, mode="r") as expected_lp_file:
        atlas_lp = expected_lp_file.read()

    mapping_df = pd.read_csv(lp_mapping_path, delimiter=";")[["New Name", "Original Name"]]
    with open(prometheus_lp_path, mode="r") as expected_lp_file:
        expected_lp = expected_lp_file.read()

    for index, row in mapping_df.iterrows():
        expected_lp = expected_lp.replace(row["New Name"], row["Original Name"])
    if other_mapping:
        pass
    atlas_lp = SolverHelper.read_lp_ortools(atlas_lp_path)
    legacy_lp = SolverHelper.read_lp_legacy(prometheus_lp_path)


def compute_mapping_from_market_data(market_data_path):
    coupling_groups, market_areas, control_blocks, market_borders, market_data = read_expected_data(market_data_path)
    print()


@pytest.mark.skip(reason="No data available")
def test_clearing():
    path = "C:/Users/aboutet/Documents/atlas 2/ATLAS/data/market_clearing_prometheus/MarketClearing input v1.3 ATC_1"
    parameters_path = os.path.join(path, "parameters.yml")
    dataset_path = os.path.join(path, "atlas-dataset")
    pkl_path = os.path.join(path, "raw_data.pkl")
    expected_lp_path = os.path.join(path, "optimization_data", "clearing_phase.lp")
    lp_mapping_path = os.path.join(path, "optimization_data", "clearing_phase.lp_correspondance.csv")

    if os.path.exists(pkl_path):
        print("Chargement rapide depuis un pickle...")
        with open(pkl_path, "rb") as f:
            raw_data = pickle.load(f)
    else:
        print("Chargement long des données...")
        raw_data = InputLoader.from_directory(dataset_path)
        print("Création d'un pickle...")
        with open(pkl_path, "wb") as f:
            pickle.dump(raw_data, f)

    mc_module = MarketClearingModule()
    parameters = mc_module.import_parameters(parameters_path)
    input_dataset = mc_module.import_data(raw_data, parameters)

    clearing = Clearing(input_dataset, parameters)
    clearing.run()

    clearing_lp_path = os.path.join(path, "tests", "market_clearing_local", "clearing_model.lp")

    compare_lp(clearing_lp_path, expected_lp_path, lp_mapping_path)

    print()

@pytest.mark.skip(reason="No data available")
def test_compare_lp():
    path = "C:/Users/aboutet/Documents/atlas 2/ATLAS/data/market_clearing_prometheus/MarketClearing input v1.3 ATC_1"
    expected_lp_path = os.path.join(path, "optimization_data", "clearing_phase.lp")
    lp_mapping_path = os.path.join(path, "optimization_data", "clearing_phase.lp_correspondance.csv")
    clearing_lp_path = "clearing_model.lp"
    market_data_path = os.path.join(path, "market_data_export")

    other_mapping = compute_mapping_from_market_data(market_data_path)

    compare_lp(clearing_lp_path, expected_lp_path, lp_mapping_path)


