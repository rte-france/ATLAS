"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
import json
import os
import pickle

import pytest

from atlas import InputLoader
from atlas.io_utils.utils import to_snake_case
from atlas.modules.market_clearing.marker_clearing_module import MarketClearingModule
from atlas.modules.market_clearing.phases.pricing import Pricing
from atlas.solver.solver_helper import SolverHelper
from tests.market_clearing_local.market_clearing_test_utils import transform_clearing_prometheus_lp
from tests.market_clearing_local.test_market_data_market_clearing import read_expected_data


def retrieve_local_balances_from_json(optim_variable_path: str, market_area_mapping: dict[str, str]) -> dict[tuple[str, int], float]:
    with (open(optim_variable_path, "r") as f):
        optim_variables = json.load(f)
        local_balances = {}
        for time_index, balances in enumerate(optim_variables["local_balances"]):
            for area_id, _dict in enumerate(balances):
                local_balances[market_area_mapping[str(area_id)], time_index] = _dict["VarValue"]
        return local_balances


def retrieve_saturated_critical_branches_from_json(other_outputs_path: str, critical_branch_mapping: dict[str, str]) -> dict[tuple[str, int], float]:
    if not critical_branch_mapping:
        return {}
    with (open(other_outputs_path, "r") as f):
        other_outputs = json.load(f)
        critical_branches = {}
        for saturated_time_index in other_outputs["saturated_cb"]:
            for cb_id, time_index, value in saturated_time_index:
                critical_branches[critical_branch_mapping[str(cb_id)], time_index] = value
        return critical_branches


def retrieve_border_exchanges_from_json(optim_variable_path: str, border_mapping: dict[str, str]) -> dict[tuple[str, int], float]:
    with (open(optim_variable_path, "r") as f):
        optim_variables = json.load(f)
        borders = {}
        for time_index, balances in enumerate(optim_variables["border_exchanges"]):
            for border_id, _dict in enumerate(balances):
                borders[border_mapping[str(border_id)], time_index] = _dict["VarValue"]
        return borders

def retrieve_accepted_powers_from_json(optim_variable_path: str, market_area_mapping: dict[str, str], orders_mapping: dict[tuple[str, str], str]) -> dict[tuple[str, str], float]:
    with (open(optim_variable_path, "r") as f):
        optim_variables = json.load(f)
        accepted_powers = {}
        for area_id, balances in enumerate(optim_variables["accepted_powers"]):
            for order_id, _dict in enumerate(balances):
                accepted_powers[market_area_mapping[str(area_id)], orders_mapping[str(area_id), str(order_id)]] = _dict["VarValue"]
        return accepted_powers

def retrieve_orders_mapping(market_area) -> dict[tuple[str, str], str]:
    order_mapping = {}
    for market_area_dict in market_area.values():
        for order_name, order_dict in market_area_dict["orders"].items():
            order_mapping[str(market_area_dict["id"]), str(order_dict["id"])] = to_snake_case(order_name)
    return order_mapping


def retrieve_pricing_lp(path, clearing_local_balances, clearing_saturated_critical_branches,
                        exchange_fixing_border_exchanges, clearing_accepted_powers, path_only=False):
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

        pricing = Pricing(input_dataset, parameters, clearing_saturated_critical_branches,
                          exchange_fixing_border_exchanges, clearing_local_balances, clearing_accepted_powers)
        pricing.run()

    with open(os.path.join(path, "optimization_data", "pricing_market_prices.json"), "w") as f:
        json.dump([[market_area_name, time_index, val]
                   for (market_area_name, time_index), val in pricing.retrieve_market_prices().items()], f)

    return "pricing_1_model.lp", "pricing_2_model.lp", "pricing_3_model.lp"


