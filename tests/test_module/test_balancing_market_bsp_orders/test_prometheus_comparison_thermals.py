"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Comparison of the BSPBalancingOrders outputs against Prometheus, on thermal units.
``input`` is the Prometheus input converted to an Atlas dataset, ``output`` is what Prometheus
formulated on it: the same objects plus the orders and the order couplings. The module is run on
the input and its orders and order couplings are compared with the Prometheus ones.

The module runs with its default parameters, except for two that cannot be left to their default
for the reference to be reproducible:

- ``temporal`` has no default. The window is the single 15 minutes step 10:00-10:15, formulated at 09:45,
  which is what the orders of the reference carry.
- ``product_type`` is mFRR. The reference only holds MFRRActivation orders, while the module defaults to
  RRActivation.

The 10 thermal units are the test cases of the reference. The ones named ``impossible`` are expected
to get no order at all.
"""

from pathlib import Path
from pprint import pformat

import pytest
from pendulum import Duration

from atlas.enums import CouplingType, MarketType
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.balancing_market_bsp_orders.module import BSPBalancingOrdersModule
from atlas.modules.balancing_market_bsp_orders.parameters import BSPBalancingOrdersParameters
from atlas.modules.module_run import ModuleRun
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling

PROMETHEUS_DATASET_DIR = Path("tests/dataset/reserves/bsp_balancing_orders/thermal")
INPUT_DIR = PROMETHEUS_DATASET_DIR / "input"
REFERENCE_DIR = PROMETHEUS_DATASET_DIR / "output"
NUMERICAL_TOLERANCE = 1e-6

THERMAL_CASES = (
    "th_case_1",
    "th_case_1_impossible",
    "th_case_2",
    "th_case_3",
    "th_case_4",
    "th_case_4_procured",
    "th_case_5",
    "th_case_5_impossible_1",
    "th_case_5_impossible_2",
    "th_case_5_impossible_3",
)

DEFAULT_PARAMETERS = {
    "temporal": {
        "start_date": "2028-09-27 10:00:00",
        "end_date": "2028-09-27 10:15:00",
        "execution_date": "2028-09-27 09:45:00",
        "timestep": "PT15M",
    },
}
PARAMETERS = {**DEFAULT_PARAMETERS, "product_type": MarketType.mfrr_activation}

# Compared output fields: the orders and the order couplings, keyed by name.
COMPARISON_FIELDS = ("order", "order_coupling")

# What an order is made of. References are compared by name, floats within NUMERICAL_TOLERANCE.
ORDER_REFERENCES = ("equipment", "market_area", "portfolio")
ORDER_FLOATS = ("qmin", "qmax", "price")
ORDER_VALUES = (
    "order_type",
    "product",
    "start_date",
    "end_date",
    "execution_date",
    "is_agent_tso",
    "price_group",
    "accepted_power",
    "individual_spread",
)

# Values on which ATLAS deliberately departs from Prometheus, as (field, key, attribute): (Prometheus, ATLAS).
# The values test only accepts a drift listed here with these exact values, and a deviation that no longer
# occurs fails test_known_deviations_still_occur, so that the list stays up to date.
KNOWN_DEVIATIONS: dict[tuple[str, str, str], tuple[object, object]] = {
    # Intentional evolution of ATLAS on the upward volume of a unit running on both sides of the step.
    ("order", "th_case_4_mfrr_u_10_00_10_15_at_09_45", "qmax"): (300.0, 150.0),
}

# Prometheus exports an unset duration of a thermal unit as PT0S, the input holds None.
PROMETHEUS_ZERO_DURATIONS = (
    "startup_duration",
    "minimum_time_on",
    "minimum_time_off",
    "minimum_stable_power_duration",
)


def _order_snapshot(order: Order) -> dict[str, object]:
    snapshot: dict[str, object] = {}
    for field in ORDER_REFERENCES:
        reference = getattr(order, field)
        snapshot[field] = None if reference is None else reference.name
    for field in (*ORDER_VALUES, *ORDER_FLOATS):
        snapshot[field] = getattr(order, field)
    return snapshot


def _coupling_snapshot(coupling: OrderCoupling) -> dict[str, object]:
    names = [order.name for order in coupling.orders]
    return {
        "coupling_type": coupling.coupling_type,
        # The first order of a parent-children coupling is the parent, the others have no order.
        "orders": names if coupling.coupling_type == CouplingType.PARENT_CHILDREN else sorted(names),
        "complement_direction": coupling.complement_direction,
        "complement_energy": coupling.complement_energy,
    }


def _dump_snapshot(dataset: AtlasDataset) -> dict[str, dict[str, dict[str, object]]]:
    """Render the orders and the order couplings of a dataset as comparable snapshots, keyed by name."""
    return {
        "order": {order.name: _order_snapshot(order) for order in dataset.order},
        "order_coupling": {coupling.name: _coupling_snapshot(coupling) for coupling in dataset.order_coupling},
    }


def _value_matches(field: str, actual: object, expected: object) -> bool:
    if field in ORDER_FLOATS and actual is not None and expected is not None:
        return abs(float(actual) - float(expected)) <= NUMERICAL_TOLERANCE  # type: ignore[arg-type]
    return actual == expected


def _is_known_deviation(field: str, key: str, attribute: str, expected: object, actual: object) -> bool:
    deviation = KNOWN_DEVIATIONS.get((field, key, attribute))
    if deviation is None:
        return False
    prometheus_value, atlas_value = deviation
    return _value_matches(attribute, expected, prometheus_value) and _value_matches(attribute, actual, atlas_value)


def _zero_if_none(duration: Duration | None) -> Duration:
    return Duration() if duration is None else duration


def _unexplained_differences(result: AtlasDataset, reference: AtlasDataset) -> dict:
    """
    Differences between two datasets once the compared fields and the PT0S convention are set aside.

    The orders and the order couplings have their own tests. A duration that is None on one side and
    PT0S on the other is the way Prometheus exports an unset duration, not a difference.
    """
    differences = result.diff(reference)
    for field in COMPARISON_FIELDS:
        differences.pop(field, None)

    thermal = differences.get("thermal")
    if thermal:
        for name in list(thermal["modified"]):
            fields = thermal["modified"][name]
            for field in PROMETHEUS_ZERO_DURATIONS:
                if field not in fields:
                    continue
                value = getattr(result.thermal.get(name), field)
                reference_value = getattr(reference.thermal.get(name), field)
                if _zero_if_none(value) == _zero_if_none(reference_value):
                    del fields[field]
            if not fields:
                del thermal["modified"][name]
        if not (thermal["only_in_self"] or thermal["only_in_other"] or thermal["modified"]):
            del differences["thermal"]
    return differences


@pytest.fixture(scope="module")
def reference() -> AtlasDataset:
    """The dataset Prometheus produced from the input."""
    if not REFERENCE_DIR.exists():
        pytest.fail(f"Prometheus reference missing: {REFERENCE_DIR}")
    return AtlasDataset.from_directory(REFERENCE_DIR)


@pytest.fixture(scope="module")
def result() -> AtlasDataset:
    """The dataset the module produces from the same input, the way the CLI does."""
    if not INPUT_DIR.exists():
        pytest.fail(f"Prometheus input missing: {INPUT_DIR}")
    parameters = BSPBalancingOrdersParameters.model_validate(PARAMETERS)
    return ModuleRun(BSPBalancingOrdersModule, INPUT_DIR, parameters).run()


class TestThermalPrometheusComparison:
    """Tests comparing the module outputs against the Prometheus reference."""

    def test_only_the_product_differs_from_the_default_parameters(self) -> None:
        default = BSPBalancingOrdersParameters.model_validate(DEFAULT_PARAMETERS)
        used = BSPBalancingOrdersParameters.model_validate(PARAMETERS)

        changed = {field for field in type(used).model_fields if getattr(used, field) != getattr(default, field)}

        assert changed == {"product_type"}

    def test_input_holds_the_thermal_cases_of_the_reference(self, result: AtlasDataset) -> None:
        assert {thermal.name for thermal in result.thermal} == set(THERMAL_CASES)

    @pytest.mark.parametrize("field", COMPARISON_FIELDS)
    def test_field_keys_match_reference(self, result: AtlasDataset, reference: AtlasDataset, field: str) -> None:
        actual_keys = set(_dump_snapshot(result)[field])
        expected_keys = set(_dump_snapshot(reference)[field])

        missing = sorted(expected_keys - actual_keys)
        extra = sorted(actual_keys - expected_keys)
        assert not missing, f"{field}: missing {len(missing)} keys, e.g. {missing[:3]}"
        assert not extra, f"{field}: unexpected {len(extra)} keys, e.g. {extra[:3]}"

    @pytest.mark.parametrize("field", COMPARISON_FIELDS)
    def test_field_values_match_reference_within_tolerance(
            self, result: AtlasDataset, reference: AtlasDataset, field: str
    ) -> None:
        actual = _dump_snapshot(result)[field]
        expected = _dump_snapshot(reference)[field]

        drifted = []
        for key, expected_snapshot in expected.items():
            if key not in actual:
                continue  # reported by test_field_keys_match_reference
            for attribute, expected_value in expected_snapshot.items():
                actual_value = actual[key][attribute]
                if _value_matches(attribute, actual_value, expected_value):
                    continue
                if not _is_known_deviation(field, key, attribute, expected_value, actual_value):
                    drifted.append((key, attribute, expected_value, actual_value))

        assert not drifted, (
            f"{field}: {len(drifted)} values drifted beyond tolerance {NUMERICAL_TOLERANCE}, e.g. {drifted[:3]}"
        )

    def test_known_deviations_still_occur(self, result: AtlasDataset, reference: AtlasDataset) -> None:
        actual = _dump_snapshot(result)
        expected = _dump_snapshot(reference)

        stale = [
            (field, key, attribute)
            for field, key, attribute in KNOWN_DEVIATIONS
            if key not in actual[field]
               or key not in expected[field]
               or not _is_known_deviation(
                field, key, attribute, expected[field][key][attribute], actual[field][key][attribute]
            )
        ]

        assert not stale, f"{len(stale)} known deviations no longer occur, remove them: {stale}"

    def test_other_objects_are_left_unchanged(self, result: AtlasDataset, reference: AtlasDataset) -> None:
        differences = _unexplained_differences(result, reference)

        assert not differences, pformat(differences, width=120)
