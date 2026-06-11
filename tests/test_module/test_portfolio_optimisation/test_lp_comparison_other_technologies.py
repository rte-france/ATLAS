"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Tests for LP model export and comparison against reference LP files.
This test compares generated LP files for other technologies (non-thermal)
against pre-existing reference LP files to ensure the optimization model remains consistent.
"""

import tempfile
from pathlib import Path

import pendulum
import pytest

from atlas.core.io_utils.atlas_dataset import AtlasDataset
from atlas.core.solver.solver_helper import SolverHelper
from atlas.modules.portfolio_optimisation.module import PortfolioOptimisationModule
from tests.utils import load_threshold_for_module

# Test data directories
INPUT_DATASET_DIR = Path("tests/dataset/day_ahead/portfolio_optimisation_input")
REFERENCE_LP_DIR = Path(__file__).parent / "lp_files" / "others"


@pytest.fixture(scope="class")
def generated_lp_files():
    """Generate LP files once for all other technology tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        params_dict = {
            "temporal": {
                "start_date": "2028-09-27 00:00:00",
                "end_date": "2028-09-28 00:00:00",
                "execution_date": "2028-09-26 12:00:00",
                "timestep": "PT1H",
            },
            "solver": {
                "solver_name": "SCIP",
                "use_presolve": False,
                "export_lp": True,
                "timeout": "PT120S",
            },
            "battery_smoothing_factor": 0.1,
            "small_imbalance_size": 0.15,
            "small_imbalance_penalty": 0.05,
            "excluded_technologies": ["thermal"],
            "excluded_market_areas": ["ma_b"],
            "output": {
                "output_dir": tmpdir,
            },
        }

        input_data = AtlasDataset.from_directory(INPUT_DATASET_DIR)
        po_module = PortfolioOptimisationModule()

        start = pendulum.now()
        try:
            po_module.run(input_data, params_dict)
        except Exception as e:
            pytest.fail(f"Portfolio optimization failed: {e}")
        elapsed = (pendulum.now() - start).total_seconds()

        lp_files = list((Path(tmpdir) / "lp_export").glob("*.lp"))

        lp_data_cache = {}
        for lp_file in lp_files:
            lp_data_cache[lp_file.name] = SolverHelper.read_lp_ortools(str(lp_file))

        yield lp_data_cache, elapsed


class TestOtherTechnologiesLPComparison:
    """Tests for comparing generated LP files against reference LP files for other technologies."""

    @pytest.mark.parametrize(
        "lp_filename",
        ["po_generator_a.lp", "po_supplier_a.lp"],
    )
    def test_generated_lp_matches_reference(self, generated_lp_files, lp_filename):
        """Test that generated LP files match the reference LP files for other technologies."""
        lp_data_cache, _ = generated_lp_files
        reference_lp = REFERENCE_LP_DIR / lp_filename

        if not INPUT_DATASET_DIR.exists():
            pytest.skip(f"Input dataset not found: {INPUT_DATASET_DIR}")

        if not reference_lp.exists():
            pytest.skip(f"Reference LP file not found: {reference_lp}")

        if lp_filename not in lp_data_cache:
            pytest.fail(f"Generated LP file not found: {lp_filename}")

        generated_lp_data = lp_data_cache[lp_filename]

        try:
            reference_lp_data = SolverHelper.read_lp_ortools(str(reference_lp))
        except Exception as e:
            pytest.fail(f"Failed to read reference LP file: {e}")

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
                f"Objectives mismatch for {lp_filename}: {comparison_result['objectives']['identical_pct']}% identical"
            )
            assert comparison_result["variables"]["identical_pct"] == 100.0, (
                f"Variables mismatch for {lp_filename}: {comparison_result['variables']['identical_pct']}% identical"
            )
            assert comparison_result["constraints"]["identical_pct"] == 100.0, (
                f"Constraints mismatch for {lp_filename}: "
                f"{comparison_result['constraints']['identical_pct']}% identical"
            )
            for category in ["objectives", "variables", "constraints"]:
                assert comparison_result[category]["modified"] == 0, f"Modified {category} found in {lp_filename}"
                assert comparison_result[category]["only_legacy"] == 0, (
                    f"{category.capitalize()} only in reference LP for {lp_filename}"
                )
                assert comparison_result[category]["only_atlas"] == 0, (
                    f"{category.capitalize()} only in generated LP for {lp_filename}"
                )

    def test_execution_time_within_threshold(self, generated_lp_files):
        """Test that module execution time is within the defined threshold."""
        _, elapsed = generated_lp_files

        threshold = load_threshold_for_module("PortfolioOptimisationTechno")
        if threshold is None:
            pytest.skip("No performance threshold defined for PortfolioOptimisationTechno")

        assert elapsed <= threshold, f"PortfolioOptimisation took {elapsed:.2f}s, expected <= {threshold}s"