# @pytest.mark.skip(reason="No data available")
@pytest.mark.parametrize(
    "dataset_name",
    [
        #"MarketClearing input v1.3 FB_1",
        #"MarketClearing input v1.3 FB_2",
        #"MarketClearing input v1.3 ATC_1",
        "MarketClearing input v1.3 ATC_2"
    ]
)
def test_compare_lp(dataset_name):
    path = os.path.join("data", "market_clearing_prometheus", dataset_name)
    clearing_optim_variables_path = os.path.join(path, "optimization_data", "clearing", "optim_variables.json")
    clearing_other_outputs_path = os.path.join(path, "optimization_data", "clearing", "other_outputs.json")
    exchange_optim_variables_path = os.path.join(path, "optimization_data", "exchanges_fixing", "optim_variables.json")

    first_expected_lp_path = os.path.join(path, "optimization_data", "first_pricing_phase.lp")
    first_lp_mapping_path = os.path.join(path, "optimization_data", "first_pricing_phase.lp_correspondance.csv")
    second_expected_lp_path = os.path.join(path, "optimization_data", "second_pricing_phase.lp")
    second_lp_mapping_path = os.path.join(path, "optimization_data", "second_pricing_phase.lp_correspondance.csv")
    third_expected_lp_path = os.path.join(path, "optimization_data", "third_pricing_phase.lp")
    third_lp_mapping_path = os.path.join(path, "optimization_data", "third_pricing_phase.lp_correspondance.csv")

    market_data_export_path = os.path.join(path, "market_data_export")
    expected_data = read_expected_data(market_data_export_path)
    legacy_1_dict = transform_clearing_prometheus_lp(first_expected_lp_path, first_lp_mapping_path, expected_data)
    legacy_1_solver = SolverHelper.model_from_dict_mc(legacy_1_dict, "XPRESS")
    legacy_1_solver.Solve()
    s_legacy_1 = legacy_1_solver.ExportModelAsLpFormat(False)
    with open(os.path.join(path, "pricing_1_test_legacy.lp"), "w") as f:
        f.write(s_legacy_1)

    if os.path.exists(second_expected_lp_path):
        legacy_2_dict = transform_clearing_prometheus_lp(second_expected_lp_path, second_lp_mapping_path, expected_data)
        legacy_2_solver = SolverHelper.model_from_dict_mc(legacy_2_dict, "XPRESS")
        legacy_2_solver.Solve()
        s_legacy_2 = legacy_2_solver.ExportModelAsLpFormat(False)
        with open(os.path.join(path, "pricing_2_test_legacy.lp"), "w") as f:
            f.write(s_legacy_2)

    if os.path.exists(third_lp_mapping_path):
        legacy_3_dict = transform_clearing_prometheus_lp(third_expected_lp_path, third_lp_mapping_path, expected_data)
        legacy_3_solver = SolverHelper.model_from_dict_mc(legacy_3_dict, "XPRESS")
        legacy_3_solver.Solve()
        s_legacy_3 = legacy_3_solver.ExportModelAsLpFormat(False)
        with open(os.path.join(path, "pricing_3_test_legacy.lp"), "w") as f:
            f.write(s_legacy_3)
    _, market_areas, _, borders, _, critical_branches = expected_data
    market_area_mapping = {value["id"]: key.lower() for key, value in market_areas.items()}
    orders_mapping = retrieve_orders_mapping(market_areas)
    if critical_branches:
        critical_branches_mapping = {value["id"]: key.lower() for key, value in critical_branches.items()}
    else:
        critical_branches_mapping = {}
    borders_mapping = {value["id"]: key.lower() for key, value in borders.items()}
    clearing_local_balances = retrieve_local_balances_from_json(clearing_optim_variables_path, market_area_mapping)
    clearing_saturated_critical_branches = retrieve_saturated_critical_branches_from_json(clearing_other_outputs_path,
                                                                                          critical_branches_mapping)
    exchange_fixing_border_exchanges = retrieve_border_exchanges_from_json(exchange_optim_variables_path, borders_mapping)
    clearing_accepted_powers = retrieve_accepted_powers_from_json(clearing_optim_variables_path, market_area_mapping, orders_mapping)
    pricing_1_lp_path, pricing_2_lp_path, pricing_3_lp_path = retrieve_pricing_lp(
        path, clearing_local_balances, clearing_saturated_critical_branches, exchange_fixing_border_exchanges,
        clearing_accepted_powers, False)
    atlas_1_objectives, atlas_1_constraints, atlas_1_variables, atlas_1_binaries = SolverHelper.read_lp_ortools(
        pricing_1_lp_path)
    atlas_1_dict = {
        "constraints": {to_snake_case(key): value for key, value in atlas_1_constraints.items()},
        "variables": atlas_1_variables,
        "objectives": atlas_1_objectives,
        "binaries": atlas_1_binaries,
    }
    atlas_1_solver = SolverHelper.model_from_dict_mc(atlas_1_dict, "XPRESS")
    atlas_1_solver.Solve()
    s_atlas_1 = atlas_1_solver.ExportModelAsLpFormat(False)
    with open(os.path.join(path, "pricing_1_test_atlas.lp"), "w") as f:
        f.write(s_atlas_1)

    if os.path.exists(pricing_2_lp_path):
        atlas_2_objectives, atlas_2_constraints, atlas_2_variables, atlas_2_binaries = SolverHelper.read_lp_ortools(
            pricing_2_lp_path)
        atlas_2_dict = {
            "constraints": {to_snake_case(key): value for key, value in atlas_2_constraints.items()},
            "variables": atlas_2_variables,
            "objectives": atlas_2_objectives,
            "binaries": atlas_2_binaries,
        }
        atlas_2_solver = SolverHelper.model_from_dict_mc(atlas_2_dict, "XPRESS")
        atlas_2_solver.Solve()
        s_atlas_2 = atlas_2_solver.ExportModelAsLpFormat(False)
        with open(os.path.join(path, "pricing_2_test_atlas.lp"), "w") as f:
            f.write(s_atlas_2)

    if os.path.exists(pricing_3_lp_path):
        atlas_3_objectives, atlas_3_constraints, atlas_3_variables, atlas_3_binaries = SolverHelper.read_lp_ortools(
            pricing_3_lp_path)
        atlas_3_dict = {
            "constraints": {to_snake_case(key): value for key, value in atlas_3_constraints.items()},
            "variables": atlas_3_variables,
            "objectives": atlas_3_objectives,
            "binaries": atlas_3_binaries,
        }
        atlas_3_solver = SolverHelper.model_from_dict_mc(atlas_3_dict, "XPRESS")
        atlas_3_solver.Solve()
        s_atlas_3 = atlas_3_solver.ExportModelAsLpFormat(False)
        with open(os.path.join(path, "pricing_3_test_atlas.lp"), "w") as f:
            f.write(s_atlas_3)


    SolverHelper.add_binaries_to_lp_problems_variables(legacy_dict)
    SolverHelper.add_binaries_to_lp_problems_variables(atlas_dict)

    diff_constraint, diff_variables, diff_objectives = SolverHelper.compare_lp_problems(atlas_dict, legacy_dict)
    # constraint ok
    add_constraint = []
    remove_constraint = []
    for constraint in diff_constraint:
        if "add" == constraint[0]:
            add_constraint.append(constraint[2])
        if "remove" == constraint[0]:
            remove_constraint.append(constraint[2])
    if len(remove_constraint) == len(add_constraint):
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
