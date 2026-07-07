"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Tests for LP model export and comparison against reference LP files.
This test compares generated LP files from thermal combinations against
pre-existing reference LP files to ensure the optimization model remains consistent.
"""

import tempfile
from pathlib import Path

import pendulum
import pytest

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.day_ahead_orders.module import DayAheadOrdersModule
from atlas.solver.solver_helper import SolverHelper
from tests.utils import load_threshold_for_module

# Test data directories
THERMAL_COMBINATIONS_DIR = Path("tests/dataset/thermals-dataset")
REFERENCE_LP_DIR = Path(__file__).parent / "lp_files" / "thermal"


@pytest.fixture(scope="class")
def base_parameters_dict():
    """Create base day-ahead orders parameters dictionary for testing."""
    return {
        "temporal": {
            "start_date": "2028-09-27 00:00:00",
            "execution_date": "2028-09-26 12:00:00",
            "end_date": "2028-09-28 00:00:00",
            "timestep": "PT1H",
        },
        "solver": {
            "solver_name": "SCIP",
            "export_lp": True,
            "use_presolve": True,
            "duality_gap": 0.0001,
            "timeout": "PT120S",
        },
        "proportional_reserves_penalty": True,
        "automated_unprocured_reserves_penalty": 10000,
        "battery_smoothing_factor": 0.1,
        "ev_energy_coef": 1.5,
        "electric_vehicle_smoothing_factor": 0.1,
        "allowed_round_off_error": 0.001,
        "hydraulic_minimal_fragment_size": 100,
        "load_price": 3000,
        "manual_unprocured_reserves_penalty": 100,
        "pumped_hydraulic_smoothing_factor": 0.2,
        "battery_nb_fragments": 3,
        "electric_vehicle_nb_fragments": 3,
        "pumped_hydraulic_nb_fragments": 3,
        "price_forecasts_types": ["Medium"],
    }


@pytest.fixture(params=[1, 2, 3, 4, 5, 6, 7, 8], scope="class")
def thermal_combination_number(request):
    """Parametrize test across all thermal combinations (1-8)."""
    combination_num = request.param
    combination_name = f"thermal-combination-{combination_num}"
    combination_dir = THERMAL_COMBINATIONS_DIR / combination_name
    reference_lp = REFERENCE_LP_DIR / f"dao-combination-{combination_num}.lp"

    if not combination_dir.exists():
        pytest.skip(f"Thermal combination dataset not found: {combination_dir}")

    if not reference_lp.exists():
        pytest.skip(f"Reference LP file not found: {reference_lp}")

    return combination_num, combination_name, combination_dir, reference_lp


class TestThermalCombinationLPComparison:
    """Tests for comparing generated LP files against reference LP files."""

    @pytest.fixture(scope="class")
    def executed_dao_module(self, thermal_combination_number, base_parameters_dict):
        _combination_num, combination_name, combination_dir, reference_lp = thermal_combination_number

        with tempfile.TemporaryDirectory() as tmpdir:
            params_dict = base_parameters_dict.copy()
            params_dict["output"] = {"output_dir": tmpdir}

            input_data = AtlasDataset.from_directory(combination_dir)
            module = DayAheadOrdersModule()

            start = pendulum.now()
            module.run(input_data, params_dict)
            elapsed = (pendulum.now() - start).total_seconds()

            lp_files = list((Path(tmpdir) / "lp_export").glob("*.lp"))
            generated_lp_data = None
            if lp_files:
                try:
                    generated_lp_data = SolverHelper.read_lp_ortools(str(lp_files[0]))
                except Exception as e:
                    pytest.fail(f"Failed to read generated LP file: {e}")

            try:
                reference_lp_data = SolverHelper.read_lp_ortools(str(reference_lp))
            except Exception as e:
                pytest.fail(f"Failed to read reference LP file: {e}")

            yield combination_name, generated_lp_data, reference_lp_data, elapsed, len(lp_files)

    def test_generated_lp_matches_reference(self, executed_dao_module):
        """Test that generated LP matches the reference LP for each thermal combination."""
        combination_name, generated_lp_data, reference_lp_data, _, lp_count = executed_dao_module

        assert lp_count > 0, f"No LP files generated for {combination_name}"

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
                f"Objectives mismatch for {combination_name}: {comparison_result['objectives']['identical_pct']}% identical"
            )
            assert comparison_result["variables"]["identical_pct"] == 100.0, (
                f"Variables mismatch for {combination_name}: {comparison_result['variables']['identical_pct']}% identical"
            )
            assert comparison_result["constraints"]["identical_pct"] == 100.0, (
                f"Constraints mismatch for {combination_name}: "
                f"{comparison_result['constraints']['identical_pct']}% identical"
            )
            for category in ["objectives", "variables", "constraints"]:
                assert comparison_result[category]["modified"] == 0, f"Modified {category} found in {combination_name}"
                assert comparison_result[category]["only_legacy"] == 0, (
                    f"{category.capitalize()} only in reference LP for {combination_name}"
                )
                assert comparison_result[category]["only_atlas"] == 0, (
                    f"{category.capitalize()} only in generated LP for {combination_name}"
                )

    def test_execution_time_within_threshold(self, executed_dao_module):
        """Test that module execution time is within the defined threshold."""
        combination_name, _, _, elapsed, _ = executed_dao_module

        threshold = load_threshold_for_module("DayAheadOrdersThermal")
        if threshold is None:
            pytest.skip("No performance threshold defined for DayAheadOrdersThermal")

        assert elapsed <= threshold, (
            f"DayAheadOrders took {elapsed:.2f}s for {combination_name}, expected <= {threshold}s"
        )
