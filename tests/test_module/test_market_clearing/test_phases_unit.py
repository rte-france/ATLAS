"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Unit tests for the pure algorithms of the market_clearing phases (price groups, neighbour
detection, order-link resolution, marginal fixing, order feasibility) — PR-1 of the code
quality audit in issue #296. These run without a solver: Pricing's algorithmic methods are
exercised via the unbound-method technique against a lightweight duck-typed stand-in for
`self`, since `Pricing.__init__` otherwise requires a live OR-Tools model.
"""

import pendulum
import pytest

import atlas.modules.market_clearing.constants as constants
from atlas.enums import CouplingType, OrderType, Product
from atlas.math.timeseries import Timeseries
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.input_objects.order import OrderMC
from atlas.modules.market_clearing.order_links import OrderLinkResolver
from atlas.modules.market_clearing.parameters import MarketClearingParameters
from atlas.modules.market_clearing.phases.marginal_fixing import MarginalFixing
from atlas.modules.market_clearing.phases.pricing import Pricing, third_pass
from atlas.modules.market_clearing.price_group import PriceGroup
from tests.test_module.test_market_clearing.factories import (
    make_market_area,
    make_market_border,
    make_order,
    make_order_coupling,
    make_plain_market_area,
    make_plain_order,
)

ONE_HOUR = pendulum.duration(hours=1)


class _FakeOptimisationModel:
    """Duck-typed stand-in for the `OptimisationModel` a real `Pricing` composes as `self.model` —
    returns a plain float placeholder for any variable, since these tests only check whether a
    variable/constraint was created and, for arithmetic, don't care about its exact value."""

    def __init__(self):
        self._variables: dict = {}

    def add_continuous_variable(self, name, lower_bound=float("-inf"), upper_bound=float("inf")):
        return self._variables.setdefault(name, 0.0)

    def get_variable(self, name):
        return self._variables.setdefault(name, 0.0)


class _PricingAlgorithms:
    """Duck-typed stand-in for `Pricing` exposing only its solver-free algorithms.

    `Pricing.__init__` builds a live OR-Tools model and immediately runs these methods as a
    side effect, which makes the real class impractical to unit test in isolation. Binding the
    unbound methods here runs the exact same production code against a minimal fake `input_dataset`
    / `parameters`, without needing a solver.
    """

    def __init__(self, input_dataset, parameters, clearing_border_exchanges=None, clearing_accepted_powers=None):
        self.input_dataset = input_dataset
        self.parameters = parameters
        self.clearing_border_exchanges = clearing_border_exchanges or {}
        self.clearing_accepted_powers = clearing_accepted_powers or {}
        self.saturated_critical_branch = {}
        self.dict_linked_orders: dict = {}
        self._full_link_id_by_order: dict = {}
        self.model = _FakeOptimisationModel()

    # Each wrapper below calls the real, unbound `Pricing` method (or, for the third pricing pass,
    # the plain `third_pass` function it now delegates to) against this stand-in — mypy doesn't
    # accept `self: _PricingAlgorithms` where `Pricing`/`_PricingPhase` is expected, hence the ignores.
    def get_market_area_neighbours(self, mc_market_area_name):
        return Pricing.get_market_area_neighbours(self, mc_market_area_name)  # type: ignore[arg-type]

    def propagate_through_unsaturated(self, mc_market_area, time_index, area_price_group, price_group):
        return Pricing.propagate_through_unsaturated(  # type: ignore[arg-type]
            self, mc_market_area, time_index, area_price_group, price_group
        )

    def create_price_groups(self):
        return Pricing.create_price_groups(self)  # type: ignore[arg-type]

    def is_neighbour(self, price_group, other_price_group):
        return Pricing.is_neighbour(self, price_group, other_price_group)  # type: ignore[arg-type]

    def compute_price_bounds(self, price_group, pricing_type):
        return Pricing.compute_price_bounds(self, price_group, pricing_type)  # type: ignore[arg-type]

    def compute_opposite_delta_p(self):
        return third_pass.compute_opposite_delta_p(self)  # type: ignore[arg-type]

    def create_delta_price_pc_variables(self, opposite_delta_p_dict):
        return third_pass.create_delta_price_pc_variables(self, opposite_delta_p_dict)  # type: ignore[arg-type]


