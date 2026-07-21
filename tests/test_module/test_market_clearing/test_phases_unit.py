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

from atlas.enums import CouplingType, OrderType, Product
from atlas.math.timeseries import Timeseries
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.input_objects.order import OrderMC
from atlas.modules.market_clearing.parameters import MarketClearingParameters
from atlas.modules.market_clearing.phases.marginal_fixing import MarginalFixing
from atlas.modules.market_clearing.phases.pricing import Pricing
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
        self.dict_circular_children_bids: dict = {}
        self.dict_linked_orders: dict = {}

    # Each wrapper below calls the real, unbound `Pricing` method against this stand-in — mypy
    # doesn't accept `self: _PricingAlgorithms` where `Pricing` is expected, hence the ignores.
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

    def compute_linked_bids_sets(self):
        return Pricing.compute_linked_bids_sets(self)  # type: ignore[arg-type]

    def compute_parent_child_sets(self):
        return Pricing.compute_parent_child_sets(self)  # type: ignore[arg-type]

    def get_children(self, parent_orders):
        return Pricing.get_children(self, parent_orders)  # type: ignore[arg-type]

    def get_circular_children(self, mc_order_coupling, orders, processed_order_couplings):
        return Pricing.get_circular_children(  # type: ignore[arg-type]
            self, mc_order_coupling, orders, processed_order_couplings
        )

    def get_circular_parent_child_sets(self):
        return Pricing.get_circular_parent_child_sets(self)  # type: ignore[arg-type]

    def get_idv_idr_block_sets_fast(self, *args, **kwargs):
        return Pricing.get_idv_idr_block_sets_fast(self, *args, **kwargs)  # type: ignore[arg-type]


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


class TestLinkedBidsSets:
    """`compute_linked_bids_sets` — a simple, non-circular IDENTICAL_VOLUME coupling."""

    def test_identical_volume_orders_land_in_the_same_linked_set(self, parameters: MarketClearingParameters) -> None:
        times = [parameters.temporal.start_date]
        area = make_market_area("ma_a", ONE_HOUR, times)
        order_1 = make_order("o1", area, ONE_HOUR, start_date=times[0], end_date=times[0] + ONE_HOUR, is_linked=True)
        order_2 = make_order("o2", area, ONE_HOUR, start_date=times[0], end_date=times[0] + ONE_HOUR, is_linked=True)
        coupling = make_order_coupling("idv_1", CouplingType.IDENTICAL_VOLUME, [order_1, order_2])

        input_dataset = _FakeInputDataset(
            times=times,
            mc_orders={"o1": order_1, "o2": order_2},
            mc_order_couplings={"idv_1": coupling},
        )
        pricing = _PricingAlgorithms(input_dataset, parameters)
        pricing.dict_circular_children_bids = pricing.get_circular_parent_child_sets()

        linked_sets = pricing.compute_linked_bids_sets()

        assert len(linked_sets) == 1
        (linked_orders,) = linked_sets.values()
        assert {order.name for order in linked_orders} == {"o1", "o2"}
        assert order_1.full_link_id == order_2.full_link_id


class TestParentChildSets:
    """`compute_parent_child_sets` / `get_circular_children` — a simple, non-circular
    PARENT_CHILDREN coupling (the child is not itself a parent elsewhere)."""

    def test_non_circular_parent_child_link_is_not_flagged_circular(self, parameters: MarketClearingParameters) -> None:
        times = [parameters.temporal.start_date]
        area = make_market_area("ma_a", ONE_HOUR, times)
        parent = make_order("parent", area, ONE_HOUR, start_date=times[0], end_date=times[0] + ONE_HOUR, is_parent=True)
        child = make_order("child", area, ONE_HOUR, start_date=times[0], end_date=times[0] + ONE_HOUR)
        coupling = make_order_coupling("pc_1", CouplingType.PARENT_CHILDREN, [parent, child])

        input_dataset = _FakeInputDataset(
            times=times,
            mc_orders={"parent": parent, "child": child},
            mc_order_couplings={"pc_1": coupling},
        )
        pricing = _PricingAlgorithms(input_dataset, parameters)

        circular_sets = pricing.get_circular_parent_child_sets()

        assert circular_sets == {}
        assert parent.circular_pc_id is None
        assert child.circular_pc_id is None

    def test_parent_and_child_are_assigned_the_same_full_pc_id(self, parameters: MarketClearingParameters) -> None:
        times = [parameters.temporal.start_date]
        area = make_market_area("ma_a", ONE_HOUR, times)
        parent = make_order("parent", area, ONE_HOUR, start_date=times[0], end_date=times[0] + ONE_HOUR, is_parent=True)
        child = make_order("child", area, ONE_HOUR, start_date=times[0], end_date=times[0] + ONE_HOUR)
        coupling = make_order_coupling("pc_1", CouplingType.PARENT_CHILDREN, [parent, child])

        input_dataset = _FakeInputDataset(
            times=times,
            mc_orders={"parent": parent, "child": child},
            mc_order_couplings={"pc_1": coupling},
        )
        pricing = _PricingAlgorithms(input_dataset, parameters)
        pricing.dict_circular_children_bids = pricing.get_circular_parent_child_sets()
        pricing.dict_linked_orders = pricing.compute_linked_bids_sets()

        pricing.compute_parent_child_sets()

        assert parent.full_pc_id is not None
        assert parent.full_pc_id == child.full_pc_id
        assert child.child_id == "0"


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
