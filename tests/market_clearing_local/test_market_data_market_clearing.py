"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import ast
import math
import os
import pickle
import re
from pathlib import Path
from collections import OrderedDict

import pandas as pd
import pendulum
import pytest

from atlas import InputLoader
from atlas.io_utils.utils import to_snake_case
from atlas.math.timeseries import Timeseries
from atlas.modules.market_clearing.module import MarketClearingModule
from atlas.modules.market_clearing.phases.clearing import Clearing


def transform_dataframe_to_dict(df: pd.DataFrame):
    _dict = {}
    for name, df_group in df.groupby("Name"):
        _dict[name] = {}
        # Convert to dictionary with Attribute as key and Value as value
        _dict[name] = dict(zip(df_group["Attribute"], df_group["Value"]))
    return _dict


def parse_orders(raw_text):
    # Split the raw text into individual orders using regex
    order_blocks = re.findall(r"Order named (.+?) comprised of:\s*(.*?)(?=(?:, Order named|$))", raw_text, re.DOTALL)

    orders = {}

    for name, block in order_blocks:
        order_dict = {"name": name.strip()}
        # Extract all "- key = value" lines
        fields = re.findall(r"- ([a-zA-Z0-9_]+)\s*=\s*(.*)", block)
        for key, value in fields:
            # Convert string values to correct Python types
            value = value.strip()
            if value == "None":
                parsed_value = None
            elif value in ("True", "False"):
                parsed_value = value == "True"
            else:
                try:
                    parsed_value = float(value) if "." in value else int(value)
                except ValueError:
                    parsed_value = value  # Leave as string if not a number
            order_dict[key] = parsed_value
        orders[name] = order_dict

    return orders


def read_order_coupling_csv(path):
    coupling_groups_df = pd.read_csv(Path(path) / "coupling_groups.csv", sep=";")
    coupling_groups = transform_dataframe_to_dict(coupling_groups_df)
    for coupling_group in coupling_groups.values():
        coupling_group["orders_info"] = ast.literal_eval(coupling_group["orders_info"])
    return coupling_groups


def read_critical_branches_csv(path):
    critical_branches_path = Path(path) / "critical_branches.csv"
    if not os.path.exists(critical_branches_path):
        return None
    critical_branches_df = pd.read_csv(critical_branches_path, sep=";")
    critical_branches = transform_dataframe_to_dict(critical_branches_df)
    return critical_branches


def read_market_area_csv(path):
    market_areas_df = pd.read_csv(Path(path) / "market_areas.csv", sep=";")
    market_areas = transform_dataframe_to_dict(market_areas_df)
    for market_area in market_areas.values():
        market_area["ref_balance"] = eval(market_area["ref_balance"])
        market_area["min_price"] = eval(market_area["min_price"])
        market_area["max_price"] = eval(market_area["max_price"])
        market_area["orders"] = parse_orders(market_area["orders"])
    return market_areas


def read_control_block_csv(path):
    control_blocks_df = pd.read_csv(Path(path) / "control_blocks.csv", sep=";")
    control_blocks = transform_dataframe_to_dict(control_blocks_df)
    for control_block in control_blocks.values():
        control_block["market_areas"] = re.findall(r"\('([^']+)',", control_block["market_areas"])
        control_block["max_tso_power_sold"] = eval(control_block["max_tso_power_sold"])
        control_block["max_tso_power_bought"] = eval(control_block["max_tso_power_bought"])
    return control_blocks


def read_market_borders_csv(path):
    market_borders_df = pd.read_csv(Path(path) / "market_borders.csv", sep=";")
    market_borders = transform_dataframe_to_dict(market_borders_df)
    for market_border in market_borders.values():
        market_border["max_flow"] = eval(market_border["max_flow"])
        market_border["min_flow"] = eval(market_border["min_flow"])
    return market_borders


def read_market_data_csv(path):
    market_data_df = pd.read_csv(Path(path) / "market_data.csv", sep=";")
    # Convert to dictionary with Attribute as key and Value as value
    market_data = dict(zip(market_data_df["Attribute"], market_data_df["Value"]))
    market_data["control_blocks"] = re.findall(r"\('([^']+)',", market_data["control_blocks"])
    market_data["coupling_groups"] = market_data["coupling_groups"].count("<OrderCoupling object at")
    market_data["market_borders"] = market_data["market_borders"].count("<MarketBorder object at")
    return market_data


def read_expected_data(path):
    coupling_groups = read_order_coupling_csv(path)
    market_areas = read_market_area_csv(path)
    control_blocks = read_control_block_csv(path)
    market_borders = read_market_borders_csv(path)
    market_data = read_market_data_csv(path)
    critical_branches_data = read_critical_branches_csv(path)
    # Price group is empty before the phases
    return coupling_groups, market_areas, control_blocks, market_borders, market_data, critical_branches_data


def compare_market_area(market_areas_expected, input_dataset):
    for market_area_name, market_area_expected in market_areas_expected.items():
        market_area_mc = input_dataset.mc_market_areas[to_snake_case(market_area_name)]
        assert market_area_mc.market_area.control_block.name == to_snake_case(market_area_expected["control_block"])
        for order_name_expected, order_expected in market_area_expected["orders"].items():
            assert to_snake_case(order_name_expected) in market_area_mc.orders
        assert compare_timeseries_to_dict(market_area_mc.max_price, market_area_expected["max_price"])
        assert compare_timeseries_to_dict(market_area_mc.min_price, market_area_expected["min_price"])
        assert compare_timeseries_to_dict(market_area_mc.ref_balance, market_area_expected["ref_balance"])


