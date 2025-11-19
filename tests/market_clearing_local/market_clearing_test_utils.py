import inspect
import json
import os
from collections import OrderedDict

import pandas as pd

import atlas.modules.market_clearing.market_clearing_constants as mc_constants
from atlas.io_utils.utils import to_snake_case
from atlas.solver.solver_helper import SolverHelper


def map_args(pattern: str, encoded_str: str) -> list[str]:
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


def find_func(name, func_with_start, coupling_groups_expected, market_areas_expected, market_borders_expected,
              critical_branches_expected):
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
        order_coupling = \
        [key for key, value in coupling_groups_expected.items() if str(value["id"]) == f"{arguments[index]}"][0]
        arguments[index] = to_snake_case(order_coupling)
    if "order_name" in func_with_start[fun_associated][1]:
        index = func_with_start[fun_associated][1].index("order_name")
        if order_coupling:
            market_area, order_id = coupling_groups_expected[order_coupling]["orders_info"][int(arguments[index])]
            arguments[index] = order_id
        if market_area:
            arguments[index] = to_snake_case(
                [key for key, value in market_areas_expected[market_area]["orders"].items() if
                 str(value["id"]) == f"{arguments[index]}"][0])
    if "border_name" in func_with_start[fun_associated][1]:
        index = func_with_start[fun_associated][1].index("border_name")
        border_name = \
        [key for key, value in market_borders_expected.items() if str(value["id"]) == f"{arguments[index]}"][0]
        arguments[index] = to_snake_case(border_name)
    if "branch_name" in func_with_start[fun_associated][1]:
        index = func_with_start[fun_associated][1].index("branch_name")
        branch_name = \
        [key for key, value in critical_branches_expected.items() if str(value["id"]) == f"{arguments[index]}"][0]
        arguments[index] = to_snake_case(branch_name)
    return fun_associated, arguments


def transform_clearing_prometheus_lp(prometheus_lp_path, lp_mapping_path, expected_data):
    (coupling_groups_expected, market_areas_expected, _, market_borders_expected,
     _, critical_branches_expected) = expected_data
    mapping_df = pd.read_csv(lp_mapping_path, delimiter=";")[["New Name", "Original Name"]]
    prometheus_objectives, prometheus_constraints, prometheus_variables, prometheus_binaries = SolverHelper.read_lp_legacy(
        prometheus_lp_path)
    variable_mapping = mapping_df[mapping_df["New Name"].str.contains("V_")]
    constraint_mapping = mapping_df[mapping_df["New Name"].str.contains("C_")]
    new_prometheus_binaries = [variable_mapping[variable_mapping["New Name"] == v_name]["Original Name"].values[0] for
                               v_name in prometheus_binaries]
    new_prometheus_constraints = {}
    new_prometheus_variables = {}
    new_prometheus_objectives = {}
    for v_name in prometheus_variables:
        new_name = variable_mapping[variable_mapping["New Name"] == v_name]["Original Name"].values[0]
        new_prometheus_variables[new_name] = prometheus_variables[v_name]
    for v_name in prometheus_objectives:
        if v_name == "Constant":
            new_prometheus_objectives[v_name] = prometheus_objectives[v_name]
            continue
        new_name = variable_mapping[variable_mapping["New Name"] == v_name]["Original Name"].values[0]
        if new_name not in new_prometheus_variables:
            new_prometheus_variables[new_name] = [-float("inf"), float("inf")]
        new_prometheus_objectives[new_name] = prometheus_objectives[v_name]
    for c_name, _dict in prometheus_constraints.items():
        c_new_name = constraint_mapping[constraint_mapping["New Name"] == c_name]["Original Name"].values[0]
        new_prometheus_constraints[c_new_name] = {}
        for v_name in _dict:
            if v_name in ["UB", "LB"]:
                new_prometheus_constraints[c_new_name][v_name] = _dict[v_name]
                continue
            new_name = variable_mapping[variable_mapping["New Name"] == v_name]["Original Name"].values[0]
            if new_name not in new_prometheus_variables:
                new_prometheus_variables[new_name] = [-float("inf"), float("inf")]
            new_prometheus_constraints[c_new_name][new_name] = prometheus_constraints[c_name][v_name]
    naming_functions = inspect.getmembers(mc_constants, inspect.isfunction)

    func_with_start = {}
    # get func parameter
    for _, func in naming_functions:
        parameters = list(inspect.signature(func).parameters)
        name = func(*[f";{i};" for i in range(len(parameters))])
        start = name[:name.find(";")]
        func_with_start[start] = (func, parameters, name)

    mapping = {}
    variable_dict = {}
    for var_name in new_prometheus_variables:
        fun_associated, arguments = find_func(var_name, func_with_start, coupling_groups_expected,
                                              market_areas_expected, market_borders_expected,
                                              critical_branches_expected)
        variable_dict[var_name] = func_with_start[fun_associated][0](*arguments)
        mapping[variable_dict[var_name]] = var_name
    prometheus_variables = {
        variable_dict[key]: value for key, value in new_prometheus_variables.items()
    }

    binaries_dict = {}
    prometheus_binaries = []
    for var_name in new_prometheus_binaries:
        fun_associated, arguments = find_func(var_name, func_with_start, coupling_groups_expected,
                                              market_areas_expected, market_borders_expected,
                                              critical_branches_expected)
        prometheus_binaries.append(func_with_start[fun_associated][0](*arguments))
        binaries_dict[var_name] = func_with_start[fun_associated][0](*arguments)
        mapping[binaries_dict[var_name]] = var_name

    prometheus_constraints = {}
    for c_name in new_prometheus_constraints:
        # manage price group bound create as constraint in prometheus
        if "_bound_PG" in c_name or "part_price_group_" in c_name or "_part_price_diff_groups_" in c_name:
            continue
        fun_associated, arguments = find_func(c_name, func_with_start, coupling_groups_expected, market_areas_expected,
                                              market_borders_expected, critical_branches_expected)
        constraint_name = to_snake_case(func_with_start[fun_associated][0](*arguments))
        mapping[constraint_name] = c_name
        constraints = {}
        for key, value in new_prometheus_constraints[c_name].items():
            if key in variable_dict:
                constraints[variable_dict[key]] = value
            elif key in binaries_dict:
                constraints[binaries_dict[key]] = value
            else:
                constraints[key] = value
        prometheus_constraints[constraint_name] = constraints

    prometheus_objectives = {
        variable_dict[var_name]: new_prometheus_objectives[var_name] for var_name in new_prometheus_objectives
        if "Constant" != var_name
    }
    mapping_path, _ = os.path.splitext(prometheus_lp_path)
    with open(mapping_path + "_mapping_json", "w") as f:
        json.dump(mapping, f)

    return {
        "constraints": OrderedDict(prometheus_constraints),
        "variables": OrderedDict(prometheus_variables),
        "objectives": OrderedDict(prometheus_objectives),
        "binaries": prometheus_binaries,
    }
