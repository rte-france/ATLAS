"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
import json
import os
import pickle
import pandas as pd
import pytest
import copy

from atlas import InputLoader
from atlas.io_utils.utils import to_snake_case
from atlas.modules.market_clearing.marker_clearing_module import MarketClearingModule
from atlas.modules.market_clearing.phases.clearing import Clearing
from atlas.solver.solver_helper import SolverHelper

from atlas.modules.market_clearing.market_clearing_constants import lp_obj


def compare_lp(atlas_lp_path, prometheus_lp_path, lp_mapping_path, other_mapping_path=None):
    mapping_df = pd.read_csv(lp_mapping_path, delimiter=";")[["New Name", "Original Name"]]

    atlas_objectives, atlas_constraints, atlas_variables, atlas_binaries = SolverHelper.read_lp_ortools(atlas_lp_path)

    prometheus_objectives, prometheus_constraints, prometheus_variables, prometheus_binaries = SolverHelper.read_lp_legacy(prometheus_lp_path)
    variable_mapping = mapping_df[mapping_df["New Name"].str.contains("V_")]
    constraint_mapping = mapping_df[mapping_df["New Name"].str.contains("C_")]
    new_prometheus_binaries = [variable_mapping[variable_mapping["New Name"] == v_name]["Original Name"].values[0] for v_name in prometheus_binaries]
    new_prometheus_constraints = {}
    new_prometheus_variables = {}
    new_prometheus_objectives = {}
    for v_name in prometheus_variables:
        new_name = variable_mapping[variable_mapping["New Name"] == v_name]["Original Name"].values
        new_prometheus_variables[new_name[0]] = prometheus_variables[v_name]
    for v_name in prometheus_objectives:
        if v_name == "Constant":
            new_prometheus_objectives[v_name] = prometheus_objectives[v_name]
            continue
        new_name = variable_mapping[variable_mapping["New Name"] == v_name]["Original Name"].values
        new_prometheus_objectives[new_name[0]] = prometheus_objectives[v_name]
    for c_name, _dict in prometheus_constraints.items():
        c_new_name = constraint_mapping[constraint_mapping["New Name"] == c_name]["Original Name"].values
        new_prometheus_constraints[c_new_name[0]] = {}
        for v_name in _dict:
            if v_name in ["UB", "LB"]:
                new_prometheus_constraints[c_new_name[0]][v_name] = _dict[v_name]
                continue
            new_name = variable_mapping[variable_mapping["New Name"] == v_name]["Original Name"].values
            new_prometheus_constraints[c_new_name[0]][new_name[0]] = prometheus_constraints[c_name][v_name]

    if other_mapping_path:
        other_mapping = pd.read_csv(other_mapping_path, delimiter=";")[["Class", "InstanceName", "ID"]]

        mapping = {}
        lp_obj_c = sorted(copy.deepcopy(lp_obj), key=lambda x: len(x["name"]), reverse=True)
        for _dict in lp_obj_c:
            kwargs = {key: item for key, item in _dict.items() if key not in ["name", "func"]}
            key = "border_name"
            if key in _dict:
                kwargs[key] = other_mapping[other_mapping["Class"] == "MarketBorder"][other_mapping["InstanceName"].apply(to_snake_case) == _dict[key]]["ID"].values[0]
            key = "market_area_name"
            if key in _dict and _dict["func"].__name__ not in ["accepted_power_variable_name", "order_status_variable_name"]:
                kwargs[key] = other_mapping[other_mapping["Class"] == "MarketArea"][other_mapping["InstanceName"].apply(to_snake_case) == _dict[key]]["ID"].values[0]
            key = "order_coupling_name"
            if key in _dict:
                kwargs[key] = other_mapping[other_mapping["Class"] == "OrderCoupling"][other_mapping["InstanceName"].apply(to_snake_case) == _dict[key]]["ID"].values[0]
            key = "order_name"
            if key in _dict:
                kwargs[key] = other_mapping[other_mapping["Class"] == "Order"][other_mapping["InstanceName"].apply(to_snake_case) == _dict[key]]["ID"].values[0]
            new_name = _dict["func"](**kwargs)
            mapping[_dict["name"]] = new_name

        new_atlas_binaries = []
        new_atlas_constraints = {}
        new_atlas_variables = {}
        new_atlas_objectives = {}
        for v_name in atlas_variables:
            if v_name == "Constant":
                new_atlas_variables[v_name] = atlas_variables[v_name]
                continue
            if v_name not in mapping:
                continue
            new_name = mapping[v_name]
            new_atlas_variables[new_name] = atlas_variables[v_name]
        for v_name in atlas_objectives:
            if v_name == "Constant":
                new_atlas_objectives[v_name] = atlas_objectives[v_name]
                continue
            if v_name not in mapping:
                continue
            new_name = mapping[v_name]
            new_atlas_objectives[new_name] = atlas_objectives[v_name]
        for c_name, _dict in atlas_constraints.items():
            if c_name not in mapping:
                continue
            c_new_name = mapping[c_name]
            new_atlas_constraints[c_new_name] = {}
            for v_name in _dict:
                if v_name in ["UB", "LB"]:
                    new_atlas_constraints[c_new_name][v_name] = _dict[v_name]
                    continue
                if v_name not in mapping:
                    continue
                new_name = mapping[v_name]
                new_atlas_constraints[c_new_name][new_name] = atlas_constraints[c_name][v_name]
        for v_name in atlas_binaries:
            if v_name not in mapping:
                continue
            new_name = mapping[v_name]
            new_atlas_binaries.append(new_name)


    atlas_dict = {
        "constraints": new_atlas_constraints,
        "variables": new_atlas_variables,
        "objectives": new_atlas_objectives,
        "binaries": new_atlas_binaries,
    }
    legacy_dict = {
        "constraints": new_prometheus_constraints,
        "variables": new_prometheus_variables,
        "objectives": new_prometheus_objectives,
        "binaries": new_prometheus_binaries,
    }

    with open("atlas_lp.json", "w") as f:
        json.dump(atlas_dict, f, indent=2, sort_keys=True)
    with open("legacy_lp.json", "w") as f:
        json.dump(legacy_dict, f, indent=2, sort_keys=True)


