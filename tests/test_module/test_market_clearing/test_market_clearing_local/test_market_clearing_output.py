import json
import os
import pickle

import pytest
import polars as pl

import atlas.config as cfg
from atlas import AtlasDataset
from atlas.config import EQUIPMENT_MODELS
from atlas.io_utils.utils import to_snake_case
from atlas.models.portfolio import Portfolio
from atlas.modules.market_clearing.module import MarketClearingModule
from atlas.modules.market_clearing.output_dataset import MarketClearingOutputDataset
from tests.test_module.test_market_clearing.test_market_clearing_local.test_market_data_market_clearing import (
    read_expected_data,
)


def retrieve_accepted_powers_from_json(
    optim_variable_path: str, market_area_mapping: dict[str, str], orders_mapping: dict[tuple[str, str], str]
) -> dict[tuple[str, str], float]:
    with open(optim_variable_path, "r") as f:
        optim_variables = json.load(f)
        accepted_powers = {}
        for area_id, balances in enumerate(optim_variables["accepted_powers"]):
            for order_id, _dict in enumerate(balances):
                accepted_powers[market_area_mapping[str(area_id)], orders_mapping[str(area_id), str(order_id)]] = _dict[
                    "VarValue"
                ]
        return accepted_powers


# only work with wo market area
def retrieve_market_prices_from_json(
    optim_variable_path: str, market_area_mapping: dict[str, str]
) -> dict[tuple[str, int], float]:
    with open(optim_variable_path, "r") as f:
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


def retrieve_local_balances_from_json(
    optim_variable_path: str, market_area_mapping: dict[str, str]
) -> dict[tuple[str, int], float]:
    with open(optim_variable_path, "r") as f:
        optim_variables = json.load(f)
        local_balances = {}
        for time_index, balances in enumerate(optim_variables["local_balances"]):
            for area_id, _dict in enumerate(balances):
                local_balances[market_area_mapping[str(area_id)], time_index] = _dict["VarValue"]
        return local_balances


def retrieve_border_exchanges_from_json(
    optim_variable_path: str, border_mapping: dict[str, str]
) -> dict[tuple[str, int], float]:
    with open(optim_variable_path, "r") as f:
        optim_variables = json.load(f)
        borders = {}
        for time_index, balances in enumerate(optim_variables["border_exchanges"]):
            for border_id, _dict in enumerate(balances):
                borders[border_mapping[str(border_id)], time_index] = _dict["VarValue"]
        return borders


def retrieve_orders_mapping(market_area) -> dict[tuple[str, str], str]:
    order_mapping = {}
    for market_area_dict in market_area.values():
        for order_name, order_dict in market_area_dict["orders"].items():
            order_mapping[str(market_area_dict["id"]), str(order_dict["id"])] = to_snake_case(order_name)
    return order_mapping


@pytest.mark.skip(reason="No data available")
@pytest.mark.parametrize(
    "dataset_name",
    [
        "atc-1",
        "atc-2",
        "fb-1",
        "fb-2",
    ],
)
def test_market_clearing_output(dataset_name):
    path = os.path.join("data", "market_clearing_prometheus", "test_clearing", dataset_name)
    parameters_path = os.path.join(path, "parameters.yml")
    dataset_path = os.path.join(path, "atlas-dataset")
    pkl_path = os.path.join(path, "raw_data.pkl")
    expected_dataset_path = os.path.join("data", "market_clearing_prometheus", "test_clearing", "output", dataset_name)
    # last variables come from marginal_fixing
    optim_variables_path = os.path.join(path, "optimization_data", "marginal_fixing", "optim_variables.json")

    raw_data = AtlasDataset.from_directory(dataset_path)

    mc_module = MarketClearingModule()
    parameters = mc_module.import_parameters(parameters_path)
    input_dataset = mc_module.import_data(raw_data, parameters)

    market_data_export_path = os.path.join(path, "market_data_export")
    expected_data = read_expected_data(market_data_export_path)
    _, market_areas, _, borders, _, critical_branches = expected_data
    market_areas_mapping = {value["id"]: key.lower() for key, value in market_areas.items()}
    orders_mapping = retrieve_orders_mapping(market_areas)
    market_borders_mapping = {value["id"]: key.lower() for key, value in borders.items()}

    accepted_powers = retrieve_accepted_powers_from_json(optim_variables_path, market_areas_mapping, orders_mapping)
    local_balances = retrieve_local_balances_from_json(optim_variables_path, market_areas_mapping)
    border_exchanges = retrieve_border_exchanges_from_json(optim_variables_path, market_borders_mapping)
    market_prices = retrieve_market_prices_from_json(optim_variables_path, market_areas_mapping)

    market_clearing_output_dataset = MarketClearingOutputDataset(input_dataset)
    market_clearing_output_dataset.run(accepted_powers, local_balances, border_exchanges, market_prices)

    expected_raw_data = AtlasDataset.from_directory(expected_dataset_path)

    expected_equipments = {}
    for equipment_type in EQUIPMENT_MODELS:
        expected_equipments[equipment_type] = {}
        for equipment in getattr(expected_raw_data, equipment_type):
            expected_equipments[equipment_type][equipment.name] = equipment

    expected_portfolios = {}
    for portfolio in expected_raw_data.portfolio:
        expected_portfolios[portfolio.name] = portfolio

    # Test on equipments
    for equipment_type in EQUIPMENT_MODELS:
        for output_equipment in getattr(market_clearing_output_dataset.raw_data, equipment_type):
            expected_equipment = expected_equipments[equipment_type][output_equipment.name]
            if output_equipment.da_cleared_quantity is None:
                if expected_equipment.da_cleared_quantity is not None:
                    assert False
                continue
            if expected_equipment.da_cleared_quantity is None:
                if output_equipment.da_cleared_quantity is not None:
                    assert False
                continue
            expected_df = expected_equipment.da_cleared_quantity.dataframe
            output_df = output_equipment.da_cleared_quantity.dataframe
            assert expected_df.shape == output_df.shape
            assert expected_df.columns == output_df.columns
            for index in expected_df["time"]:
                expected_value = expected_df.filter(pl.col("time") == index)["value"][0]
                output_value = output_df.filter(pl.col("time") == index)["value"][0]
                try:
                    assert abs(expected_value - output_value) <= 1e-6
                except:
                    print(expected_equipment.name)
                    print(expected_df)
                    print(output_df)

    # Test on portfolios
    for output_portfolio in market_clearing_output_dataset.raw_data.portfolio:
        expected_portfolio = expected_portfolios[output_portfolio.name]
        if output_portfolio.da_cleared_quantity is None:
            if expected_portfolio.da_cleared_quantity is not None:
                assert False
            continue
        if expected_portfolio.da_cleared_quantity is None:
            if output_portfolio.da_cleared_quantity is not None:
                assert False
            continue
        expected_df = expected_portfolio.da_cleared_quantity.dataframe
        output_df = output_portfolio.da_cleared_quantity.dataframe
        assert expected_df.shape == output_df.shape
        assert expected_df.columns == output_df.columns
        for index in expected_df["time"]:
            expected_value = expected_df.filter(pl.col("time") == index)["value"][0]
            output_value = output_df.filter(pl.col("time") == index)["value"][0]
            try:
                assert abs(expected_value - output_value) <= 1e-6
            except:
                print(expected_portfolio.name)
                print(expected_df)
                print(output_df)
