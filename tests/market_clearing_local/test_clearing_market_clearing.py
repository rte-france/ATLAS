"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
import os
import pickle
from collections import OrderedDict

import pandas as pd
import pytest

import inspect
import atlas.modules.market_clearing.market_clearing_constants as mc_constants


from atlas import InputLoader
from atlas.io_utils.utils import to_snake_case
from atlas.modules.market_clearing.marker_clearing_module import MarketClearingModule
from atlas.modules.market_clearing.phases.clearing import Clearing
from atlas.solver.solver_helper import SolverHelper
from tests.market_clearing_local.test_market_data_market_clearing import read_expected_data



def retrieve_clearing_lp(path):
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


def map_args(pattern: str, encoded_str: str) -> list[str, ...]:
    args_map = {}

    i = j = 0
    while i < len(pattern) and j < len(encoded_str):
        if pattern[i] == ";":
            # lire le numéro entre ';'
            i += 1
            start = i
            while i < len(pattern) and pattern[i] != ";":
                i += 1
            index_str = pattern[start:i]
            if not index_str.isdigit():
                raise ValueError(f"Invalid slot '{index_str}' in pattern")
            index = int(index_str)
            i += 1  # sauter le ';' de fin

            # trouver la prochaine partie fixe après ce slot
            k = i
            while k < len(pattern) and pattern[k] != ";":
                k += 1
            fixed = pattern[i:k]

            if fixed:
                pos = encoded_str.find(fixed, j)
                if pos == -1:
                    raise ValueError(f"Motif '{fixed}' introuvable dans '{encoded_str}'")
                val = encoded_str[j:pos]
                j = pos
            else:
                val = encoded_str[j:]
                j = len(encoded_str)

            args_map[index] = val
        else:
            # avancer dans les parties fixes
            if j < len(encoded_str) and encoded_str[j] == pattern[i]:
                j += 1
            i += 1

    return [args_map[i] for i in sorted(args_map.keys())]


def find_func(name, func_with_start, coupling_groups_expected, market_areas_expected, market_borders_expected, critical_branches_expected):
    fun_associated = None
    for func_start in func_with_start:
        if func_start in name and func_start[:2] == name[:2]:
            fun_associated = func_start
            break
    arguments = map_args(func_with_start[fun_associated][2], name)
    market_area = None
    if "market_area_name" in func_with_start[fun_associated][1]:
        index = func_with_start[fun_associated][1].index("market_area_name")
        market_area = arguments[index]
        market_areas = [key for key, value in market_areas_expected.items() if value["id"] == f"{arguments[index]}"]
        if len(market_areas) == 1:
            market_area = market_areas[0]
        arguments[index] = to_snake_case(market_area)
    order_coupling = None
    if "order_coupling_name" in func_with_start[fun_associated][1]:
        index = func_with_start[fun_associated][1].index("order_coupling_name")
        order_coupling = [key for key, value in coupling_groups_expected.items() if str(value["id"]) == f"{arguments[index]}"][0]
        arguments[index] = to_snake_case(order_coupling)
    if "order_name" in func_with_start[fun_associated][1]:
        index = func_with_start[fun_associated][1].index("order_name")
        if order_coupling:
            market_area, order_id = coupling_groups_expected[order_coupling]["orders_info"][int(arguments[index])]
            arguments[index] = order_id
        if market_area:
            arguments[index] = to_snake_case([key for key, value in market_areas_expected[market_area]["orders"].items() if
                                  str(value["id"]) == f"{arguments[index]}"][0])
    if "border_name" in func_with_start[fun_associated][1]:
        index = func_with_start[fun_associated][1].index("border_name")
        border_name = [key for key, value in market_borders_expected.items() if str(value["id"]) == f"{arguments[index]}"][0]
        arguments[index] = to_snake_case(border_name)
    if "branch_name" in func_with_start[fun_associated][1]:
        index = func_with_start[fun_associated][1].index("branch_name")
        branch_name = [key for key, value in critical_branches_expected.items() if str(value["id"]) == f"{arguments[index]}"][0]
        arguments[index] = to_snake_case(branch_name)
    return fun_associated, arguments

