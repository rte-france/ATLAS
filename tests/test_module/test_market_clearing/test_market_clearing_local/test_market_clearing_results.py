import os
import pickle

import pytest

from atlas import AtlasDataset
from atlas.modules.market_clearing.module import MarketClearingModule
from atlas.modules.market_clearing.phases.market_clearing_results import MarketClearingResults


@pytest.mark.skip(reason="No data available")
@pytest.mark.parametrize(
    "dataset_name",
    [
        "MarketClearing input v1.3 FB_1",
        "MarketClearing input v1.3 FB_2",
        "MarketClearing input v1.3 ATC_1",
        "MarketClearing input v1.3 ATC_2",
    ],
)
def test_compare_lp(dataset_name):
    path = os.path.join("data", "market_clearing_prometheus", dataset_name)
    parameters_path = os.path.join(path, "parameters.yml")
    dataset_path = os.path.join("data", "market_clearing_prometheus", "portfolio-optimisation")
    pkl_path = os.path.join(path, "expected_raw_data.pkl")

    if os.path.exists(pkl_path):
        print("Chargement rapide depuis un pickle...")
        with open(pkl_path, "rb") as f:
            raw_data = pickle.load(f)
    else:
        print("Chargement long des données...")
        raw_data = AtlasDataset.from_directory(dataset_path)
        print("Création d'un pickle...")
        with open(pkl_path, "wb") as f:
            pickle.dump(raw_data, f)

    mc_module = MarketClearingModule()
    parameters = mc_module.import_parameters(parameters_path)
    parameters.output.output_dir = "tmp"
    input_dataset = mc_module.import_data(raw_data, parameters)

    market_clearing_results = MarketClearingResults(input_dataset, parameters)
    market_clearing_results.run()
