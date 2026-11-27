"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Validation of the semi-peak (intermediate) thermal formulation of the day-ahead orders module
against a reference dataset: orders and couplings formulated from ``dao_semi_peak_input`` must
match those stored in ``dao_semi_peak_output``.

Object names differ between Atlas and the reference (abbreviated naming in Atlas), so orders and
couplings are compared on their content: an order is identified by all its attributes but its name,
a coupling by its attributes and the content of the orders it links.
"""

from collections import Counter
from collections.abc import Hashable, Iterable
from pathlib import Path

import pytest

from atlas.enums import CouplingType, ThermalStrategy
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.day_ahead_orders.input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.result import DayAheadOrdersResult
from atlas.modules.day_ahead_orders.steps.abstract_step import StepResult
from atlas.modules.day_ahead_orders.steps.thermal.thermal_intermediate_orders import ThermalIntermediateLoadOrders
from atlas.objects.business_model import BusinessModel
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling
from atlas.timing import generate_datetimes

SEMI_PEAK_INPUT_DIR = Path("tests/dataset/day_ahead/dao_semi_peak_input")
SEMI_PEAK_OUTPUT_DIR = Path("tests/dataset/day_ahead/dao_semi_peak_output")

# Same parameters as the other step tests (see conftest.STEPS_PARAMS_DICT), with SCIP as solver
# since Xpress is not available everywhere.
SEMI_PEAK_PARAMS_DICT = {
    "temporal": {
        "start_date": "2028-09-27 00:00:00",
        "execution_date": "2028-09-26 12:00:00",
        "end_date": "2028-09-28 00:00:00",
        "timestep": "PT1H",
    },
    "solver": {"solver_name": "SCIP"},
    "load_price": 3000,
    "hydraulic_minimal_fragment_size": 100,
    "price_forecasts_types": ["Medium", "High", "Low"],
}

FLOAT_DECIMALS = 6

# Order attributes filled by the market clearing, not by the day-ahead orders module
# (they are None in Atlas and default to 0 in the reference dataset).
CLEARING_ORDER_FIELDS = {"accepted_power", "individual_spread", "price_group"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_dataset(directory: Path, parameters: DayAheadOrdersParameters) -> AtlasDataset:
    if not directory.exists():
        pytest.skip(f"Semi peak dataset not found: {directory}")
    data = AtlasDataset.from_directory(directory)
    data.set_frequency_all(parameters.temporal.timestep, inplace=True)
    return data


def _normalize(value: object) -> Hashable:
    """Make an attribute value hashable and comparable: references by name, floats rounded."""
    if isinstance(value, BusinessModel):
        return value.name
    if isinstance(value, float):
        return round(value, FLOAT_DECIMALS)
    return value  # type: ignore[return-value]


def _order_key(order: Order) -> tuple:
    """Content of an order: the fields of ``Order`` except its name and the clearing results."""
    return tuple(
        (field, _normalize(getattr(order, field)))
        for field in Order.model_fields
        if field != "name" and field not in CLEARING_ORDER_FIELDS
    )


def _coupling_key(coupling: OrderCoupling) -> tuple:
    """Content of a coupling: its own fields except name, and the content of its orders.

    Orders are compared unordered, except the parent (first order) of a parent-children coupling.
    ``complement_energy`` is only used by complement couplings: unset (None) is taken as 0.
    """
    fields = tuple(
        (field, _normalize(getattr(coupling, field)))
        for field in OrderCoupling.model_fields
        if field not in ("name", "orders", "complement_energy")
    )
    complement_energy = _normalize(coupling.complement_energy or 0.0)

    order_keys = [_order_key(o) for o in coupling.orders]
    if coupling.coupling_type == CouplingType.PARENT_CHILDREN:
        orders = (order_keys[0], *sorted(order_keys[1:], key=repr))
    else:
        orders = tuple(sorted(order_keys, key=repr))
    return fields + (("complement_energy", complement_energy), ("orders", orders))


def _assert_same_content(generated: Iterable[tuple], expected: Iterable[tuple], label: str) -> None:
    generated_count, expected_count = Counter(generated), Counter(expected)
    missing = expected_count - generated_count
    unexpected = generated_count - expected_count
    assert not missing and not unexpected, (
        f"Generated {label} do not match expected ones.\n"
        f"{missing.total()} expected not generated:\n" + "\n".join(map(str, missing)) + "\n"
        f"{unexpected.total()} generated not expected:\n" + "\n".join(map(str, unexpected))
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def semi_peak_parameters() -> DayAheadOrdersParameters:
    return DayAheadOrdersParameters.model_validate(SEMI_PEAK_PARAMS_DICT)


@pytest.fixture(scope="module")
def semi_peak_result(semi_peak_parameters) -> StepResult:
    input_data = _load_dataset(SEMI_PEAK_INPUT_DIR, semi_peak_parameters)
    steps_result = DayAheadOrdersResult(DayAheadOrdersInputDataset(input_data, semi_peak_parameters))
    orders_time = generate_datetimes(
        semi_peak_parameters.temporal.start_date,
        semi_peak_parameters.penultimate_date,
        semi_peak_parameters.temporal.timestep,
    )

    units = [t for t in steps_result.thermal if t.strategy == ThermalStrategy.INTERMEDIATE]
    assert units, "No intermediate thermal unit in the semi peak input dataset"

    result = StepResult()
    for unit in units:
        unit_orders, unit_couplings = ThermalIntermediateLoadOrders(orders_time, semi_peak_parameters).formulate(unit)
        result.orders.extend(unit_orders)
        result.order_couplings.extend(unit_couplings)
    return result


@pytest.fixture(scope="module")
def semi_peak_expected(semi_peak_parameters) -> AtlasDataset:
    return _load_dataset(SEMI_PEAK_OUTPUT_DIR, semi_peak_parameters)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestThermalSemiPeakOrders:
    def test_order_names_are_unique(self, semi_peak_result):
        names = [o.name for o in semi_peak_result.orders]
        assert len(names) == len(set(names))

    def test_coupling_names_are_unique(self, semi_peak_result):
        names = [c.name for c in semi_peak_result.order_couplings]
        assert len(names) == len(set(names))

    def test_orders_match_expected(self, semi_peak_result, semi_peak_expected):
        _assert_same_content(
            map(_order_key, semi_peak_result.orders), map(_order_key, semi_peak_expected.order), "orders"
        )

    def test_couplings_match_expected(self, semi_peak_result, semi_peak_expected):
        _assert_same_content(
            map(_coupling_key, semi_peak_result.order_couplings),
            map(_coupling_key, semi_peak_expected.order_coupling),
            "order couplings",
        )
