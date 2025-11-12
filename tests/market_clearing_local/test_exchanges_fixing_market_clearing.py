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
from atlas.modules.market_clearing.phases.exchanges_fixing import ExchangesFixing
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


def retrieve_exchanges_fixing_lp(path, clearing_local_balances):
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

    exchange_fixing = ExchangesFixing(input_dataset, parameters)
    exchange_fixing.run(clearing_local_balances)

    with open(os.path.join(path, "optimization_data", "clearing_border_exchanges.json"), "w") as f:
        json.dump([[b, time_index, val] for (b, time_index), val in exchange_fixing.retrieve_border_exchanges().items()], f)

    return "exchanges_fixing_model.lp"


# @pytest.mark.skip(reason="No data available")
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
    expected_lp_path = os.path.join(path, "optimization_data", "exchanges_fixing_phase.lp")
    lp_mapping_path = os.path.join(path, "optimization_data", "exchanges_fixing_phase.lp_correspondance.csv")
    clearing_optim_variables_path = os.path.join(path, "optimization_data", "clearing", "optim_variables.json")

    market_data_export_path = os.path.join(path, "market_data_export")
    expected_data = read_expected_data(market_data_export_path)
    legacy_dict = transform_clearing_prometheus_lp(expected_lp_path, lp_mapping_path, expected_data)
    legacy_solver = SolverHelper.model_from_dict_mc(legacy_dict, "XPRESS")
    legacy_solver.Solve()
    s_legacy = legacy_solver.ExportModelAsLpFormat(False)
    with open(os.path.join(path, "exchange_fixing_test_legacy.lp"), "w") as f:
        f.write(s_legacy)

    _, market_area_mapping, _, _, _, _ = expected_data
    market_area_mapping = {value["id"]: key.lower() for key, value in market_area_mapping.items()}
    clearing_local_balances = retrieve_local_balances_from_json(clearing_optim_variables_path, market_area_mapping)
    exchange_fixing_lp_path = retrieve_exchanges_fixing_lp(path, clearing_local_balances)
    atlas_objectives, atlas_constraints, atlas_variables, atlas_binaries = SolverHelper.read_lp_ortools(
        exchange_fixing_lp_path)
    atlas_dict = {
        "constraints": atlas_constraints,
        "variables": atlas_variables,
        "objectives": atlas_objectives,
        "binaries": atlas_binaries,
    }
    atlas_solver = SolverHelper.model_from_dict_mc(atlas_dict, "XPRESS")
    atlas_solver.Solve()
    s_atlas = atlas_solver.ExportModelAsLpFormat(False)
    with open(os.path.join(path, "exchange_fixing_test_atlas.lp"), "w") as f:
        f.write(s_atlas)

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
