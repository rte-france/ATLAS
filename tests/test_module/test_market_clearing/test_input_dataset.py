"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Shape assertions on the MarketClearing input dataset built from the local fixture.
Acts as a regression anchor for the upcoming input_dataset refactor.
"""

from collections import Counter

from atlas.enums import CouplingType
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.input_objects.market_area import INITIAL_MAX_PRICE, INITIAL_MIN_PRICE
from atlas.modules.market_clearing.input_objects.market_border import get_max_flow, get_min_flow


class TestTimesAndMode:
    def test_times_cover_horizon_at_parameter_step(self, input_dataset: MarketClearingInputDataset) -> None:
        params = input_dataset.parameters
        expected_steps = (params.temporal.end_date - params.temporal.start_date) // params.temporal.timestep

        assert len(input_dataset.times) == expected_steps
        assert input_dataset.times[0] == params.temporal.start_date
        assert input_dataset.times[-1] == params.temporal.end_date - params.temporal.timestep

    def test_atc_mode_has_no_flow_based_objects(self, input_dataset: MarketClearingInputDataset) -> None:
        assert input_dataset.is_atc
        assert input_dataset.mc_critical_branches == {}
        assert input_dataset.mc_market_area_ptdfs == {}


class TestMarketAreas:
    def test_each_market_area_links_to_a_known_control_block(self, input_dataset: MarketClearingInputDataset) -> None:
        for market_area in input_dataset.mc_market_areas.values():
            assert market_area.control_block.name in input_dataset.mc_control_blocks

    def test_market_area_orders_match_global_orders_filtered_by_area(
        self, input_dataset: MarketClearingInputDataset
    ) -> None:
        for area_name, market_area in input_dataset.mc_market_areas.items():
            expected_order_names = {
                order_name
                for order_name, order in input_dataset.mc_orders.items()
                if order.market_area.name == area_name
            }
            assert set(market_area.mc_orders) == expected_order_names

    def test_price_bounds_are_consistent_over_horizon(self, input_dataset: MarketClearingInputDataset) -> None:
        for market_area in input_dataset.mc_market_areas.values():
            for time in input_dataset.times:
                max_price = (
                    market_area.maximum_price.get_value(time) if market_area.maximum_price else INITIAL_MAX_PRICE
                )
                min_price = (
                    market_area.minimum_price.get_value(time) if market_area.minimum_price else INITIAL_MIN_PRICE
                )
                assert max_price > min_price


class TestOrders:
    def test_every_order_belongs_to_an_imported_market_area(self, input_dataset: MarketClearingInputDataset) -> None:
        known_areas = set(input_dataset.mc_market_areas)
        for order in input_dataset.mc_orders.values():
            assert order.market_area.name in known_areas

    def test_every_order_starts_within_the_optimization_horizon(
        self, input_dataset: MarketClearingInputDataset
    ) -> None:
        times = set(input_dataset.times)
        for order in input_dataset.mc_orders.values():
            assert order.start_date in times
            assert order.time_index == input_dataset.times.index(order.start_date)


class TestOrderCouplings:
    def test_linked_orders_have_link_id_pointing_to_their_coupling(
        self, input_dataset: MarketClearingInputDataset
    ) -> None:
        linking_types = {CouplingType.IDENTICAL_VOLUME, CouplingType.IDENTICAL_RATIO, CouplingType.COMPLEMENT}
        for coupling in input_dataset.mc_order_couplings.values():
            if coupling.coupling_type not in linking_types:
                continue
            for order in coupling.orders:
                if order.name not in input_dataset.mc_orders:
                    continue
                mc_order = input_dataset.mc_orders[order.name]
                assert mc_order.is_linked
                assert mc_order.link_id == coupling.name

    def test_parent_children_couplings_mark_first_order_as_parent(
        self, input_dataset: MarketClearingInputDataset
    ) -> None:
        parent_count_per_order: Counter[str] = Counter()
        for coupling in input_dataset.mc_order_couplings.values():
            if coupling.coupling_type != CouplingType.PARENT_CHILDREN or not coupling.orders:
                continue
            parent_name = coupling.orders[0].name
            parent_count_per_order[parent_name] += 1

            parent = input_dataset.mc_orders.get(parent_name)
            assert parent is not None
            assert parent.is_parent
            assert parent.order_coupling_parent_ids is not None
            assert coupling.name in parent.order_coupling_parent_ids

            for child in coupling.orders:
                if child.name not in input_dataset.mc_orders:
                    continue
                mc_child = input_dataset.mc_orders[child.name]
                assert mc_child.is_in_parent_child_coupling
                assert mc_child.parent_child_id == coupling.name

        for order_name, count in parent_count_per_order.items():
            order = input_dataset.mc_orders[order_name]
            assert len(order.order_coupling_parent_ids) == count

    def test_exclusion_couplings_mark_orders_as_mutually_excluding(
        self, input_dataset: MarketClearingInputDataset
    ) -> None:
        for coupling in input_dataset.mc_order_couplings.values():
            if coupling.coupling_type != CouplingType.EXCLUSION:
                continue
            for order in coupling.orders:
                if order.name not in input_dataset.mc_orders:
                    continue
                mc_order = input_dataset.mc_orders[order.name]
                assert mc_order.is_mutually_excluding
                assert mc_order.requires_status_variable

    def test_couplings_with_fewer_than_two_feasible_orders_are_dropped(
        self, input_dataset: MarketClearingInputDataset
    ) -> None:
        for coupling in input_dataset.mc_order_couplings.values():
            assert coupling.orders is not None
            assert len(coupling.orders) >= 2


class TestMarketBorders:
    def test_border_endpoints_are_imported_market_areas(self, input_dataset: MarketClearingInputDataset) -> None:
        known_areas = set(input_dataset.mc_market_areas)
        for border in input_dataset.mc_market_borders.values():
            assert border.uphill_market_area.name in known_areas
            assert border.downhill_market_area.name in known_areas

    def test_border_flow_bounds_are_consistent(self, input_dataset: MarketClearingInputDataset) -> None:
        for border in input_dataset.mc_market_borders.values():
            for time in input_dataset.times:
                assert get_max_flow(border, time) >= get_min_flow(border, time)
