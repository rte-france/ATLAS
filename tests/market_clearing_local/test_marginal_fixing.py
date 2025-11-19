import json
import os
import pickle

import pytest

from atlas.io_utils.input_loader import InputLoader
from atlas.io_utils.utils import to_snake_case
from atlas.modules.market_clearing.marker_clearing_module import MarketClearingModule
from atlas.modules.market_clearing.phases.marginal_fixing import MarginalFixing
from tests.market_clearing_local.test_market_data_market_clearing import read_expected_data


def retrieve_accepted_powers_from_json(optim_variable_path: str, market_area_mapping: dict[str, str], orders_mapping: dict[tuple[str, str], str]) -> dict[tuple[str, str], float]:
    with (open(optim_variable_path, "r") as f):
        optim_variables = json.load(f)
        accepted_powers = {}
        for area_id, balances in enumerate(optim_variables["accepted_powers"]):
            for order_id, _dict in enumerate(balances):
                accepted_powers[market_area_mapping[str(area_id)], orders_mapping[str(area_id), str(order_id)]] = _dict["VarValue"]
        return accepted_powers

# only work with wo market area
def retrieve_market_prices_from_json(optim_variable_path: str, market_area_mapping: dict[str, str]) -> dict[tuple[str, int], float]:
    with (open(optim_variable_path, "r") as f):
        optim_variables = json.load(f)
        market_prices_dict = {}
        for time_index, market_prices in enumerate(optim_variables["groups_prices"]):
            if len(market_prices) == 1:
                for market_area_name in market_area_mapping.values():
                    market_prices_dict[market_area_name, time_index] = market_prices[0]["VarValue"]
            else:
                for area_id, _dict in enumerate(market_prices):
                    market_prices_dict[market_area_mapping[str(area_id)], time_index] = _dict["VarValue"]
        return market_prices_dict

def retrieve_orders_mapping(market_area) -> dict[tuple[str, str], str]:
    order_mapping = {}
    for market_area_dict in market_area.values():
        for order_name, order_dict in market_area_dict["orders"].items():
            order_mapping[str(market_area_dict["id"]), str(order_dict["id"])] = to_snake_case(order_name)
    return order_mapping

def retrieve_marginal_fixing(path, clearing_accepted_powers, market_prices, path_only=False) -> MarginalFixing:
    if not path_only:
        parameters_path = os.path.join(path, "parameters.yml")
        dataset_path = os.path.join(path, "atlas-dataset")
        pkl_path = os.path.join(path, "raw_data.pkl")
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

        marginal_fixing = MarginalFixing(input_dataset, parameters)
        marginal_fixing.run(clearing_accepted_powers, market_prices)
        return marginal_fixing

@pytest.mark.skip(reason="No data available")
@pytest.mark.parametrize(
    "dataset_name",
    [
        "MarketClearing input v1.3 FB_1",
        "MarketClearing input v1.3 FB_2",
        "MarketClearing input v1.3 ATC_1",
        "MarketClearing input v1.3 ATC_2"
    ]
)
def test_compare_lp(dataset_name):
    path = os.path.join("data", "market_clearing_prometheus", dataset_name)
    clearing_optim_variables_path = os.path.join(path, "optimization_data", "clearing", "optim_variables.json")
    pricing_optim_variables_path = os.path.join(path, "optimization_data", "pricing", "optim_variables.json")
    marginal_fixing_optim_variables_path = os.path.join(path, "optimization_data", "marginal_fixing", "optim_variables.json")

    market_data_export_path = os.path.join(path, "market_data_export")
    expected_data = read_expected_data(market_data_export_path)
    _, market_areas, _, borders, _, critical_branches = expected_data
    market_area_mapping = {value["id"]: key.lower() for key, value in market_areas.items()}
    orders_mapping = retrieve_orders_mapping(market_areas)
    clearing_accepted_powers = retrieve_accepted_powers_from_json(clearing_optim_variables_path, market_area_mapping, orders_mapping)
    market_prices = retrieve_market_prices_from_json(pricing_optim_variables_path, market_area_mapping)

    marginal_fixing = retrieve_marginal_fixing(path, clearing_accepted_powers, market_prices)

    # Retrieve expected accepted power after marginal fixing
    expected_accepted_powers = retrieve_accepted_powers_from_json(marginal_fixing_optim_variables_path, market_area_mapping,
                                                                  orders_mapping)

    for (market_area_name, order_name), expected_value in expected_accepted_powers.items():
        assert (market_area_name, order_name) in marginal_fixing.accepted_powers
        value = marginal_fixing.accepted_powers[market_area_name, order_name]
        old_value = clearing_accepted_powers[market_area_name, order_name]
        if abs(expected_value - value) > 1e-8:
            print(f"Movement '{str(order_name)}': {old_value}, {expected_value}, {value}")
        assert expected_value == pytest.approx(value, 1e-8)