class _FakeInputDataset:
    """Duck-typed stand-in for `MarketClearingInputDataset` carrying only the attributes the
    Pricing algorithms read."""

    def __init__(
        self, times, is_atc=True, mc_market_areas=None, mc_market_borders=None, mc_orders=None, mc_order_couplings=None
    ):
        self.times = times
        self.is_atc = is_atc
        self.mc_market_areas = mc_market_areas or {}
        self.mc_market_borders = mc_market_borders or {}
        self.mc_orders = mc_orders or {}
        self.mc_order_couplings = mc_order_couplings or {}


class TestOrderIsFeasible:
    """`OrderMC.is_feasible` — every rejection branch, using the real day-ahead `parameters`
    and `input_dataset.times` fixtures so bound values reflect an actual configuration."""

    def test_accepts_order_matching_every_criterion(self, parameters: MarketClearingParameters, input_dataset) -> None:
        market_area = make_plain_market_area("ma_a")
        order = make_plain_order(
            "o1",
            market_area,
            product=parameters.market,
            start_date=input_dataset.times[0],
            end_date=input_dataset.times[0] + ONE_HOUR,
            execution_date=parameters.temporal.execution_date,
        )
        assert OrderMC.is_feasible(order, input_dataset.times, parameters)

    def test_rejects_order_missing_a_required_date(self, parameters: MarketClearingParameters, input_dataset) -> None:
        market_area = make_plain_market_area("ma_a")
        order = make_plain_order("o1", market_area, product=None)
        assert not OrderMC.is_feasible(order, input_dataset.times, parameters)

    def test_rejects_wrong_product(self, parameters: MarketClearingParameters, input_dataset) -> None:
        market_area = make_plain_market_area("ma_a")
        wrong_product = Product.Intraday if parameters.market != Product.Intraday else Product.DayAhead
        order = make_plain_order(
            "o1",
            market_area,
            product=wrong_product,
            start_date=input_dataset.times[0],
            end_date=input_dataset.times[0] + ONE_HOUR,
            execution_date=parameters.temporal.execution_date,
        )
        assert not OrderMC.is_feasible(order, input_dataset.times, parameters)

    def test_rejects_start_date_off_the_optimization_grid(
        self, parameters: MarketClearingParameters, input_dataset
    ) -> None:
        market_area = make_plain_market_area("ma_a")
        order = make_plain_order(
            "o1",
            market_area,
            product=parameters.market,
            start_date=input_dataset.times[0] + pendulum.duration(minutes=30),
            end_date=input_dataset.times[0] + pendulum.duration(minutes=90),
            execution_date=parameters.temporal.execution_date,
        )
        assert not OrderMC.is_feasible(order, input_dataset.times, parameters)

    def test_rejects_end_date_beyond_the_optimization_horizon(
        self, parameters: MarketClearingParameters, input_dataset
    ) -> None:
        market_area = make_plain_market_area("ma_a")
        order = make_plain_order(
            "o1",
            market_area,
            product=parameters.market,
            start_date=input_dataset.times[-1],
            end_date=parameters.temporal.end_date + ONE_HOUR,
            execution_date=parameters.temporal.execution_date,
        )
        assert not OrderMC.is_feasible(order, input_dataset.times, parameters)

    def test_rejects_execution_date_outside_tolerance(
        self, parameters: MarketClearingParameters, input_dataset
    ) -> None:
        market_area = make_plain_market_area("ma_a")
        too_early = parameters.temporal.execution_date - pendulum.duration(
            minutes=parameters.execution_datetime_tolerance + 60
        )
        order = make_plain_order(
            "o1",
            market_area,
            product=parameters.market,
            start_date=input_dataset.times[0],
            end_date=input_dataset.times[0] + ONE_HOUR,
            execution_date=too_early,
        )
        assert not OrderMC.is_feasible(order, input_dataset.times, parameters)

    def test_rejects_duration_shorter_than_the_timestep(
        self, parameters: MarketClearingParameters, input_dataset
    ) -> None:
        market_area = make_plain_market_area("ma_a")
        order = make_plain_order(
            "o1",
            market_area,
            product=parameters.market,
            start_date=input_dataset.times[0],
            end_date=input_dataset.times[0] + pendulum.duration(minutes=30),
            execution_date=parameters.temporal.execution_date,
        )
        assert parameters.temporal.timestep >= pendulum.duration(minutes=30)
        assert not OrderMC.is_feasible(order, input_dataset.times, parameters)

    def test_rejects_market_area_excluded_by_selection(
        self, parameters: MarketClearingParameters, input_dataset
    ) -> None:
        restricted_parameters = parameters.model_copy(update={"market_area_names": ["some_other_area"]})
        market_area = make_plain_market_area("ma_a")
        order = make_plain_order(
            "o1",
            market_area,
            product=parameters.market,
            start_date=input_dataset.times[0],
            end_date=input_dataset.times[0] + ONE_HOUR,
            execution_date=parameters.temporal.execution_date,
        )
        assert not OrderMC.is_feasible(order, input_dataset.times, restricted_parameters)


