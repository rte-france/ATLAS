"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Unit tests for CurrentInputState features:
- State history & versioning
- Diff/comparison capabilities
- Immutable copy/clone
- Transaction context manager
- Utility methods
"""

import pytest

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.models.market.market_area import MarketArea
from atlas.models.market.order import Order
from atlas.orchestrator.change_set import AddObject, UpdateObject
from atlas.orchestrator.current_input_state import CurrentInputState
from atlas.orchestrator.handler.cis_handler import CISHandler


@pytest.fixture
def cis():
    """Create a basic CurrentInputState with some test data."""
    dataset = AtlasDataset()
    cis = CurrentInputState(dataset)

    # Add some test objects
    ma1 = MarketArea(name="ma1")
    ma2 = MarketArea(name="ma2")
    cis.data.market_area.add(ma1)
    cis.data.market_area.add(ma2)

    order1 = Order(name="order_1", price=10.0, market_area=ma1)
    order2 = Order(name="order_2", price=20.0, market_area=ma2)
    cis.data.order.add(order1)
    cis.data.order.add(order2)

    return cis


@pytest.fixture
def empty_cis():
    """Create an empty CurrentInputState."""
    dataset = AtlasDataset()
    return CurrentInputState(dataset)


class TestStateHistoryAndVersioning:
    """Test snapshot/history functionality."""

    def test_create_snapshot_stores_current_state(self, cis):
        """Test that creating a snapshot stores the current state."""
        cis.create_snapshot("initial")

        assert "initial" in cis.list_snapshots()
        assert len(cis.list_snapshots()) == 1

    def test_multiple_snapshots_stored_in_order(self, cis):
        """Test that multiple snapshots are stored chronologically."""
        cis.create_snapshot("snapshot_1")
        cis.create_snapshot("snapshot_2")
        cis.create_snapshot("snapshot_3")

        snapshots = cis.list_snapshots()
        assert snapshots == ["snapshot_1", "snapshot_2", "snapshot_3"]

    def test_restore_snapshot_restores_previous_state(self, cis):
        """Test that restoring a snapshot brings back previous state."""
        # Create snapshot before changes
        cis.create_snapshot("before_changes")
        initial_order_count = len(cis.data.order)

        # Make changes
        order3 = Order(name="order_3", price=30.0)
        cis.data.order.add(order3)

        assert len(cis.data.order) == initial_order_count + 1

        # Restore snapshot
        cis.restore_snapshot("before_changes")

        # Check state is restored
        assert len(cis.data.order) == initial_order_count
        assert "order_3" not in cis.data.order

    def test_restore_snapshot_with_invalid_label_raises_error(self, cis):
        """Test that restoring non-existent snapshot raises ValueError."""
        with pytest.raises(ValueError, match="Snapshot 'nonexistent' not found"):
            cis.restore_snapshot("nonexistent")

    def test_get_snapshot_returns_snapshot_without_modifying_current(self, cis):
        """Test that get_snapshot retrieves data without changing current state."""
        cis.create_snapshot("test_snapshot")

        # Modify current state
        order3 = Order(name="order_3", price=30.0)
        cis.data.order.add(order3)

        # Get snapshot (should not have order_3)
        snapshot = cis.get_snapshot("test_snapshot")
        assert "order_3" not in snapshot.order

        # Current state should still have order_3
        assert "order_3" in cis.data.order

    def test_get_snapshot_with_invalid_label_raises_error(self, cis):
        """Test that getting non-existent snapshot raises ValueError."""
        with pytest.raises(ValueError, match="Snapshot 'nonexistent' not found"):
            cis.get_snapshot("nonexistent")

    def test_clear_history_removes_all_snapshots(self, cis):
        """Test that clear_history removes all snapshots."""
        cis.create_snapshot("snapshot_1")
        cis.create_snapshot("snapshot_2")

        assert len(cis.list_snapshots()) == 2

        cis.clear_history()

        assert len(cis.list_snapshots()) == 0

    def test_snapshot_is_deep_copy(self, cis):
        """Test that snapshots are independent deep copies."""
        cis.create_snapshot("snapshot")

        # Modify original
        original_order = cis.data.order.get("order_1")
        original_order.price = 999.0

        # Snapshot should have original price
        snapshot = cis.get_snapshot("snapshot")
        snapshot_order = snapshot.order.get("order_1")
        assert snapshot_order.price == 10.0  # Original price
        assert original_order.price == 999.0  # Modified price

    def test_get_all_snapshots_returns_all_snapshots(self, cis):
        """Test that get_all_snapshots returns all snapshots as a dictionary."""
        # Create multiple snapshots
        cis.create_snapshot("snapshot_1")

        # Modify data
        order3 = Order(name="order_3", price=30.0)
        cis.data.order.add(order3)
        cis.create_snapshot("snapshot_2")

        # Get all snapshots
        all_snapshots = cis.get_all_snapshots()

        # Verify it's a dictionary with correct keys
        assert isinstance(all_snapshots, dict)
        assert set(all_snapshots.keys()) == {"snapshot_1", "snapshot_2"}

        # Verify snapshot_1 doesn't have order_3
        assert "order_3" not in all_snapshots["snapshot_1"].order

        # Verify snapshot_2 has order_3
        assert "order_3" in all_snapshots["snapshot_2"].order

    def test_get_all_snapshots_returns_copy(self, cis):
        """Test that get_all_snapshots returns a copy, not the internal dict."""
        cis.create_snapshot("snapshot_1")

        # Get all snapshots
        all_snapshots = cis.get_all_snapshots()

        # Modify the returned dict
        all_snapshots["fake_snapshot"] = cis.data

        # Verify the internal history wasn't modified
        assert "fake_snapshot" not in cis.list_snapshots()
        assert len(cis.list_snapshots()) == 1

    def test_get_all_snapshots_empty(self, cis):
        """Test that get_all_snapshots returns empty dict when no snapshots exist."""
        all_snapshots = cis.get_all_snapshots()

        assert isinstance(all_snapshots, dict)
        assert len(all_snapshots) == 0


class TestDiffComparison:
    """Test diff/comparison functionality."""

    def test_diff_with_no_changes_returns_empty(self, cis):
        """Test that diff with identical CIS returns empty dict."""
        cis_copy = cis.clone()
        diff = cis.diff(cis_copy)

        assert diff == {}

    def test_diff_detects_added_objects(self, cis):
        """Test that diff detects newly added objects."""
        cis_modified = cis.clone()
        order3 = Order(name="order_3", price=30.0)
        cis_modified.data.order.add(order3)

        diff = cis_modified.diff(cis)

        assert "order" in diff
        assert "order_3" in diff["order"]["added"]
        assert diff["order"]["removed"] == []
        assert diff["order"]["modified"] == []

    def test_diff_detects_removed_objects(self, cis):
        """Test that diff detects removed objects."""
        cis_modified = cis.clone()
        cis_modified.data.order.remove("order_1")

        diff = cis_modified.diff(cis)

        assert "order" in diff
        assert diff["order"]["added"] == []
        assert "order_1" in diff["order"]["removed"]
        assert diff["order"]["modified"] == []

    def test_diff_detects_modified_objects(self, cis):
        """Test that diff detects modified objects."""
        cis_modified = cis.clone()
        modified_order = cis_modified.data.order.get("order_1")
        modified_order.price = 999.0

        diff = cis_modified.diff(cis)

        assert "order" in diff
        assert diff["order"]["added"] == []
        assert diff["order"]["removed"] == []
        assert "order_1" in diff["order"]["modified"]

    def test_diff_detects_multiple_change_types(self, cis):
        """Test that diff detects added, removed, and modified objects together."""
        cis_modified = cis.clone()

        # Add
        order3 = Order(name="order_3", price=30.0)
        cis_modified.data.order.add(order3)

        # Remove
        cis_modified.data.order.remove("order_1")

        # Modify
        modified_order = cis_modified.data.order.get("order_2")
        modified_order.price = 999.0

        diff = cis_modified.diff(cis)

        assert "order" in diff
        assert "order_3" in diff["order"]["added"]
        assert "order_1" in diff["order"]["removed"]
        assert "order_2" in diff["order"]["modified"]

    def test_diff_with_snapshot_label(self, cis):
        """Test that diff can compare with a snapshot using label."""
        cis.create_snapshot("before_changes")

        # Make changes
        order3 = Order(name="order_3", price=30.0)
        cis.data.order.add(order3)

        diff = cis.diff(label="before_changes")

        assert "order" in diff
        assert "order_3" in diff["order"]["added"]

    def test_diff_with_atlas_dataset(self, cis):
        """Test that diff can compare with AtlasDataset directly."""
        dataset_copy = cis.clone().data

        # Modify cis
        order3 = Order(name="order_3", price=30.0)
        cis.data.order.add(order3)

        diff = cis.diff(dataset_copy)

        assert "order" in diff
        assert "order_3" in diff["order"]["added"]


class TestImmutableCopyClone:
    """Test clone functionality."""

    def test_clone_creates_independent_copy(self, cis):
        """Test that clone creates an independent deep copy."""
        cis_clone = cis.clone()

        # Modify original
        cis.data.order.get("order_1").price = 999.0

        # Clone should be unchanged
        assert cis_clone.data.order.get("order_1").price == 10.0

    def test_clone_does_not_copy_history(self, cis):
        """Test that clone does not copy snapshot history."""
        cis.create_snapshot("snapshot_1")
        cis.create_snapshot("snapshot_2")

        cis_clone = cis.clone()

        assert len(cis.list_snapshots()) == 2
        assert len(cis_clone.list_snapshots()) == 0

    def test_clone_copies_all_data(self, cis):
        """Test that clone copies all objects."""
        cis_clone = cis.clone()

        assert len(cis_clone.data.order) == len(cis.data.order)
        assert len(cis_clone.data.market_area) == len(cis.data.market_area)
        assert "order_1" in cis_clone.data.order
        assert "order_2" in cis_clone.data.order
        assert "ma1" in cis_clone.data.market_area
        assert "ma2" in cis_clone.data.market_area


class TestTransactionContextManager:
    """Test transaction context manager."""

    def test_transaction_commits_on_success(self, cis):
        """Test that changes are kept when transaction succeeds."""
        initial_count = len(cis.data.order)

        with cis.transaction():
            order3 = Order(name="order_3", price=30.0)
            cis.data.order.add(order3)

        # Changes should be committed
        assert len(cis.data.order) == initial_count + 1
        assert "order_3" in cis.data.order

    def test_transaction_rolls_back_on_error(self, cis):
        """Test that changes are rolled back when exception occurs."""
        initial_count = len(cis.data.order)
        initial_price = cis.data.order.get("order_1").price

        with pytest.raises(ValueError):
            with cis.transaction():
                # Make some changes
                order3 = Order(name="order_3", price=30.0)
                cis.data.order.add(order3)
                cis.data.order.get("order_1").price = 999.0

                # Trigger error
                raise ValueError("Simulated error")

        # Changes should be rolled back
        assert len(cis.data.order) == initial_count
        assert "order_3" not in cis.data.order
        assert cis.data.order.get("order_1").price == initial_price

    def test_transaction_with_cis_handler(self, cis):
        """Test transaction works with CISHandler operations."""
        initial_count = len(cis.data.order)

        change_sets = [
            AddObject({"name": "order_3", "price": 30.0}, model_type=Order),
            AddObject({"name": "order_4", "price": 40.0}, model_type=Order),
        ]

        with cis.transaction():
            CISHandler.apply(change_sets, cis, rollback_on_error=False)

        # Changes should be committed
        assert len(cis.data.order) == initial_count + 2
        assert "order_3" in cis.data.order
        assert "order_4" in cis.data.order

    def test_transaction_rolls_back_on_cis_handler_error(self, cis):
        """Test that transaction rolls back when CISHandler fails."""
        initial_count = len(cis.data.order)

        # This will fail because order_999 doesn't exist
        change_sets = [
            AddObject({"name": "order_3", "price": 30.0}, model_type=Order),
            UpdateObject({"name": "order_999", "price": 999.0}, model_type=Order),
        ]

        from atlas.custom_errors import ChangeSetApplicationError

        with pytest.raises(ChangeSetApplicationError):  # CISHandler will raise an error
            with cis.transaction():
                CISHandler.apply(change_sets, cis, rollback_on_error=False)

        # All changes should be rolled back (including the successful add)
        assert len(cis.data.order) == initial_count
        assert "order_3" not in cis.data.order

    def test_nested_transactions_not_recommended(self, cis):
        """Test behavior with nested transactions (outer rollback wins)."""
        initial_price = cis.data.order.get("order_1").price

        with pytest.raises(ValueError):
            with cis.transaction():
                cis.data.order.get("order_1").price = 100.0

                with cis.transaction():
                    cis.data.order.get("order_1").price = 200.0

                # Outer transaction error
                raise ValueError("Outer error")

        # Outer transaction should roll back everything
        assert cis.data.order.get("order_1").price == initial_price


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""

    def test_workflow_step_debugging_scenario(self, cis):
        """Test a realistic workflow debugging scenario with snapshots and diffs."""
        # Snapshot before step 1
        cis.create_snapshot("before_step_1")

        # Step 1: Add new order
        change_sets_1 = [AddObject({"name": "order_3", "price": 30.0}, model_type=Order)]
        CISHandler.apply(change_sets_1, cis)
        cis.create_snapshot("after_step_1")

        # Step 2: Modify existing order
        change_sets_2 = [UpdateObject({"name": "order_1", "price": 100.0}, model_type=Order)]
        CISHandler.apply(change_sets_2, cis)
        cis.create_snapshot("after_step_2")

        # Debug: What changed in step 1?
        step_1_diff = cis.diff(label="before_step_1")
        assert "order_3" in step_1_diff["order"]["added"]

        # Debug: What changed in step 2?
        before_step_2 = cis.get_snapshot("after_step_1")
        after_step_2 = cis.data
        cis_after_step_2 = CurrentInputState(after_step_2)
        cis_before_step_2 = CurrentInputState(before_step_2)
        step_2_diff = cis_after_step_2.diff(cis_before_step_2)
        assert "order_1" in step_2_diff["order"]["modified"]

    def test_safe_experimentation_with_clone_and_transaction(self, cis):
        """Test safe experimentation pattern using clone and transaction."""
        # Clone for experimentation
        experimental_cis = cis.clone()

        # Try risky changes in transaction
        try:
            with experimental_cis.transaction():
                # Make experimental changes
                order3 = Order(name="order_3", price=30.0)
                experimental_cis.data.order.add(order3)

                # Simulate: check if results are acceptable
                if len(experimental_cis.data.order) > 10:  # Some validation
                    raise ValueError("Too many orders")

                # If we reach here, changes are acceptable
                # Could copy experimental_cis back to main cis if desired
        except ValueError:
            # Experimental changes were rolled back
            pass

        # Original cis is unchanged
        assert "order_3" not in cis.data.order
