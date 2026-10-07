"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
from atlas.enums import CouplingType, OrderType
from atlas.modules.balancing_market_bsp_orders.order_formulators.thermal import ThermalOrderFormulator


def _make_formulator(equipment, time_index, parameters) -> ThermalOrderFormulator:
    return ThermalOrderFormulator(equipment, time_index, parameters)


class TestNextCouplingName:
    def test_counter_increments_per_coupling_type(self, thermal_equipment, parameters):
        """Independent counters per CouplingType, starting at 1."""
        test_time = parameters.temporal.start_date
        next_time = test_time.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)
        order = formulator.build_order(
            order_type=OrderType.Sell, start=test_time, end=next_time, price=10.0, qmin=0.0, qmax=10.0
        )

        assert formulator._next_coupling_name(CouplingType.PARENT_CHILDREN, order) == f"parent_children1_{order.name}"
        assert formulator._next_coupling_name(CouplingType.PARENT_CHILDREN, order) == f"parent_children2_{order.name}"
        assert formulator._next_coupling_name(CouplingType.EXCLUSION, order) == f"exclusion1_{order.name}"

    def test_counters_independent_per_formulator_instance(self, thermal_equipment, parameters):
        test_time = parameters.temporal.start_date
        next_time = test_time.add(minutes=15)
        formulator_a = _make_formulator(thermal_equipment, [test_time], parameters)
        formulator_b = _make_formulator(thermal_equipment, [test_time], parameters)
        order = formulator_a.build_order(
            order_type=OrderType.Sell, start=test_time, end=next_time, price=10.0, qmin=0.0, qmax=10.0
        )

        formulator_a._next_coupling_name(CouplingType.PARENT_CHILDREN, order)
        assert formulator_b._next_coupling_name(CouplingType.PARENT_CHILDREN, order) == f"parent_children1_{order.name}"


class TestRecordUpwardOrder:
    def test_records_order_under_its_timestep(self, thermal_equipment, parameters):
        test_time = parameters.temporal.start_date
        next_time = test_time.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)
        order = formulator.build_order(
            order_type=OrderType.Sell, start=test_time, end=next_time, price=10.0, qmin=0.0, qmax=10.0
        )

        formulator._record_upward_order(test_time, order)
        assert formulator._upward_orders_by_time[test_time] == [order]

    def test_multiple_orders_at_same_timestep_accumulate_in_order(self, thermal_equipment, parameters):
        test_time = parameters.temporal.start_date
        next_time = test_time.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)
        order_1 = formulator.build_order(
            order_type=OrderType.Sell, start=test_time, end=next_time, price=10.0, qmin=0.0, qmax=10.0, suffix="_a"
        )
        order_2 = formulator.build_order(
            order_type=OrderType.Sell, start=test_time, end=next_time, price=10.0, qmin=0.0, qmax=20.0, suffix="_b"
        )

        formulator._record_upward_order(test_time, order_1)
        formulator._record_upward_order(test_time, order_2)
        assert formulator._upward_orders_by_time[test_time] == [order_1, order_2]


class TestExclusionCouplingsWithAdjacentUpwardOrders:
    def test_links_to_previous_timestep_orders(self, thermal_equipment, parameters):
        test_time = parameters.temporal.start_date.add(minutes=15)
        previous_time = test_time.subtract(minutes=15)
        next_time = test_time.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        previous_order = formulator.build_order(
            order_type=OrderType.Sell, start=previous_time, end=test_time, price=10.0, qmin=0.0, qmax=10.0
        )
        formulator._record_upward_order(previous_time, previous_order)

        order = formulator.build_order(
            order_type=OrderType.Buy, start=test_time, end=next_time, price=10.0, qmin=0.0, qmax=10.0
        )
        couplings = formulator._exclusion_couplings_with_adjacent_upward_orders(test_time, order)

        assert len(couplings) == 1
        assert couplings[0].coupling_type == CouplingType.EXCLUSION
        assert couplings[0].orders == [previous_order, order]

    def test_links_to_both_previous_and_next_when_both_directions(self, thermal_equipment, parameters):
        test_time = parameters.temporal.start_date.add(minutes=15)
        previous_time = test_time.subtract(minutes=15)
        next_time = test_time.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        previous_order = formulator.build_order(
            order_type=OrderType.Sell, start=previous_time, end=test_time, price=10.0, qmin=0.0, qmax=10.0
        )
        formulator._record_upward_order(previous_time, previous_order)
        next_order = formulator.build_order(
            order_type=OrderType.Sell,
            start=next_time,
            end=next_time.add(minutes=15),
            price=10.0,
            qmin=0.0,
            qmax=10.0,
        )
        formulator._record_upward_order(next_time, next_order)

        order = formulator.build_order(
            order_type=OrderType.Buy, start=test_time, end=next_time, price=10.0, qmin=0.0, qmax=10.0
        )
        couplings = formulator._exclusion_couplings_with_adjacent_upward_orders(test_time, order)

        assert len(couplings) == 2
        assert couplings[0].orders == [previous_order, order]
        assert couplings[1].orders == [order, next_order]

    def test_both_directions_false_skips_next(self, thermal_equipment, parameters):
        test_time = parameters.temporal.start_date.add(minutes=15)
        previous_time = test_time.subtract(minutes=15)
        next_time = test_time.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)

        previous_order = formulator.build_order(
            order_type=OrderType.Sell, start=previous_time, end=test_time, price=10.0, qmin=0.0, qmax=10.0
        )
        formulator._record_upward_order(previous_time, previous_order)
        next_order = formulator.build_order(
            order_type=OrderType.Sell,
            start=next_time,
            end=next_time.add(minutes=15),
            price=10.0,
            qmin=0.0,
            qmax=10.0,
        )
        formulator._record_upward_order(next_time, next_order)

        order = formulator.build_order(
            order_type=OrderType.Buy, start=test_time, end=next_time, price=10.0, qmin=0.0, qmax=10.0
        )
        couplings = formulator._exclusion_couplings_with_adjacent_upward_orders(test_time, order, both_directions=False)

        assert len(couplings) == 1
        assert couplings[0].orders == [previous_order, order]

    def test_no_couplings_when_no_neighbors_recorded(self, thermal_equipment, parameters):
        test_time = parameters.temporal.start_date.add(minutes=15)
        next_time = test_time.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [test_time], parameters)
        order = formulator.build_order(
            order_type=OrderType.Buy, start=test_time, end=next_time, price=10.0, qmin=0.0, qmax=10.0
        )

        assert formulator._exclusion_couplings_with_adjacent_upward_orders(test_time, order) == []