class TestGetOrdersTimeIndex:
    """`MarketClearingInputDataset.get_orders` — time_index assignment for a feasible order."""

    def test_time_index_matches_the_order_start_date_position(
        self, parameters: MarketClearingParameters, input_dataset
    ) -> None:
        fake_dataset = MarketClearingInputDataset.__new__(MarketClearingInputDataset)
        fake_dataset.times = input_dataset.times
        fake_dataset.parameters = parameters

        market_area = make_plain_market_area("ma_a")
        start_date = input_dataset.times[3]
        order = make_plain_order(
            "o1",
            market_area,
            product=parameters.market,
            start_date=start_date,
            end_date=start_date + ONE_HOUR,
            execution_date=parameters.temporal.execution_date,
        )

        mc_orders = fake_dataset.get_orders([order], {})

        assert mc_orders["o1"].time_index == input_dataset.times.index(start_date)


class TestCreatePriceGroups:
    """`Pricing.create_price_groups` / `propagate_through_unsaturated` on a 3-zone ATC network
    (A - B - C, two borders, no direct A-C border)."""

    def _bounded_flow(self, time, value):
        return Timeseries.from_index(time, ONE_HOUR, time, value)

    def _build_network(self, times, ab_flow, bc_flow, max_flow=100.0):
        area_a = make_market_area("ma_a", ONE_HOUR, times)
        area_b = make_market_area("ma_b", ONE_HOUR, times)
        area_c = make_market_area("ma_c", ONE_HOUR, times)
        border_ab = make_market_border(
            "ab",
            area_a,
            area_b,
            ONE_HOUR,
            times,
            maximum_flow=self._bounded_flow(times[0], max_flow),
            minimum_flow=self._bounded_flow(times[0], -max_flow),
        )
        border_bc = make_market_border(
            "bc",
            area_b,
            area_c,
            ONE_HOUR,
            times,
            maximum_flow=self._bounded_flow(times[0], max_flow),
            minimum_flow=self._bounded_flow(times[0], -max_flow),
        )
        input_dataset = _FakeInputDataset(
            times=times,
            mc_market_areas={"ma_a": area_a, "ma_b": area_b, "ma_c": area_c},
            mc_market_borders={"ab": border_ab, "bc": border_bc},
        )
        exchanges = {("ab", 0): ab_flow, ("bc", 0): bc_flow}
        return input_dataset, exchanges

    @pytest.mark.xfail(
        reason=(
            "ATLAS-296 (new finding, not in the original B1-B13 list): "
            "Pricing.get_market_area_neighbours (pricing.py) does not check that a border actually "
            "touches the queried area — for a border where the area is neither the uphill nor the "
            "downhill endpoint, it still returns `uphill_market_area` as a bogus 'neighbour'. With "
            "only 2 zones (the real day-ahead fixture) every border always touches both areas, so "
            "this is invisible there; a 3-zone chain (A-B-C, no direct A-C border) exposes it: "
            "propagating from C spuriously treats B as reachable through the unrelated A-B border, "
            "merging groups it shouldn't. Needs business validation before a fix lands in PR-2."
        ),
        strict=True,
    )
    def test_areas_merge_across_an_unsaturated_border_and_split_at_a_saturated_one(
        self, parameters: MarketClearingParameters
    ) -> None:
        times = [parameters.temporal.start_date]
        input_dataset, exchanges = self._build_network(times, ab_flow=0.0, bc_flow=100.0)
        pricing = _PricingAlgorithms(input_dataset, parameters, clearing_border_exchanges=exchanges)

        price_groups = pricing.create_price_groups()[0]

        groups_by_area = {area: frozenset(pg.market_area_names) for pg in price_groups for area in pg.market_area_names}
        assert groups_by_area["ma_a"] == frozenset({"ma_a", "ma_b"})
        assert groups_by_area["ma_c"] == frozenset({"ma_c"})

    def test_all_areas_merge_when_no_border_is_saturated(self, parameters: MarketClearingParameters) -> None:
        times = [parameters.temporal.start_date]
        input_dataset, exchanges = self._build_network(times, ab_flow=0.0, bc_flow=0.0)
        pricing = _PricingAlgorithms(input_dataset, parameters, clearing_border_exchanges=exchanges)

        price_groups = pricing.create_price_groups()[0]

        assert len(price_groups) == 1
        assert set(price_groups[0].market_area_names) == {"ma_a", "ma_b", "ma_c"}

    def test_every_area_splits_when_every_border_is_saturated(self, parameters: MarketClearingParameters) -> None:
        times = [parameters.temporal.start_date]
        input_dataset, exchanges = self._build_network(times, ab_flow=100.0, bc_flow=100.0)
        pricing = _PricingAlgorithms(input_dataset, parameters, clearing_border_exchanges=exchanges)

        price_groups = pricing.create_price_groups()[0]

        assert {frozenset(pg.market_area_names) for pg in price_groups} == {
            frozenset({"ma_a"}),
            frozenset({"ma_b"}),
            frozenset({"ma_c"}),
        }


