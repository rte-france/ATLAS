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
from atlas.modules.market_clearing.marker_clearing_module import MarketClearingModule
from atlas.modules.market_clearing.phases.pricing import Pricing
from atlas.solver.solver_helper import SolverHelper
from tests.market_clearing_local.market_clearing_test_utils import transform_clearing_prometheus_lp


def retrieve_local_balances_from_json(local_balances_path: str) -> dict[tuple[str, int], float]:
    local_balances = {}
    with open(local_balances_path, mode="r") as f:
        local_balances_list = json.load(f)
        for ma, t, val in local_balances_list:
            local_balances[ma, t] = val
    return local_balances


def retrieve_saturated_critical_branches_from_json(local_balances_path: str) -> dict[tuple[str, int], float]:
    saturated_critical_branches = {}
    with open(local_balances_path, mode="r") as f:
        saturated_critical_branches_list = json.load(f)
        for critical_branch, time_index, val in saturated_critical_branches_list:
            saturated_critical_branches[critical_branch, time_index] = val
    return saturated_critical_branches


def retrieve_border_exchanges_from_json(local_balances_path: str) -> dict[tuple[str, int], float]:
    border_exchanges = {}
    with open(local_balances_path, mode="r") as f:
        border_exchanges_list = json.load(f)
        for border_name, time_index, val in border_exchanges_list:
            border_exchanges[border_name, time_index] = val
    return border_exchanges


def retrieve_pricing_lp(path):
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

    clearing_local_balances = retrieve_local_balances_from_json(os.path.join(path, "optimization_data",
                                                                             "clearing_local_balances.json"))
    clearing_saturated_critical_branches = retrieve_local_balances_from_json(
        os.path.join(path, "optimization_data", "clearing_saturated_critical_branches.json"))
    exchange_fixing_border_exchanges = retrieve_border_exchanges_from_json(os.path.join(path, "optimization_data",
                                                                             "clearing_border_exchanges.json"))
    clearing_accepted_powers = retrieve_border_exchanges_from_json(os.path.join(path, "optimization_data",
                                                                             "clearing_accepted_powers.json"))

    pricing = Pricing(input_dataset, parameters, clearing_saturated_critical_branches,
                      exchange_fixing_border_exchanges, clearing_local_balances, clearing_accepted_powers)
    pricing.run()

    return "pricing_1_model.lp", "pricing_2_model.lp", "pricing_3_model.lp"


# @pytest.mark.skip(reason="No data available")
@pytest.mark.parametrize(
    "dataset_name",
    [
        #"MarketClearing input v1.3 FB_1",
        #"MarketClearing input v1.3 FB_2",
        "MarketClearing input v1.3 ATC_1",
        "MarketClearing input v1.3 ATC_2"
    ]
)
def test_compare_lp(dataset_name):
    path = os.path.join("data", "market_clearing_prometheus", dataset_name)
    first_expected_lp_path = os.path.join(path, "optimization_data", "first_pricing_phase.lp")
    first_lp_mapping_path = os.path.join(path, "optimization_data", "first_pricing_phase.lp_correspondance.csv")
    pricing_lp_path = retrieve_pricing_lp(path)

    market_data_export_path = os.path.join(path, "market_data_export")
    legacy_dict = transform_clearing_prometheus_lp(first_expected_lp_path, first_lp_mapping_path, market_data_export_path)
    atlas_objectives, atlas_constraints, atlas_variables, atlas_binaries = SolverHelper.read_lp_ortools(
        pricing_lp_path)
    atlas_dict = {
        "constraints": atlas_constraints,
        "variables": atlas_variables,
        "objectives": atlas_objectives,
        "binaries": atlas_binaries,
    }
    SolverHelper.add_binaries_to_lp_problems_variables(atlas_dict)
    SolverHelper.add_binaries_to_lp_problems_variables(legacy_dict)
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
