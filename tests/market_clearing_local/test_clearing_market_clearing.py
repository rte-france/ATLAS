"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import tempfile
from pathlib import Path

import pytest

from atlas import InputLoader
from atlas.modules.market_clearing.module import MarketClearingModule
from atlas.modules.market_clearing.phases.clearing import Clearing
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
def test_if_clearing_generated_lp_matches_reference(dataset_name):
    dataset_path = Path("data") / "market_clearing_prometheus" / dataset_name
    dataset_data_path = dataset_path / "atlas-dataset"
    parameters_path = dataset_path / "parameters.yml"
    expected_clearing_path = dataset_path / "expected_results" / "clearing_model.lp"

    with tempfile.TemporaryDirectory() as tmpdir:
        raw_data = InputLoader.from_directory(dataset_data_path)

        try:
            mc_module = MarketClearingModule()
            parameters = mc_module.import_parameters(parameters_path)
            parameters.output_path = tmpdir
            input_dataset = mc_module.import_data(raw_data, parameters)

            clearing = Clearing(input_dataset, parameters)
            clearing.run()
        except Exception as e:
            pytest.fail(f"Clearing failed for {dataset_name}: {e}")

        clearing_lp = Path(parameters.output_path) / "clearing_model.lp"

        try:
            generated_lp_data = SolverHelper.read_lp_ortools(str(clearing_lp))
            reference_lp_data = SolverHelper.read_lp_ortools(str(expected_clearing_path))
        except Exception as e:
            pytest.fail(f"Failed to read LP files: {e}")

        with tempfile.TemporaryDirectory() as compare_dir:
            comparison_result = SolverHelper.compare_lp_problems(
                reference_lp_data,
                generated_lp_data,
                output_dir=compare_dir,
                pb1_name="Reference",
                pb2_name="Generated",
                tolerance=1,
                normalize_names=True,
                keep_identical=False,
            )

            assert comparison_result["objectives"]["identical_pct"] == 100.0, (
                f"Objectives mismatch for {dataset_name}: {comparison_result['objectives']['identical_pct']}% identical"
            )

            assert comparison_result["variables"]["identical_pct"] == 100.0, (
                f"Variables mismatch for {dataset_name}: {comparison_result['variables']['identical_pct']}% identical"
            )

            assert comparison_result["constraints"]["identical_pct"] == 100.0, (
                f"Constraints mismatch for {dataset_name}: "
                f"{comparison_result['constraints']['identical_pct']}% identical"
            )

            for category in ["objectives", "variables", "constraints"]:
                assert comparison_result[category]["modified"] == 0, f"Modified {category} found in {dataset_name}"
                assert comparison_result[category]["only_legacy"] == 0, (
                    f"{category.capitalize()} only in reference LP for {dataset_name}"
                )
                assert comparison_result[category]["only_atlas"] == 0, (
                    f"{category.capitalize()} only in generated LP for {dataset_name}"
                )