class TestIsNeighbour:
    def _network(self, times):
        area_a = make_market_area("ma_a", ONE_HOUR, times)
        area_b = make_market_area("ma_b", ONE_HOUR, times)
        area_c = make_market_area("ma_c", ONE_HOUR, times)
        border_ab = make_market_border("ab", area_a, area_b, ONE_HOUR, times)
        border_bc = make_market_border("bc", area_b, area_c, ONE_HOUR, times)
        return _FakeInputDataset(
            times=times,
            mc_market_areas={"ma_a": area_a, "ma_b": area_b, "ma_c": area_c},
            mc_market_borders={"ab": border_ab, "bc": border_bc},
        )

    def test_groups_sharing_an_external_border_are_neighbours(self, parameters: MarketClearingParameters) -> None:
        times = [parameters.temporal.start_date]
        input_dataset = self._network(times)
        pricing = _PricingAlgorithms(input_dataset, parameters)

        group_a = PriceGroup(0, 0)
        group_a.market_area_names = ["ma_a"]
        group_bc = PriceGroup(1, 0)
        group_bc.market_area_names = ["ma_b", "ma_c"]

        assert pricing.is_neighbour(group_a, group_bc)

    def test_groups_without_a_shared_border_are_not_neighbours(self, parameters: MarketClearingParameters) -> None:
        times = [parameters.temporal.start_date]
        input_dataset = self._network(times)
        pricing = _PricingAlgorithms(input_dataset, parameters)

        group_a = PriceGroup(0, 0)
        group_a.market_area_names = ["ma_a"]
        group_c = PriceGroup(1, 0)
        group_c.market_area_names = ["ma_c"]

        assert not pricing.is_neighbour(group_a, group_c)


class TestOrderLinkResolverLinkedBids:
    """`OrderLinkResolver` — a simple, non-circular IDENTICAL_VOLUME coupling.

    ATLAS-296 PR-5 step 1: this logic used to live on `Pricing` and mutate the shared `OrderMC`
    instances directly (`full_link_id`, `circular_pc_id`); it's now a plain, solver-free class
    returning an immutable result, so these tests no longer need the `_PricingAlgorithms` harness.
    """

    def test_identical_volume_orders_land_in_the_same_linked_set(self, parameters: MarketClearingParameters) -> None:
        times = [parameters.temporal.start_date]
        area = make_market_area("ma_a", ONE_HOUR, times)
        order_1 = make_order("o1", area, ONE_HOUR, start_date=times[0], end_date=times[0] + ONE_HOUR, is_linked=True)
        order_2 = make_order("o2", area, ONE_HOUR, start_date=times[0], end_date=times[0] + ONE_HOUR, is_linked=True)
        coupling = make_order_coupling("idv_1", CouplingType.IDENTICAL_VOLUME, [order_1, order_2])

        order_links = OrderLinkResolver({"o1": order_1, "o2": order_2}, {"idv_1": coupling}).resolve()

        assert len(order_links.linked_orders) == 1
        (linked_orders,) = order_links.linked_orders.values()
        assert {order.name for order in linked_orders} == {"o1", "o2"}
        assert order_links.full_link_id_by_order["o1"] == order_links.full_link_id_by_order["o2"]

    def test_linked_order_pulls_in_its_circular_parent_child_set(self, parameters: MarketClearingParameters) -> None:
        """ATLAS-296 B2 regression: `circular_pc_id` (not `circular_PC_id`) must resolve, and the
        lookup must use the order actually being linked, not a variable leaked from an earlier
        unrelated loop. The circular precondition is injected directly on the resolver's internal
        state rather than produced by `_get_circular_parent_child_sets`, since building a
        genuinely circular PC chain hits a separate, unrelated infinite-recursion bug in
        `_get_circular_children`.
        """
        times = [parameters.temporal.start_date]
        area = make_market_area("ma_a", ONE_HOUR, times)
        order_1 = make_order("o1", area, ONE_HOUR, start_date=times[0], end_date=times[0] + ONE_HOUR, is_linked=True)
        order_2 = make_order("o2", area, ONE_HOUR, start_date=times[0], end_date=times[0] + ONE_HOUR, is_linked=True)
        circular_child = make_order("circular_child", area, ONE_HOUR, start_date=times[0], end_date=times[0] + ONE_HOUR)
        coupling = make_order_coupling("idv_1", CouplingType.IDENTICAL_VOLUME, [order_1, order_2])

        resolver = OrderLinkResolver(
            {"o1": order_1, "o2": order_2, "circular_child": circular_child}, {"idv_1": coupling}
        )
        resolver._circular_pc_id["o1"] = 0

        linked_orders = resolver._compute_linked_bids_sets({0: [circular_child]})

        assert len(linked_orders) == 1
        (orders,) = linked_orders.values()
        assert {order.name for order in orders} == {"o1", "o2", "circular_child"}


