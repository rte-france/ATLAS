"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

LP-level snapshot comparison for the MarketClearing module on the ATC dataset.

Each phase exports its LP to disk; we compare the generated LPs byte-equivalently
to a committed reference using ``SolverHelper.compare_lp_problems``. The LP
formulation is built from the input dataset and is fully deterministic, so any
divergence flags an unintended formulation change during refactor.

"""

import tempfile
from pathlib import Path

import pytest

from atlas.solver.solver_helper import SolverHelper

REFERENCE_LP_DIR = Path(__file__).parent / "lp_files" / "atc"
REFERENCE_LP_ID_DIR = Path(__file__).parent / "lp_files" / "atc_id"
LP_FILENAMES = [
    "clearing_model.lp",
    "exchanges_fixing_model.lp",
    "pricing_1_model.lp",
]


class TestLPComparisonATC:
    @pytest.mark.parametrize("lp_filename", LP_FILENAMES)
    def test_generated_lp_matches_reference(self, generated_lp_dir: Path, lp_filename: str) -> None:
        generated_lp = generated_lp_dir / lp_filename
        reference_lp = REFERENCE_LP_DIR / lp_filename

        assert generated_lp.exists(), f"Module did not generate {lp_filename}"

        assert reference_lp.exists(), f"Reference LP missing: {reference_lp}"

        generated_lp_data = SolverHelper.read_lp_ortools(str(generated_lp))
        reference_lp_data = SolverHelper.read_lp_ortools(str(reference_lp))

        with tempfile.TemporaryDirectory() as compare_dir:
            comparison = SolverHelper.compare_lp_problems(
                reference_lp_data,
                generated_lp_data,
                output_dir=compare_dir,
                pb1_name="Reference",
                pb2_name="Generated",
                tolerance=1,
                normalize_names=True,
                keep_identical=False,
            )

        for category in ("objectives", "variables", "constraints"):
            assert comparison[category]["identical_pct"] == 100.0, (
                f"{category} drift in {lp_filename}: {comparison[category]['identical_pct']}% identical"
            )
            assert comparison[category]["modified"] == 0, f"Modified {category} in {lp_filename}"
            assert comparison[category]["only_legacy"] == 0, f"{category} present only in reference for {lp_filename}"
            assert comparison[category]["only_atlas"] == 0, f"{category} present only in generated LP for {lp_filename}"


class TestLPComparisonATCID:
    @pytest.mark.parametrize("lp_filename", LP_FILENAMES)
    def test_generated_lp_matches_reference(self, generated_lp_dir_id: Path, lp_filename: str) -> None:
        generated_lp = generated_lp_dir_id / lp_filename
        reference_lp = REFERENCE_LP_ID_DIR / lp_filename

        assert generated_lp.exists(), f"Module did not generate {lp_filename}"

        assert reference_lp.exists(), f"Reference LP missing: {reference_lp}"

        generated_lp_data = SolverHelper.read_lp_ortools(str(generated_lp))
        reference_lp_data = SolverHelper.read_lp_ortools(str(reference_lp))

        with tempfile.TemporaryDirectory() as compare_dir:
            comparison = SolverHelper.compare_lp_problems(
                reference_lp_data,
                generated_lp_data,
                output_dir=compare_dir,
                pb1_name="Reference",
                pb2_name="Generated",
                tolerance=1,
                normalize_names=True,
                keep_identical=False,
            )

        for category in ("objectives", "variables", "constraints"):
            assert comparison[category]["identical_pct"] == 100.0, (
                f"{category} drift in {lp_filename}: {comparison[category]['identical_pct']}% identical"
            )
            assert comparison[category]["modified"] == 0, f"Modified {category} in {lp_filename}"
            assert comparison[category]["only_legacy"] == 0, f"{category} present only in reference for {lp_filename}"
            assert comparison[category]["only_atlas"] == 0, f"{category} present only in generated LP for {lp_filename}"
