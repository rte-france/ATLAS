"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import json
import tempfile
from pathlib import Path

import pytest

from atlas import AtlasDataset
from atlas.modules.market_clearing.module import MarketClearingModule
from atlas.modules.market_clearing.phases.pricing import Pricing
from atlas.solver.solver_helper import SolverHelper


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
def test_if_pricing_generated_lp_matches_reference(dataset_name):
    dataset_path = Path("data") / "market_clearing_prometheus" / dataset_name
    dataset_data_path = dataset_path / "atlas-dataset"
    parameters_path = dataset_path / "parameters.yml"
    saturated_critical_branches_path = dataset_path / "expected_results" / "clearing_saturated_critical_branches.json"
    exchanges_fixing_border_exchanges_path = (
        dataset_path / "expected_results" / "exchanges_fixing_border_exchanges.json"
    )
    clearing_local_balances_path = dataset_path / "expected_results" / "clearing_local_balances.json"
    clearing_accepted_powers_path = dataset_path / "expected_results" / "clearing_accepted_powers.json"
    expected_pricing_1_path = dataset_path / "expected_results" / "pricing_1_model.lp"
    expected_pricing_2_path = dataset_path / "expected_results" / "pricing_2_model.lp"
    expected_pricing_3_path = dataset_path / "expected_results" / "pricing_3_model.lp"

    with tempfile.TemporaryDirectory() as tmpdir:
        raw_data = AtlasDataset.from_directory(dataset_data_path)

        try:
            mc_module = MarketClearingModule()
            parameters = mc_module.import_parameters(parameters_path)
            parameters.output.output_dir = Path(tmpdir)
            input_dataset = mc_module.import_data(raw_data, parameters)

            with open(saturated_critical_branches_path) as f:
                saturated_critical_branches = {}
                for cb, time_index, val in json.load(f):
                    saturated_critical_branches[cb, time_index] = val
            with open(exchanges_fixing_border_exchanges_path) as f:
                exchanges_fixing_border_exchanges = {}
                for b, time_index, val in json.load(f):
                    exchanges_fixing_border_exchanges[b, time_index] = val
            with open(clearing_local_balances_path) as f:
                clearing_local_balances = {}
                for ma, t, val in json.load(f):
                    clearing_local_balances[ma, t] = val
            with open(clearing_accepted_powers_path) as f:
                clearing_accepted_powers = {}
                for ma, o, val in json.load(f):
                    clearing_accepted_powers[ma, o] = val

            pricing = Pricing(
                input_dataset,
                parameters,
                saturated_critical_branches,
                exchanges_fixing_border_exchanges,
                clearing_local_balances,
                clearing_accepted_powers,
            )
            pricing.run()

        except Exception as e:
            pytest.fail(f"Clearing failed for {dataset_name}: {e}")

        pricing_1_lp = Path(parameters.output.output_dir) / "pricing_1_model.lp"

        try:
            generated_lp_data_1 = SolverHelper.read_lp_ortools(str(pricing_1_lp))
            reference_lp_data_1 = SolverHelper.read_lp_ortools(str(expected_pricing_1_path))
        except Exception as e:
            pytest.fail(f"Failed to read LP files: {e}")

        with tempfile.TemporaryDirectory() as compare_dir:
            comparison_result_1 = SolverHelper.compare_lp_problems(
                reference_lp_data_1,
                generated_lp_data_1,
                output_dir=compare_dir,
                pb1_name="Reference",
                pb2_name="Generated",
                tolerance=1,
                normalize_names=True,
                keep_identical=False,
            )

            assert comparison_result_1["objectives"]["identical_pct"] == 100.0, (
                f"Objectives mismatch for {dataset_name}: "
                f"{comparison_result_1['objectives']['identical_pct']}% identical"
            )

            assert comparison_result_1["variables"]["identical_pct"] == 100.0, (
                f"Variables mismatch for {dataset_name}: {comparison_result_1['variables']['identical_pct']}% identical"
            )

            assert (
                comparison_result_1["constraints"]["total_legacy"] == comparison_result_1["constraints"]["total_atlas"]
            ), (
                f"Constraints mismatch for {dataset_name}: "
                f"{comparison_result_1['constraints']['identical_pct']}% identical"
            )

            for category in ["objectives", "variables"]:
                assert comparison_result_1[category]["modified"] == 0, f"Modified {category} found in {dataset_name}"
                assert comparison_result_1[category]["only_legacy"] == 0, (
                    f"{category.capitalize()} only in reference LP for {dataset_name}"
                )
                assert comparison_result_1[category]["only_atlas"] == 0, (
                    f"{category.capitalize()} only in generated LP for {dataset_name}"
                )

        pricing_2_lp = Path(parameters.output.output_dir) / "pricing_2_model.lp"
        if pricing_2_lp.exists():
            try:
                generated_lp_data_2 = SolverHelper.read_lp_ortools(str(pricing_2_lp))
                reference_lp_data_2 = SolverHelper.read_lp_ortools(str(expected_pricing_2_path))
            except Exception as e:
                pytest.fail(f"Failed to read LP files: {e}")

            with tempfile.TemporaryDirectory() as compare_dir:
                comparison_result_2 = SolverHelper.compare_lp_problems(
                    reference_lp_data_2,
                    generated_lp_data_2,
                    output_dir=compare_dir,
                    pb1_name="Reference",
                    pb2_name="Generated",
                    tolerance=1,
                    normalize_names=True,
                    keep_identical=False,
                )

                assert comparison_result_2["objectives"]["identical_pct"] == 100.0, (
                    f"Objectives mismatch for {dataset_name}: "
                    f"{comparison_result_2['objectives']['identical_pct']}% identical"
                )

                assert comparison_result_2["variables"]["identical_pct"] == 100.0, (
                    f"Variables mismatch for {dataset_name}: "
                    f"{comparison_result_2['variables']['identical_pct']}% identical"
                )

                assert (
                    comparison_result_2["constraints"]["total_legacy"]
                    == comparison_result_2["constraints"]["total_atlas"]
                ), (
                    f"Constraints mismatch for {dataset_name}: "
                    f"{comparison_result_2['constraints']['identical_pct']}% identical"
                )

                for category in ["objectives", "variables"]:
                    assert comparison_result_2[category]["modified"] == 0, (
                        f"Modified {category} found in {dataset_name}"
                    )
                    assert comparison_result_2[category]["only_legacy"] == 0, (
                        f"{category.capitalize()} only in reference LP for {dataset_name}"
                    )
                    assert comparison_result_2[category]["only_atlas"] == 0, (
                        f"{category.capitalize()} only in generated LP for {dataset_name}"
                    )

        pricing_3_lp = Path(parameters.output.output_dir) / "pricing_3_model.lp"
        if pricing_3_lp.exists():
            try:
                generated_lp_data_3 = SolverHelper.read_lp_ortools(str(pricing_3_lp))
                reference_lp_data_3 = SolverHelper.read_lp_ortools(str(expected_pricing_3_path))
            except Exception as e:
                pytest.fail(f"Failed to read LP files: {e}")

            with tempfile.TemporaryDirectory() as compare_dir:
                comparison_result_3 = SolverHelper.compare_lp_problems(
                    reference_lp_data_3,
                    generated_lp_data_3,
                    output_dir=compare_dir,
                    pb1_name="Reference",
                    pb2_name="Generated",
                    tolerance=1,
                    normalize_names=True,
                    keep_identical=False,
                )

                assert comparison_result_3["objectives"]["identical_pct"] == 100.0, (
                    f"Objectives mismatch for {dataset_name}: "
                    f"{comparison_result_3['objectives']['identical_pct']}% identical"
                )

                assert comparison_result_3["variables"]["identical_pct"] == 100.0, (
                    f"Variables mismatch for {dataset_name}: "
                    f"{comparison_result_3['variables']['identical_pct']}% identical"
                )

                assert (
                    comparison_result_3["constraints"]["total_legacy"]
                    == comparison_result_3["constraints"]["total_atlas"]
                ), (
                    f"Constraints mismatch for {dataset_name}: "
                    f"{comparison_result_3['constraints']['identical_pct']}% identical"
                )

                for category in ["objectives", "variables"]:
                    assert comparison_result_3[category]["modified"] == 0, (
                        f"Modified {category} found in {dataset_name}"
                    )
                    assert comparison_result_3[category]["only_legacy"] == 0, (
                        f"{category.capitalize()} only in reference LP for {dataset_name}"
                    )
                    assert comparison_result_3[category]["only_atlas"] == 0, (
                        f"{category.capitalize()} only in generated LP for {dataset_name}"
                    )
