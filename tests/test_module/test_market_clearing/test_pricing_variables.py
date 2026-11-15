"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Temporal variables of the pricing model: the time index of the price group families, and the
second and third pricing attempts, which the test datasets never reach through `Pricing.compute`
(their first attempt is feasible) and the LP comparison therefore does not cover.
"""

import pendulum
import pytest

from atlas.modules.market_clearing.data_classes import ClearingOutputs, PriceGroup
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.parameters import MarketClearingParameters
from atlas.modules.market_clearing.phases._helpers import times_by_group, times_by_group_pair
from atlas.modules.market_clearing.phases.clearing import Clearing
from atlas.modules.market_clearing.phases.exchanges_fixing import ExchangesFixing
from atlas.modules.market_clearing.phases.pricing import Pricing, second_attempt

T0 = pendulum.datetime(2028, 9, 27)
T1 = T0.add(hours=1)
T2 = T0.add(hours=2)


class TestTimesByGroup:
    def test_a_group_id_only_holds_the_times_it_exists_at(self) -> None:
        price_groups = {
            T1: [PriceGroup(id=0, time=T1), PriceGroup(id=2, time=T1)],
            T0: [PriceGroup(id=0, time=T0)],
            T2: [PriceGroup(id=2, time=T2)],
        }

        assert times_by_group(price_groups) == {0: [T0, T1], 2: [T1, T2]}

    def test_pairs_follow_the_group_order_of_each_time(self) -> None:
        price_groups = {
            T0: [PriceGroup(id=0, time=T0)],
            T1: [PriceGroup(id=0, time=T1), PriceGroup(id=1, time=T1), PriceGroup(id=2, time=T1)],
            T2: [PriceGroup(id=0, time=T2), PriceGroup(id=1, time=T2)],
        }

        assert times_by_group_pair(price_groups) == {(0, 1): [T1, T2], (0, 2): [T1], (1, 2): [T1]}


@pytest.fixture(scope="module")
def clearing_outputs(
    input_dataset: MarketClearingInputDataset, parameters: MarketClearingParameters
) -> ClearingOutputs:
    # Do not overwrite the LPs exported by the module run, which the LP comparison reads
    parameters = parameters.evolve(solver=parameters.solver.evolve(export_lp=False))
    clearing = Clearing(input_dataset, parameters)
    clearing.compute()
    exchanges_fixing = ExchangesFixing(input_dataset, parameters)
    exchanges_fixing.compute(clearing.get_local_balances())
    return ClearingOutputs(
        saturated_critical_branch=clearing.get_saturated_critical_branch(),
        border_exchanges=exchanges_fixing.get_border_exchanges(),
        local_balances=clearing.get_local_balances(),
        accepted_powers=clearing.get_accepted_powers(),
    )


@pytest.fixture
def pricing(
    input_dataset: MarketClearingInputDataset, parameters: MarketClearingParameters, clearing_outputs: ClearingOutputs
) -> Pricing:
    pricing = Pricing(input_dataset, parameters, clearing_outputs)
    pricing.build_first()
    return pricing


def _is_relaxed(pricing: Pricing, constraint_name: str) -> bool:
    bounds = pricing.model.get_constraint_bounds(constraint_name)
    return (bounds.lower_bound, bounds.upper_bound) == (float("-inf"), float("inf"))


class TestFirstAttempt:
    def test_records_the_constraints_the_later_attempts_relax(self, pricing: Pricing) -> None:
        relaxable = pricing.relaxable

        for constraint_name in (
            relaxable.null_marginal_order
            + relaxable.linked_orders_surplus
            + relaxable.parent_child_surplus
            + relaxable.order_surplus
        ):
            assert constraint_name in pricing.model.constraints
            assert not _is_relaxed(pricing, constraint_name)

    def test_every_price_group_gets_a_price_at_its_time(self, pricing: Pricing) -> None:
        for time, price_groups in pricing.price_groups.items():
            for price_group in price_groups:
                assert time in pricing.variables.price[price_group.id]
                assert time in pricing.variables.positive_price[price_group.id]
                assert time in pricing.variables.negative_price[price_group.id]


class TestSecondAttempt:
    def test_price_variables_are_tightened_to_the_group_bounds(self, pricing: Pricing) -> None:
        pricing.build_second()

        for price_group in (group for groups in pricing.price_groups.values() for group in groups):
            price = pricing.variables.price[price_group.id][price_group.time]
            assert (price.lb(), price.ub()) == (price_group.min_price, price_group.max_price)

    def test_worst_rejected_orders_follow_the_price_groups(self, pricing: Pricing) -> None:
        rejection = second_attempt.build_variables(pricing)

        group_times = times_by_group(pricing.price_groups)
        assert {group_id: family.model_times for group_id, family in rejection.worst_rejected_sale.items()} == (
            group_times
        )
        assert {group_id: family.model_times for group_id, family in rejection.worst_rejected_buy.items()} == (
            group_times
        )

    def test_relaxes_the_null_surplus_of_the_marginal_orders(self, pricing: Pricing) -> None:
        pricing.build_second()

        for constraint_name in pricing.relaxable.null_marginal_order:
            assert _is_relaxed(pricing, constraint_name)


class TestThirdAttempt:
    def test_relaxes_every_recorded_surplus_constraint(self, pricing: Pricing) -> None:
        pricing.build_second()
        pricing.build_third()

        relaxable = pricing.relaxable
        surplus_constraints = relaxable.linked_orders_surplus + relaxable.parent_child_surplus + relaxable.order_surplus
        assert surplus_constraints
        for constraint_name in surplus_constraints:
            assert _is_relaxed(pricing, constraint_name)

    def test_relaxed_model_prices_every_market_area(self, pricing: Pricing) -> None:
        pricing.build_second()
        pricing.build_third()

        pricing.model.solve()

        assert pricing.model.has_solution
        market_prices = pricing.get_market_prices()
        assert market_prices.keys() == pricing.input_dataset.market_areas.keys()
        for prices in market_prices.values():
            assert prices.index == pricing.input_dataset.times
