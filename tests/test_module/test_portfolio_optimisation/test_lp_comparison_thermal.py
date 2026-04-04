"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Tests for LP model export and comparison against reference LP files.
This test compares generated LP files from thermal combinations against
pre-existing reference LP files to ensure the optimization model remains consistent.
"""

import tempfile
from pathlib import Path

import pytest

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.portfolio_optimisation.module import PortfolioOptimisationModule
from atlas.solver.solver_helper import SolverHelper

# Test data directories
THERMAL_COMBINATIONS_DIR = Path("tests/dataset/thermals-dataset")
REFERENCE_LP_DIR = Path(__file__).parent / "lp_files" / "thermal"


@pytest.fixture
def base_parameters_dict():
    """Create base portfolio optimisation parameters dictionary for testing."""
    return {
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
    }


@pytest.fixture(params=[1, 2, 3, 4, 5, 6, 7, 8])
def thermal_combination_number(request):
    """Parametrize test across all thermal combinations (1-8)."""
    combination_num = request.param
    combination_name = f"thermal-combination-{combination_num}"
    combination_dir = THERMAL_COMBINATIONS_DIR / combination_name
    reference_lp = REFERENCE_LP_DIR / f"po-combination-{combination_num}.lp"

    if not combination_dir.exists():
        pytest.skip(f"Thermal combination dataset not found: {combination_dir}")

    if not reference_lp.exists():
        pytest.skip(f"Reference LP file not found: {reference_lp}")

    return combination_num, combination_name, combination_dir, reference_lp


class TestThermalCombinationLPComparison:
    """Tests for comparing generated LP files against reference LP files."""

    def test_generated_lp_matches_reference(self, thermal_combination_number, base_parameters_dict):
        """Test that generated LP matches the reference LP for each thermal combination."""
        _combination_num, combination_name, combination_dir, reference_lp = thermal_combination_number

        with tempfile.TemporaryDirectory() as tmpdir:
            params_dict = base_parameters_dict.copy()
            params_dict["output"] = {
                "output_dir": tmpdir,
            }

            input_data = AtlasDataset.from_directory(combination_dir)

            po_module = PortfolioOptimisationModule()

            try:
                po_module.run(input_data, params_dict)
            except Exception as e:
                pytest.fail(f"Portfolio optimization failed for {combination_name}: {e}")

            lp_files = lp_files = list((Path(tmpdir) / "lp_export").glob("*.lp"))
            assert len(lp_files) > 0, f"No LP files generated for {combination_name}"

            generated_lp = lp_files[0]

            try:
                generated_lp_data = SolverHelper.read_lp_ortools(str(generated_lp))
                reference_lp_data = SolverHelper.read_lp_ortools(str(reference_lp))
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
                    f"Objectives mismatch for {combination_name}: "
                    f"{comparison_result['objectives']['identical_pct']}% identical"
                )

                assert comparison_result["variables"]["identical_pct"] == 100.0, (
                    f"Variables mismatch for {combination_name}: "
                    f"{comparison_result['variables']['identical_pct']}% identical"
                )

                assert comparison_result["constraints"]["identical_pct"] == 100.0, (
                    f"Constraints mismatch for {combination_name}: "
                    f"{comparison_result['constraints']['identical_pct']}% identical"
                )

                for category in ["objectives", "variables", "constraints"]:
                    assert comparison_result[category]["modified"] == 0, (
                        f"Modified {category} found in {combination_name}"
                    )
                    assert comparison_result[category]["only_legacy"] == 0, (
                        f"{category.capitalize()} only in reference LP for {combination_name}"
                    )
                    assert comparison_result[category]["only_atlas"] == 0, (
                        f"{category.capitalize()} only in generated LP for {combination_name}"
                    )