class TestOrderLinkResolverParentChild:
    """`OrderLinkResolver` — a simple, non-circular PARENT_CHILDREN coupling (the child is not
    itself a parent elsewhere)."""

    def test_non_circular_parent_child_link_is_not_flagged_circular(self, parameters: MarketClearingParameters) -> None:
        times = [parameters.temporal.start_date]
        area = make_market_area("ma_a", ONE_HOUR, times)
        parent = make_order("parent", area, ONE_HOUR, start_date=times[0], end_date=times[0] + ONE_HOUR, is_parent=True)
        child = make_order("child", area, ONE_HOUR, start_date=times[0], end_date=times[0] + ONE_HOUR)
        coupling = make_order_coupling("pc_1", CouplingType.PARENT_CHILDREN, [parent, child])

        order_links = OrderLinkResolver({"parent": parent, "child": child}, {"pc_1": coupling}).resolve()

        assert order_links.circular_pc_id_by_order == {}

    def test_parent_and_child_are_assigned_the_same_full_pc_id(self, parameters: MarketClearingParameters) -> None:
        times = [parameters.temporal.start_date]
        area = make_market_area("ma_a", ONE_HOUR, times)
        parent = make_order("parent", area, ONE_HOUR, start_date=times[0], end_date=times[0] + ONE_HOUR, is_parent=True)
        child = make_order("child", area, ONE_HOUR, start_date=times[0], end_date=times[0] + ONE_HOUR)
        coupling = make_order_coupling("pc_1", CouplingType.PARENT_CHILDREN, [parent, child])

        order_links = OrderLinkResolver({"parent": parent, "child": child}, {"pc_1": coupling}).resolve()

        assert order_links.full_pc_id_by_order["parent"] == order_links.full_pc_id_by_order["child"]
        assert order_links.child_id_by_order["child"] == "0"


class TestMarginalFixingUpdateAcceptedPower:
    """`MarginalFixing.update_accepted_power` — redistribution of marginal volume between a
    sell and a buy order priced exactly at the spot price."""

    def _build_marginal_fixing(self, parameters, area, orders, accepted_powers):
        input_dataset = _FakeInputDataset(times=[parameters.temporal.start_date], mc_orders=orders)
        marginal_fixing = MarginalFixing(input_dataset, parameters)
        marginal_fixing.accepted_powers = dict(accepted_powers)
        return marginal_fixing

    def test_marginal_sell_order_is_pushed_to_qmax_when_demand_absorbs_all_marginal_sales(
        self, parameters: MarketClearingParameters
    ) -> None:
        times = [parameters.temporal.start_date]
        area = make_market_area("ma_a", ONE_HOUR, times)
        spot_price = 50.0
        sell = make_order(
            "sell",
            area,
            ONE_HOUR,
            order_type=OrderType.Sell,
            price=spot_price,
            qmin=0.0,
            qmax=10.0,
            start_date=times[0],
            end_date=times[0] + ONE_HOUR,
        )
        buy = make_order(
            "buy",
            area,
            ONE_HOUR,
            order_type=OrderType.Buy,
            price=spot_price,
            qmin=0.0,
            qmax=20.0,
            start_date=times[0],
            end_date=times[0] + ONE_HOUR,
        )
        marginal_fixing = self._build_marginal_fixing(
            parameters,
            area,
            {"sell": sell, "buy": buy},
            {("ma_a", "sell"): 0.0, ("ma_a", "buy"): 5.0},
        )

        marginal_fixing.update_accepted_power("ma_a", times[0], spot_price)

        assert marginal_fixing.accepted_powers["ma_a", "sell"] == sell.qmax
        assert marginal_fixing.accepted_powers["ma_a", "buy"] == 15.0

    def test_orders_off_the_spot_price_are_ignored(self, parameters: MarketClearingParameters) -> None:
        times = [parameters.temporal.start_date]
        area = make_market_area("ma_a", ONE_HOUR, times)
        spot_price = 50.0
        off_price_sell = make_order(
            "sell",
            area,
            ONE_HOUR,
            order_type=OrderType.Sell,
            price=spot_price + 1,
            qmin=0.0,
            qmax=10.0,
            start_date=times[0],
            end_date=times[0] + ONE_HOUR,
        )
        marginal_fixing = self._build_marginal_fixing(
            parameters, area, {"sell": off_price_sell}, {("ma_a", "sell"): 0.0}
        )

        marginal_fixing.update_accepted_power("ma_a", times[0], spot_price)

        assert marginal_fixing.accepted_powers["ma_a", "sell"] == 0.0