def transform_clearing_prometheus_lp(prometheus_lp_path, lp_mapping_path, expected_data_path):
    (coupling_groups_expected, market_areas_expected, _, market_borders_expected,
     _, critical_branches_expected) = read_expected_data(expected_data_path)
    mapping_df = pd.read_csv(lp_mapping_path, delimiter=";")[["New Name", "Original Name"]]
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
    naming_functions = inspect.getmembers(mc_constants, inspect.isfunction)

    func_with_start = {}
    # get func parameter
    for _, func in naming_functions:
        parameters = list(inspect.signature(func).parameters)
        name = func(*[f";{i};" for i in range(len(parameters))])
        start = name[:name.find(";")]
        func_with_start[start] = (func, parameters, name)

    variable_dict = {}
    for var_name in new_prometheus_variables:
        fun_associated, arguments = find_func(var_name, func_with_start, coupling_groups_expected, market_areas_expected, market_borders_expected)
        variable_dict[var_name] = func_with_start[fun_associated][0](*arguments)
    prometheus_variables = {
        variable_dict[key]: value for key, value in new_prometheus_variables.items()
    }

    binaries_dict = {}
    prometheus_binaries = []
    for var_name in new_prometheus_binaries:
        fun_associated, arguments = find_func(var_name, func_with_start, coupling_groups_expected, market_areas_expected, market_borders_expected, critical_branches_expected)
        prometheus_binaries.append(func_with_start[fun_associated][0](*arguments))
        binaries_dict[var_name] = func_with_start[fun_associated][0](*arguments)

    prometheus_constraints = {}
    for c_name in new_prometheus_constraints:
        fun_associated, arguments = find_func(c_name, func_with_start, coupling_groups_expected, market_areas_expected, market_borders_expected, critical_branches_expected)
        constraints = {}
        for key, value in new_prometheus_constraints[c_name].items():
            if key in variable_dict:
                constraints[variable_dict[key]] = value
            elif key in binaries_dict:
                constraints[binaries_dict[key]] = value
            else:
                constraints[key] = value
        prometheus_constraints[func_with_start[fun_associated][0](*arguments)] = constraints

    prometheus_objectives = {
        variable_dict[var_name]: new_prometheus_objectives[var_name] for var_name in new_prometheus_objectives
        if "Constant" != var_name
    }

    return {
        "constraints": OrderedDict(prometheus_constraints),
        "variables": OrderedDict(prometheus_variables),
        "objectives": OrderedDict(prometheus_objectives),
        "binaries": prometheus_binaries,
    }



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
    # le lp prometheus doit être modifié dans une fonction à part
    path = os.path.join("data", "market_clearing_prometheus", dataset_name)
    expected_lp_path = os.path.join(path, "optimization_data", "clearing_phase.lp")
    lp_mapping_path = os.path.join(path, "optimization_data", "clearing_phase.lp_correspondance.csv")

    market_data_export_path = os.path.join(path, "market_data_export")

    legacy_dict = transform_clearing_prometheus_lp(expected_lp_path, lp_mapping_path, market_data_export_path)
    legacy_solver = SolverHelper.model_from_dict_test(legacy_dict, "XPRESS")
    legacy_solver.Solve()
    s_legacy = legacy_solver.ExportModelAsLpFormat(False)
    with open(os.path.join(path, "test_legacy.lp"), "w") as f:
        f.write(s_legacy)

    clearing_lp_path = retrieve_clearing_lp(path)
    atlas_objectives, atlas_constraints, atlas_variables, atlas_binaries = SolverHelper.read_lp_ortools(clearing_lp_path)
    atlas_dict = {
        "constraints": atlas_constraints,
        "variables": atlas_variables,
        "objectives": atlas_objectives,
        "binaries": atlas_binaries,
    }
    atlas_solver = SolverHelper.model_from_dict_test(atlas_dict, "XPRESS")
    atlas_solver.Solve()
    s_atlas = atlas_solver.ExportModelAsLpFormat(False)
    with open(os.path.join(path, "test_atlas.lp"), "w") as f:
        f.write(s_atlas)

    SolverHelper.add_binaries_to_lp_problems_variables(atlas_dict)
    SolverHelper.add_binaries_to_lp_problems_variables(legacy_dict)
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
    add_constraint = []
    remove_constraint = []
    for constraint in diff_constraint:
        if "add" == constraint[0]:
            add_constraint.append(constraint[2])
        if "remove" == constraint[0]:
            remove_constraint.append(constraint[2])
    if (len(remove_constraint) == len(add_constraint) and
        id_ratio_constraint_atlas == id_ratio_constraint_prometheus and
        id_volume_constraint_atlas == id_volume_constraint_prometheus and
        id_parent_child_constraint_atlas == id_parent_child_constraint_prometheus and
        id_ratio_constraint_atlas + id_volume_constraint_atlas + id_parent_child_constraint_atlas == len(add_constraint)):
        print("constraint ok !!!!")
    else:
        print("constraint not ok")
        assert False
    print("diff_variables")
    print(diff_variables)
    print("diff_objectives")
    print(diff_objectives)
    print("diff_constraint")
    print(diff_constraint)
    assert len(diff_objectives) == 0
    assert len(diff_variables) == 0
