"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Tests for manual activation of thermal Base units in Portfolio Optimisation.

Thermal Base units are excluded from optimisation (via excluded_thermal_strategy)
and go through manual activation instead. Depending on the market mode:

- Day-Ahead (use_forecast=False): the activation power is stored directly in the
  ``power`` forecasting matrix attribute.
- Intraday (use_forecast=True): the activation power is stored in the
  ``id_po_for_orders`` forecasting matrix attribute, while ``power`` is unchanged.

Both test classes verify the computed values against their respective reference
datasets.
"""

from pathlib import Path

import polars as pl
import pytest
import yaml

from atlas.enums import ThermalStrategy
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.portfolio_optimisation.module import PortfolioOptimisationModule
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters

TOLERANCE = 1e-3

# ── Intraday ──────────────────────────────────────────────────────────────────

ID_INPUT_DATASET = Path("tests/dataset/intraday/portfolio_optimisation_1_input")
ID_REFERENCE_DATASET = Path("tests/dataset/intraday/intraday_orders_input")
ID_PARAMETERS_FILE = Path("tests/dataset/parameters/intraday/portfolio_optimisation_1.yml")

# ── Day-Ahead ─────────────────────────────────────────────────────────────────

DA_INPUT_DATASET = Path("tests/dataset/day_ahead/portfolio_optimisation_input")
DA_REFERENCE_DATASET = Path("tests/dataset/day_ahead/portfolio_optimisation_output")
DA_PARAMETERS_FILE = Path("tests/dataset/parameters/day_ahead/portfolio_optimisation.yml")


def _run_po(input_dir: Path, params_file: Path, tmp_output: str):
    """Run the PO module and return (output_dataset, parameters)."""
    if not input_dir.exists():
        pytest.skip(f"Input dataset not found: {input_dir}")

    with open(params_file) as f:
        params_dict = yaml.safe_load(f)

    params_dict["output"] = {"output_dir": tmp_output}
    params = PortfolioOptimisationParameters(**params_dict)
    input_data = AtlasDataset.from_directory(input_dir)

    try:
        output_dataset = PortfolioOptimisationModule().run(input_data, params_dict)
    except Exception as e:
        pytest.fail(f"Portfolio optimisation failed: {e}")

    return output_dataset, params


def _collect_thermal_base(output_dataset, params):
    """Return list of (thermal, params) for manually activated thermal Base units."""
    results = []
    for result in output_dataset.optimisation_results:
        if result.is_manual_activation:
            for thermal in result.portfolio.equipments.thermal:
                if thermal.strategy == ThermalStrategy.BASE:
                    results.append((thermal, params))
    return results


def _compare_with_reference(thermal, params, ref_dir: Path, attribute: str, exec_date_col: str):
    """Assert that the ForecastingMatrix attribute matches the reference parquet."""
    fm = getattr(thermal, attribute)
    assert fm is not None, f"{attribute} not set for '{thermal.name}'"

    output_forecast = fm.get_forecast(
        params.temporal.execution_date,
        params.temporal.start_date,
        params.temporal.end_date,
    )
    output_values = output_forecast.values

    ref_path = ref_dir / "forecasting_matrix" / "thermal" / f"{thermal.name}.parquet"
    assert ref_path.exists(), f"Reference parquet not found: {ref_path}"

    ref_df = pl.read_parquet(ref_path)
    ref_values = ref_df.filter(pl.col("attribute") == attribute)[exec_date_col].to_list()

    assert len(output_values) == len(ref_values), (
        f"{thermal.name}: expected {len(ref_values)} values, got {len(output_values)}"
    )
    for i, (out_val, ref_val) in enumerate(zip(output_values, ref_values)):
        assert abs(out_val - ref_val) <= TOLERANCE, (
            f"{thermal.name}: mismatch at index {i} — output={out_val}, reference={ref_val}"
        )


# ── Intraday tests ────────────────────────────────────────────────────────────


@pytest.fixture(scope="class")
def id_po_output():
    return _run_po(ID_INPUT_DATASET, ID_PARAMETERS_FILE, "/tmp/atlas_po_id_thermal_base_test")


@pytest.fixture(scope="class")
def id_thermal_base_results(id_po_output):
    return _collect_thermal_base(*id_po_output)


class TestIntradayThermalBaseManualActivation:
    """In intraday mode (use_forecast=True), manual activation stores the computed
    power in ``id_po_for_orders``."""

    def test_id_po_for_orders_is_set(self, id_thermal_base_results):
        """Each thermal Base unit must have id_po_for_orders set after manual activation."""
        assert id_thermal_base_results, "No thermal Base units found in manual activation results"
        for thermal, _ in id_thermal_base_results:
            assert thermal.id_po_for_orders is not None, (
                f"id_po_for_orders not set for thermal Base unit '{thermal.name}'"
            )

    def test_id_po_for_orders_matches_reference(self, id_thermal_base_results):
        """The id_po_for_orders values for thermal Base must match the intraday reference."""
        if not ID_REFERENCE_DATASET.exists():
            pytest.skip(f"Reference dataset not found: {ID_REFERENCE_DATASET}")

        for thermal, params in id_thermal_base_results:
            _compare_with_reference(thermal, params, ID_REFERENCE_DATASET, "id_po_for_orders", "2028-09-26 22:00:00")


# ── Day-Ahead tests ───────────────────────────────────────────────────────────


@pytest.fixture(scope="class")
def da_po_output():
    return _run_po(DA_INPUT_DATASET, DA_PARAMETERS_FILE, "/tmp/atlas_po_da_thermal_base_test")


@pytest.fixture(scope="class")
def da_thermal_base_results(da_po_output):
    return _collect_thermal_base(*da_po_output)


class TestDayAheadThermalBaseManualActivation:
    """In day-ahead mode (use_forecast=False), manual activation stores the computed
    power directly in the ``power`` forecasting matrix attribute."""

    def test_power_is_set(self, da_thermal_base_results):
        """Each thermal Base unit must have power set after manual activation."""
        assert da_thermal_base_results, "No thermal Base units found in manual activation results"
        for thermal, _ in da_thermal_base_results:
            assert thermal.power is not None, f"power not set for thermal Base unit '{thermal.name}'"

    def test_power_matches_reference(self, da_thermal_base_results):
        """The power values for thermal Base must match the day-ahead reference."""
        if not DA_REFERENCE_DATASET.exists():
            pytest.skip(f"Reference dataset not found: {DA_REFERENCE_DATASET}")

        for thermal, params in da_thermal_base_results:
            _compare_with_reference(thermal, params, DA_REFERENCE_DATASET, "power", "2028-09-26 12:00:00")
