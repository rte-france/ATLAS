"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Shape assertions on the MarketClearing input dataset built from the local fixture.
Acts as a regression anchor for the upcoming input_dataset refactor.
"""

from collections import Counter

import pytest
from pendulum import DateTime, Duration

from atlas.enums import CouplingType
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.io_utils.parameters import DateParameters
from atlas.math.timeseries import Timeseries
from atlas.modules.market_clearing.input_dataset import MarketClearingInputDataset
from atlas.modules.market_clearing.parameters import ExchangeConstraintsType, MarketClearingParameters
from atlas.objects.market.critical_branch import CriticalBranch
from atlas.objects.market.market_area import MarketArea
from atlas.objects.market.market_area_ptdf import MarketAreaPtdf
from atlas.objects.network.node import Node
from atlas.objects.network_operator.control_block import ControlBlock


@pytest.fixture
def two_zone_fb_dataset() -> AtlasDataset:
    """A 2-zone dataset (FR/DE) with a critical branch and a PTDF in each zone, for testing
    zone-restricted Flow-Based resolution (see issue #422: these containers used to be built
    from the *unfiltered* dataset, regardless of market_area_names)."""
    cb_fr = ControlBlock(name="FR")
    cb_de = ControlBlock(name="DE")
    ma_fr = MarketArea(name="FR", control_block=cb_fr)
    ma_de = MarketArea(name="DE", control_block=cb_de)
    node_fr = Node(name="node_FR", control_block=cb_fr, market_area=ma_fr)
    node_de = Node(name="node_DE", control_block=cb_de, market_area=ma_de)

    da_ptdf = Timeseries.from_values(DateTime(2028, 1, 1), "1h", [0.5])
    ptdf_fr = MarketAreaPtdf(name="ptdf_FR", market_area=ma_fr, da_ptdf=da_ptdf)
    ptdf_de = MarketAreaPtdf(name="ptdf_DE", market_area=ma_de, da_ptdf=da_ptdf)
    branch_fr = CriticalBranch(
        name="branch_FR", uphill_node=node_fr, downhill_node=node_fr, market_area_ptdf=[ptdf_fr], node_ptdf=[]
    )
    branch_de = CriticalBranch(
        name="branch_DE", uphill_node=node_de, downhill_node=node_de, market_area_ptdf=[ptdf_de], node_ptdf=[]
    )

    return AtlasDataset(
        control_block=[cb_fr, cb_de],
        market_area=[ma_fr, ma_de],
        node=[node_fr, node_de],
        market_area_ptdf=[ptdf_fr, ptdf_de],
        critical_branch=[branch_fr, branch_de],
    )


def _fb_parameters(**overrides) -> MarketClearingParameters:
    return MarketClearingParameters(
        temporal=DateParameters(
            start_date=DateTime(2028, 1, 1),
            end_date=DateTime(2028, 1, 1, 1),
            execution_date=DateTime(2027, 12, 31, 23),
            timestep=Duration(hours=1),
        ),
        exchange_constraints_type=ExchangeConstraintsType.FB,
        **overrides,
    )


class TestZoneFiltering:
    """Regression tests for issue #422: MarketClearingInputDataset now scopes itself to the
    selected zones via AtlasDataset.include_zones instead of filtering each container by hand."""

    def test_restricted_zone_with_flow_based_does_not_crash(self, two_zone_fb_dataset: AtlasDataset) -> None:
        """Previously raised KeyError: critical_branch/market_area_ptdf were never zone-filtered,
        so a PTDF from the excluded zone had no matching entry in the (zone-filtered) market_areas."""
        input_dataset = MarketClearingInputDataset(two_zone_fb_dataset, _fb_parameters(market_area_names=["FR"]))

        assert set(input_dataset.market_areas) == {"FR"}
        assert set(input_dataset.control_blocks) == {"FR"}
        assert set(input_dataset.market_area_ptdfs) == {"ptdf_FR"}
        assert set(input_dataset.critical_branches) == {"branch_FR"}


class TestTimesAndMode:
    def test_times_cover_horizon_at_parameter_step(self, input_dataset: MarketClearingInputDataset) -> None:
        params = input_dataset.parameters
        expected_steps = (params.temporal.end_date - params.temporal.start_date) // params.temporal.timestep

        assert len(input_dataset.times) == expected_steps
        assert input_dataset.times[0] == params.temporal.start_date
        assert input_dataset.times[-1] == params.temporal.end_date - params.temporal.timestep

    def test_atc_mode_has_no_flow_based_objects(self, input_dataset: MarketClearingInputDataset) -> None:
        assert input_dataset.is_atc
        assert input_dataset.critical_branches == {}
        assert input_dataset.market_area_ptdfs == {}


class TestMarketAreas:
    def test_each_market_area_links_to_a_known_control_block(self, input_dataset: MarketClearingInputDataset) -> None:
        for market_area in input_dataset.market_areas.values():
            assert market_area.control_block.name in input_dataset.control_blocks

    def test_market_area_orders_match_global_orders_filtered_by_area(
        self, input_dataset: MarketClearingInputDataset
    ) -> None:
        for area_name, market_area in input_dataset.market_areas.items():
            expected_order_names = {
                order_name for order_name, order in input_dataset.orders.items() if order.market_area.name == area_name
            }
            assert set(market_area.orders) == expected_order_names

    def test_price_bounds_are_consistent_over_horizon(self, input_dataset: MarketClearingInputDataset) -> None:
        for market_area in input_dataset.market_areas.values():
            for time in input_dataset.times:
                assert market_area.max_price.get_value(time) > market_area.min_price.get_value(time)


class TestOrders:
    def test_every_order_belongs_to_an_imported_market_area(self, input_dataset: MarketClearingInputDataset) -> None:
        known_areas = set(input_dataset.market_areas)
        for order in input_dataset.orders.values():
            assert order.market_area.name in known_areas

    def test_every_order_starts_within_the_optimization_horizon(
        self, input_dataset: MarketClearingInputDataset
    ) -> None:
        times = set(input_dataset.times)
        for order in input_dataset.orders.values():
            assert order.start_date in times


class TestOrderCouplings:
    def test_linked_orders_have_link_id_pointing_to_their_coupling(
        self, input_dataset: MarketClearingInputDataset
    ) -> None:
        linking_types = {CouplingType.IDENTICAL_VOLUME, CouplingType.IDENTICAL_RATIO, CouplingType.COMPLEMENT}
        for coupling in input_dataset.order_couplings.values():
            if coupling.coupling_type not in linking_types:
                continue
            for order in coupling.orders:
                if order.name not in input_dataset.orders:
                    continue
                order = input_dataset.orders[order.name]
                assert order.is_linked
                assert order.link_id == coupling.name

    def test_parent_children_couplings_mark_first_order_as_parent(
        self, input_dataset: MarketClearingInputDataset
    ) -> None:
        parent_count_per_order: Counter[str] = Counter()
        for coupling in input_dataset.order_couplings.values():
            if coupling.coupling_type != CouplingType.PARENT_CHILDREN or not coupling.orders:
                continue
            parent_name = coupling.orders[0].name
            parent_count_per_order[parent_name] += 1

            parent = input_dataset.orders.get(parent_name)
            assert parent is not None
            assert parent.is_parent
            assert parent.order_coupling_parent_ids is not None
            assert coupling.name in parent.order_coupling_parent_ids

            for child in coupling.orders:
                if child.name not in input_dataset.orders:
                    continue
                mc_child = input_dataset.orders[child.name]
                assert mc_child.is_in_parent_child_coupling
                assert mc_child.parent_child_id == coupling.name

        for order_name, count in parent_count_per_order.items():
            order = input_dataset.orders[order_name]
            assert len(order.order_coupling_parent_ids) == count

    def test_exclusion_couplings_mark_orders_as_mutually_excluding(
        self, input_dataset: MarketClearingInputDataset
    ) -> None:
        for coupling in input_dataset.order_couplings.values():
            if coupling.coupling_type != CouplingType.EXCLUSION:
                continue
            for order in coupling.orders:
                if order.name not in input_dataset.orders:
                    continue
                order = input_dataset.orders[order.name]
                assert order.is_mutually_excluding
                assert order.requires_status_variable

    def test_couplings_with_fewer_than_two_feasible_orders_are_dropped(
        self, input_dataset: MarketClearingInputDataset
    ) -> None:
        for coupling in input_dataset.order_couplings.values():
            assert coupling.orders is not None
            assert len(coupling.orders) >= 2


class TestMarketBorders:
    def test_border_endpoints_are_imported_market_areas(self, input_dataset: MarketClearingInputDataset) -> None:
        known_areas = set(input_dataset.market_areas)
        for border in input_dataset.market_borders.values():
            assert border.uphill_market_area.name in known_areas
            assert border.downhill_market_area.name in known_areas

    def test_border_flow_bounds_are_consistent(self, input_dataset: MarketClearingInputDataset) -> None:
        for border in input_dataset.market_borders.values():
            for time in input_dataset.times:
                assert border.max_flow.get_value(time) >= border.min_flow.get_value(time)
