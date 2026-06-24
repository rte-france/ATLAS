"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Tests for LP model export and comparison against reference LP files for other technologies.
This test compares generated LP files from storage and thermal intermediate with different price scenarios
against pre-existing reference LP files to ensure the optimization model remains consistent.
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
DAY_AHEAD_INPUT_DIR = Path("tests/dataset/day_ahead/day_ahead_input")
REFERENCE_LP_DIR = Path(__file__).parent / "lp_files" / "others"


@pytest.fixture(scope="class")
def generated_lp_files():
    """Generate LP files once for all other technology tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        params_dict = {
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
            "ev_smoothing_factor": 0.1,
            "epsilon": 0.001,
            "hydraulic_minimal_fragment_size": 100,
            "load_price": 3000,
            "manual_unprocured_reserves_penalty": 100,
            "phs_smoothing_factor": 0.2,
            "battery_nb_fragments": 3,
            "ev_nb_fragments": 3,
            "phs_nb_fragments": 3,
            "price_forecasts_types": ["Medium", "High", "Low"],
            "output": {
                "output_dir": tmpdir,
            },
        }

        input_data = AtlasDataset.from_directory(DAY_AHEAD_INPUT_DIR)
        module = DayAheadOrdersModule()

        start = pendulum.now()
        module.run(input_data, params_dict)
        elapsed = (pendulum.now() - start).total_seconds()

        lp_files = list((Path(tmpdir) / "lp_export").glob("*.lp"))

        lp_data_cache = {}
        for lp_file in lp_files:
            lp_data_cache[lp_file.name] = SolverHelper.read_lp_ortools(str(lp_file))

        yield lp_data_cache, elapsed


@pytest.fixture(
    params=[
        ("a_thermal_intermediate_1", "High"),
        ("a_thermal_intermediate_1", "Low"),
        ("a_thermal_intermediate_1", "Medium"),
        ("a_battery_1", None),
        ("a_electric_vehicle_1", None),
    ]
)
def other_technology_test_case(request):
    """Parametrize test across storage and thermal intermediate price scenarios."""
    asset_name, price_forecast = request.param

    # Determine reference LP filename
    if price_forecast:
        reference_filename = f"{asset_name}_price_{price_forecast}.lp"
    else:
        reference_filename = f"storage_{asset_name}.lp"

    reference_lp = REFERENCE_LP_DIR / reference_filename

    if not DAY_AHEAD_INPUT_DIR.exists():
        pytest.skip(f"Day ahead input dataset not found: {DAY_AHEAD_INPUT_DIR}")

    if not reference_lp.exists():
        pytest.skip(f"Reference LP file not found: {reference_lp}")

    return asset_name, price_forecast, reference_lp


class TestOtherTechnologiesLPComparison:
    """Tests for comparing generated LP files against reference LP files for storage and price scenarios."""

    def test_generated_lp_matches_reference(self, generated_lp_files, other_technology_test_case):
        """Test that generated LP matches the reference LP for storage and thermal intermediate scenarios."""
        lp_data_cache, _ = generated_lp_files
        asset_name, price_forecast, reference_lp = other_technology_test_case

        matching_lp_data = None
        for lp_filename, lp_data in lp_data_cache.items():
            if price_forecast:
                if asset_name in lp_filename and price_forecast in lp_filename:
                    matching_lp_data = lp_data
                    break
            else:
                if asset_name in lp_filename:
                    matching_lp_data = lp_data
                    break

        assert matching_lp_data is not None, f"No matching LP file found for {asset_name}" + (
            f" with price {price_forecast}" if price_forecast else ""
        )

        try:
            reference_lp_data = SolverHelper.read_lp_ortools(str(reference_lp))
        except Exception as e:
            pytest.fail(f"Failed to read reference LP file: {e}")

        with tempfile.TemporaryDirectory() as compare_dir:
            comparison_result = SolverHelper.compare_lp_problems(
                reference_lp_data,
                matching_lp_data,
                output_dir=compare_dir,
                pb1_name="Reference",
                pb2_name="Generated",
                tolerance=1,
                normalize_names=True,
                keep_identical=False,
            )

            test_name = f"{asset_name}" + (f"_price_{price_forecast}" if price_forecast else "")

            assert comparison_result["objectives"]["identical_pct"] == 100.0, (
                f"Objectives mismatch for {test_name}: {comparison_result['objectives']['identical_pct']}% identical"
            )
            assert comparison_result["variables"]["identical_pct"] == 100.0, (
                f"Variables mismatch for {test_name}: {comparison_result['variables']['identical_pct']}% identical"
            )
            assert comparison_result["constraints"]["identical_pct"] == 100.0, (
                f"Constraints mismatch for {test_name}: {comparison_result['constraints']['identical_pct']}% identical"
            )
            for category in ["objectives", "variables", "constraints"]:
                assert comparison_result[category]["modified"] == 0, f"Modified {category} found in {test_name}"
                assert comparison_result[category]["only_legacy"] == 0, (
                    f"{category.capitalize()} only in reference LP for {test_name}"
                )
                assert comparison_result[category]["only_atlas"] == 0, (
                    f"{category.capitalize()} only in generated LP for {test_name}"
                )

    def test_execution_time_within_threshold(self, generated_lp_files):
        """Test that module execution time is within the defined threshold."""
        _, elapsed = generated_lp_files

        threshold = load_threshold_for_module("DayAheadOrdersTechno")
        if threshold is None:
            pytest.skip("No performance threshold defined for DayAheadOrdersTechno")

        assert elapsed <= threshold, f"DayAheadOrders took {elapsed:.2f}s, expected <= {threshold}s"