def retrieve_lp(path):
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

    clearing = Clearing(input_dataset, parameters)
    clearing.run()

    return "clearing_model.lp"

@pytest.mark.skip(reason="No data available")
def test_compare_lp():
    path = "C:/Users/aboutet/Documents/atlas 2/ATLAS/data/market_clearing_prometheus/MarketClearing input v1.3 ATC_1"
    expected_lp_path = os.path.join(path, "optimization_data", "clearing_phase.lp")
    lp_mapping_path = os.path.join(path, "optimization_data", "clearing_phase.lp_correspondance.csv")

    clearing_lp_path = retrieve_lp(path)
    indexes_mapping = os.path.join(path, "market_data_export", "class_indexes.csv")

    compare_lp(clearing_lp_path, expected_lp_path, lp_mapping_path, indexes_mapping)
    with open("atlas_lp.json", "r") as f:
        atlas_dict = json.load(f)
    with open("legacy_lp.json", "r") as f:
        legacy_dict = json.load(f)


    diff_constraint, diff_variables, diff_objectives = SolverHelper.compare_lp_problems(atlas_dict, legacy_dict)
    id_ratio_constraint_atlas = len([c for c in atlas_dict["constraints"] if "Constraint_3_8_1_id_ratio" in c])
    id_ratio_constraint_prometheus = len([c for c in legacy_dict["constraints"] if "Constraint_3_8_1_id_ratio" in c])
    id_volume_constraint_atlas = len([c for c in atlas_dict["constraints"] if "Constraint_3_8_id_volume" in c])
    id_volume_constraint_prometheus = len([c for c in legacy_dict["constraints"] if "Constraint_3_8_id_volume" in c])
    id_parent_child_constraint_atlas = len([c for c in atlas_dict["constraints"] if "Constraint_parent_child" in c])
    id_parent_child_constraint_prometheus = len([c for c in legacy_dict["constraints"] if "Constraint_parent_child" in c])
    print("id_volume atlas/prometheus : ", id_ratio_constraint_atlas, id_ratio_constraint_prometheus)
    print("id_volume atlas/prometheus : ", id_volume_constraint_atlas, id_volume_constraint_prometheus)
    print("id_parent_child atlas/prometheus : ", id_parent_child_constraint_atlas, id_parent_child_constraint_prometheus)
    # constraint ok
    add_constraint = None
    remove_constraint = None
    for constraint in diff_constraint:
        if "add" == constraint[0]:
            add_constraint = constraint[2]
        if "remove" == constraint[0]:
            remove_constraint = constraint[2]
    if (len(remove_constraint) == len(add_constraint) and
        id_ratio_constraint_atlas == id_ratio_constraint_prometheus and
        id_volume_constraint_atlas == id_volume_constraint_prometheus and
        id_parent_child_constraint_atlas == id_parent_child_constraint_prometheus and
        id_ratio_constraint_atlas + id_volume_constraint_atlas + id_parent_child_constraint_atlas == len(add_constraint)):
        print("constraint ok !!!!")
    else:
        print("constraint not ok")
    print("diff_variables")
    print(diff_variables)
    print("diff_objectives")
    print(diff_objectives)
    print("diff_constraint")
    print(diff_constraint)