class TestCreateOppositeDeltaP:
    """`Pricing.compute_opposite_delta_p` — ATLAS-296 B5: the per-parent-child-group aggregate is
    the sentinel `None` when no order in the group was accepted, and a real value otherwise. The
    old code initialized the aggregate to `0.0` and gated on `isinstance(x, int)`, which is
    always true for a `float` — the sentinel never actually distinguished the two cases. This
    method is only reachable via `build_third`, the LP fallback for an infeasible first and
    second pass; neither test dataset's optimum requires it, so the LP-comparison fixtures never
    exercise it.
    """

    def _build_parent_child_pricing(self, parameters, accepted_powers):
        times = [parameters.temporal.start_date]
        area = make_market_area("ma_a", ONE_HOUR, times)
        parent = make_order(
            "parent",
            area,
            ONE_HOUR,
            price=50.0,
            start_date=times[0],
            end_date=times[0] + ONE_HOUR,
            is_parent=True,
            group_index=0,
            time_index=0,
        )
        child = make_order(
            "child",
            area,
            ONE_HOUR,
            price=40.0,
            start_date=times[0],
            end_date=times[0] + ONE_HOUR,
            group_index=0,
            time_index=0,
        )
        coupling = make_order_coupling("pc_1", CouplingType.PARENT_CHILDREN, [parent, child])
        input_dataset = _FakeInputDataset(
            times=times,
            mc_orders={"parent": parent, "child": child},
            mc_order_couplings={"pc_1": coupling},
        )
        pricing = _PricingAlgorithms(input_dataset, parameters, clearing_accepted_powers=accepted_powers)
        order_links = OrderLinkResolver(input_dataset.mc_orders, input_dataset.mc_order_couplings).resolve()
        pricing.dict_linked_orders = order_links.linked_orders
        pricing.dict_parent_child_orders = order_links.parent_child_orders
        pricing._full_link_id_by_order = order_links.full_link_id_by_order
        return pricing

    def test_no_accepted_order_gives_the_none_sentinel(self, parameters: MarketClearingParameters) -> None:
        pricing = self._build_parent_child_pricing(parameters, {("ma_a", "parent"): 0.0, ("ma_a", "child"): 0.0})

        (value,) = pricing.compute_opposite_delta_p().values()

        assert value is None

    def test_an_accepted_order_gives_a_real_value(self, parameters: MarketClearingParameters) -> None:
        pricing = self._build_parent_child_pricing(parameters, {("ma_a", "parent"): 10.0, ("ma_a", "child"): 0.0})

        (value,) = pricing.compute_opposite_delta_p().values()

        assert value is not None

    def test_variable_and_constraint_creation_follow_the_sentinel(self, parameters: MarketClearingParameters) -> None:
        pricing = self._build_parent_child_pricing(parameters, {("ma_a", "parent"): 10.0, ("ma_a", "child"): 0.0})
        opposite_delta_p_dict = pricing.compute_opposite_delta_p()

        pricing.create_delta_price_pc_variables(opposite_delta_p_dict)

        assert constants.delta_p_pc(next(iter(pricing.dict_parent_child_orders))) in pricing.model._variables
