"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Numerical snapshot comparison of the MarketClearing solver outputs on the ATC
dataset. Complements ``test_lp_comparison_atc`` by catching changes that affect
solver values (objective coefficients, RHS, constraint signs) without altering
the LP coefficient matrix structure.
"""

import json
from pathlib import Path

import pytest

from atlas.modules.market_clearing.output_dataset import MarketClearingOutputDataset

SNAPSHOT_PATH = Path(__file__).parent / "output_snapshot" / "atc_day_ahead.json"
SNAPSHOT_ID_PATH = Path(__file__).parent / "output_snapshot" / "atc_intraday.json"
SNAPSHOT_FIELDS = ("accepted_powers", "local_balances", "border_exchanges", "market_prices")
NUMERICAL_TOLERANCE = 1e-6


def _dump_snapshot(output_dataset: MarketClearingOutputDataset) -> dict[str, list]:
    return {
        "accepted_powers": [[a, o, v] for (a, o), v in sorted(output_dataset.accepted_powers.items())],
        "local_balances": [[a, t, v] for (a, t), v in sorted(output_dataset.local_balances.items())],
        "border_exchanges": [[b, t, v] for (b, t), v in sorted(output_dataset.border_exchanges.items())],
        "market_prices": [[a, t, v] for (a, t), v in sorted(output_dataset.market_prices.items())],
    }


@pytest.fixture(scope="module")
def expected_snapshot() -> dict[str, list]:
    if not SNAPSHOT_PATH.exists():
        pytest.fail(f"Output snapshot missing: {SNAPSHOT_PATH}. Generate it once with MC_REGENERATE_REFS=1.")
    return json.loads(SNAPSHOT_PATH.read_text())


@pytest.fixture(scope="module")
def expected_snapshot_id() -> dict[str, list]:
    if not SNAPSHOT_ID_PATH.exists():
        pytest.fail(f"Output snapshot missing: {SNAPSHOT_ID_PATH}. Generate it once with MC_REGENERATE_REFS=1.")
    return json.loads(SNAPSHOT_ID_PATH.read_text())


class TestOutputSnapshotATC:
    @pytest.mark.parametrize("field", SNAPSHOT_FIELDS)
    def test_field_keys_match_snapshot(
        self,
        output_dataset: MarketClearingOutputDataset,
        expected_snapshot: dict[str, list],
        field: str,
    ) -> None:
        actual_keys = {tuple(entry[:-1]) for entry in _dump_snapshot(output_dataset)[field]}
        expected_keys = {tuple(entry[:-1]) for entry in expected_snapshot[field]}

        missing = expected_keys - actual_keys
        extra = actual_keys - expected_keys
        assert not missing, f"{field}: missing {len(missing)} keys, e.g. {list(missing)[:3]}"
        assert not extra, f"{field}: unexpected {len(extra)} keys, e.g. {list(extra)[:3]}"

    @pytest.mark.parametrize("field", SNAPSHOT_FIELDS)
    def test_field_values_match_snapshot_within_tolerance(
        self,
        output_dataset: MarketClearingOutputDataset,
        expected_snapshot: dict[str, list],
        field: str,
    ) -> None:
        actual = {tuple(entry[:-1]): entry[-1] for entry in _dump_snapshot(output_dataset)[field]}
        expected = {tuple(entry[:-1]): entry[-1] for entry in expected_snapshot[field]}

        drifted = []
        for key, expected_value in expected.items():
            if key not in actual:
                continue
            actual_value = actual[key]
            if abs(actual_value - expected_value) > NUMERICAL_TOLERANCE:
                drifted.append((key, expected_value, actual_value))

        assert not drifted, (
            f"{field}: {len(drifted)} values drifted beyond tolerance {NUMERICAL_TOLERANCE}, e.g. {drifted[:3]}"
        )


class TestOutputSnapshotATCID:
    @pytest.mark.parametrize("field", SNAPSHOT_FIELDS)
    def test_field_keys_match_snapshot(
        self,
        output_dataset: MarketClearingOutputDataset,
        expected_snapshot: dict[str, list],
        field: str,
    ) -> None:
        actual_keys = {tuple(entry[:-1]) for entry in _dump_snapshot(output_dataset)[field]}
        expected_keys = {tuple(entry[:-1]) for entry in expected_snapshot[field]}

        missing = expected_keys - actual_keys
        extra = actual_keys - expected_keys
        assert not missing, f"{field}: missing {len(missing)} keys, e.g. {list(missing)[:3]}"
        assert not extra, f"{field}: unexpected {len(extra)} keys, e.g. {list(extra)[:3]}"

    @pytest.mark.parametrize("field", SNAPSHOT_FIELDS)
    def test_field_values_match_snapshot_within_tolerance(
        self,
        output_dataset: MarketClearingOutputDataset,
        expected_snapshot: dict[str, list],
        field: str,
    ) -> None:
        actual = {tuple(entry[:-1]): entry[-1] for entry in _dump_snapshot(output_dataset)[field]}
        expected = {tuple(entry[:-1]): entry[-1] for entry in expected_snapshot[field]}

        drifted = []
        for key, expected_value in expected.items():
            if key not in actual:
                continue
            actual_value = actual[key]
            if abs(actual_value - expected_value) > NUMERICAL_TOLERANCE:
                drifted.append((key, expected_value, actual_value))

        assert not drifted, (
            f"{field}: {len(drifted)} values drifted beyond tolerance {NUMERICAL_TOLERANCE}, e.g. {drifted[:3]}"
        )