class TestCase5CouplingCounter:
    def test_counter_increments_across_consecutive_startups(self, thermal_equipment, parameters):
        """Two separate Case 5 startups on the same formulator get
        parent_children1 and parent_children2 — the counter is per-equipment,
        not per-call. couplings[0] is always the PARENT_CHILDREN entry (built
        before any EXCLUSION couplings are appended).
        """
        t1 = parameters.temporal.start_date
        t2 = t1.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [t1, t2], parameters)

        _, couplings_1 = formulator._formulate_case_5_orders(t1, t1.add(minutes=15))
        _, couplings_2 = formulator._formulate_case_5_orders(t2, t2.add(minutes=15))

        assert couplings_1[0].name.startswith("parent_children1_")
        assert couplings_2[0].name.startswith("parent_children2_")


class TestTwoPassStructureLinksAcrossTimesteps:
    def test_downward_order_links_forward_to_next_timestep_upward_order(self, thermal_equipment, parameters):
        """t1's downward order can only find t2's upward order thanks to the
        two-pass structure (every upward order is recorded before any downward
        order is formulated) — a naive single pass wouldn't have recorded t2 yet
        by the time t1 is processed.
        """
        object.__setattr__(thermal_equipment, "maximum_gradient", 2.0)
        t1 = parameters.temporal.start_date
        t2 = t1.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [t1, t2], parameters)

        orders, couplings = formulator.formulate()

        t1_downward = next(o for o in orders if o.start_date == t1 and o.order_type == OrderType.Buy and "_d_" in o.name)
        t2_upward = next(o for o in orders if o.start_date == t2 and o.order_type == OrderType.Sell and "_u_" in o.name)

        matching = [
            c
            for c in couplings
            if c.coupling_type == CouplingType.EXCLUSION and t1_downward in c.orders and t2_upward in c.orders
        ]
        assert len(matching) == 1

    def test_downward_order_links_backward_to_previous_timestep_upward_order(self, thermal_equipment, parameters):
        object.__setattr__(thermal_equipment, "maximum_gradient", 2.0)
        t1 = parameters.temporal.start_date
        t2 = t1.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [t1, t2], parameters)

        orders, couplings = formulator.formulate()

        t2_downward = next(o for o in orders if o.start_date == t2 and o.order_type == OrderType.Buy and "_d_" in o.name)
        t1_upward = next(o for o in orders if o.start_date == t1 and o.order_type == OrderType.Sell and "_u_" in o.name)

        matching = [
            c
            for c in couplings
            if c.coupling_type == CouplingType.EXCLUSION and t2_downward in c.orders and t1_upward in c.orders
        ]
        assert len(matching) == 1

    def test_no_exclusion_coupling_when_gradient_disabled(self, thermal_equipment, parameters):
        """maximum_gradient=0 (default) -> no EXCLUSION couplings for downward
        orders at all, even though adjacent upward orders exist.
        """
        t1 = parameters.temporal.start_date
        t2 = t1.add(minutes=15)
        formulator = _make_formulator(thermal_equipment, [t1, t2], parameters)

        _, couplings = formulator.formulate()
        assert not any(c.coupling_type == CouplingType.EXCLUSION for c in couplings)