def compare_control_block(control_blocks_expected, input_dataset):
    clearing = Clearing(input_dataset, input_dataset.parameters)
    for control_block_expected in control_blocks_expected.values():
        for time_index in range(len(control_block_expected["max_tso_power_sold"])):
            max_tso_power_bought = clearing.get_max_tso_power_bought(
                input_dataset.times[time_index],
                input_dataset.mc_control_blocks[control_block_expected["name"]],
                input_dataset.mc_market_areas,
            )
            max_tso_power_sold = clearing.get_max_tso_power_sold(
                input_dataset.times[time_index],
                input_dataset.mc_control_blocks[control_block_expected["name"]],
                input_dataset.mc_market_areas,
            )
            assert max_tso_power_bought == pytest.approx(
                control_block_expected["max_tso_power_bought"][time_index], rel=1e-9
            )
            assert max_tso_power_sold == pytest.approx(
                control_block_expected["max_tso_power_sold"][time_index], rel=1e-9
            )


def compare_market_borders(market_borders_expected, input_dataset):
    for market_border_expected in market_borders_expected.values():
        mc_market_border = input_dataset.mc_market_borders[market_border_expected["name"]]
        assert mc_market_border.border.loss_factor == pytest.approx(
            float(market_border_expected["loss_factor"]), rel=1e-9
        )
        assert mc_market_border.time_resolution == pytest.approx(
            float(market_border_expected["time_resolution"]), rel=1e-9
        )
        assert mc_market_border.border.uphill_market_area.name == market_border_expected["upstream_market"]
        assert mc_market_border.border.downhill_market_area.name == market_border_expected["downstream_market"]
        assert compare_timeseries_to_dict(mc_market_border.max_flow, market_border_expected["max_flow"])
        assert compare_timeseries_to_dict(mc_market_border.min_flow, market_border_expected["min_flow"])


def compare_market_data(market_data_expected, input_dataset):
    assert market_data_expected["coupling_groups"] == len(input_dataset.mc_order_couplings)
    assert market_data_expected["market_borders"] == len(input_dataset.mc_market_borders)
    assert not set(market_data_expected["control_blocks"]).difference(set(input_dataset.mc_control_blocks))


def compare_orders_couplings(order_couplings_expected, order_couplings_dict):
    for name, order_coupling_expected in order_couplings_expected.items():
        # Sometimes there is an _ at the end after with_price
        if to_snake_case(name) not in order_couplings_dict:
            name = name[:-1]
        order_coupling = order_couplings_dict[to_snake_case(name)]
        assert to_snake_case(order_coupling.name) == to_snake_case(name)
        assert order_coupling.coupling_type.value == order_coupling_expected["coupling_type"]
        expected_complement_energy = float(order_coupling_expected["complement_energy"])
        # If there are no value we are None instead of default value 0.0
        if expected_complement_energy:
            assert order_coupling.complement_energy == pytest.approx(expected_complement_energy, rel=1e-9)
        else:
            assert order_coupling.complement_energy is None
        expected_complement_direction = order_coupling_expected["complement_direction"]
        # Sometimes, there is a nan
        if isinstance(expected_complement_direction, float) and math.isnan(expected_complement_direction):
            assert order_coupling.complement_direction is None
        else:
            assert order_coupling.complement_direction.value == expected_complement_direction
        # Expected doesn't contain name so we compare size
        nb_orders = len(order_coupling_expected["orders_info"])
        assert len(order_coupling.orders) == nb_orders


def compare_timeseries_to_dict(timeseries: Timeseries, _dict: dict[str, float]):
    for time, value in _dict.items():
        time_formated = pendulum.from_format(time, "DD/MM/YYYY HH:mm:ss")
        if abs(timeseries.get_value(time_formated) - value) > 1e-9:
            return False
    return True


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
def test_input(dataset_name):
    path = Path("C:/Users/aboutet/Documents/atlas 2/ATLAS/data/market_clearing_prometheus/") / dataset_name
    parameters_path = path / "parameters.yml"
    dataset_path = path / "atlas-dataset"
    pkl_path = path / "raw_data.pkl"
    expected_data_path = path / "market_data_export"

    mc_module = MarketClearingModule()
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

    parameters = mc_module.import_parameters(parameters_path)

    input_dataset = mc_module.import_data(raw_data, parameters)

    (
        coupling_groups_expected,
        market_areas_expected,
        control_blocks_expected,
        market_borders_expected,
        market_data_expected,
        critical_branches_data,
    ) = read_expected_data(expected_data_path)
    compare_orders_couplings(coupling_groups_expected, input_dataset.mc_order_couplings)
    compare_market_area(market_areas_expected, input_dataset)
    compare_control_block(control_blocks_expected, input_dataset)
    compare_market_borders(market_borders_expected, input_dataset)
    compare_market_data(market_data_expected, input_dataset)
