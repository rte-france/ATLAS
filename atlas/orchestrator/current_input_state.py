"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from atlas.enums import BusinessModelName
from atlas.io_utils.atlas_dataset import AtlasDataset


class CurrentInputState:
    def __init__(self, data: AtlasDataset):
        self.data = data
        self._history: list[tuple[str, AtlasDataset]] = []

    def to_directory(self, path: str | Path):
        """Write the current input state to a directory."""
        self.data.to_directory(path)

    @classmethod
    def from_directory(cls, path: str | Path) -> CurrentInputState:
        """Load the current input state from a directory."""
        return cls(AtlasDataset.from_directory(path))

    def filter_dataset(
        self,
        included_types: Iterable[str | BusinessModelName] = (),
        filters: dict[str | BusinessModelName, Any] | None = None,
    ) -> AtlasDataset:
        return self.data.filter_dataset(included_types=included_types, filters=filters)

    def create_snapshot(self, label: str) -> None:
        """Create a named snapshot of current state for debugging/rollback.

        :param label: Name/label for this snapshot (e.g., "after_step_1", "before_optimization")
        :type label: str

        Example:
            >>> cis.create_snapshot("before_thermal_module")
            >>> # ... apply changes ...
            >>> cis.restore_snapshot("before_thermal_module")  # Rollback
        """
        self._history.append((label, copy.deepcopy(self.data)))

    def list_snapshots(self) -> list[str]:
        """Return list of all snapshot labels.

        :return: List of snapshot labels in chronological order
        :rtype: list[str]

        Example:
            >>> cis.list_snapshots()
            ['initial', 'after_step_1', 'after_step_2']
        """
        return [label for label, _ in self._history]

    def restore_snapshot(self, label: str) -> None:
        """Restore CIS to a previous snapshot.

        :param label: Snapshot label to restore
        :type label: str
        :raises ValueError: If snapshot label not found

        Example:
            >>> cis.restore_snapshot("after_step_1")
        """
        for snap_label, snapshot in self._history:
            if snap_label == label:
                self.data = copy.deepcopy(snapshot)
                return
        raise ValueError(f"Snapshot '{label}' not found. Available: {self.list_snapshots()}")

    def get_snapshot(self, label: str) -> AtlasDataset:
        """Get a snapshot without modifying current state.

        :param label: Snapshot label to retrieve
        :type label: str
        :return: The snapshot dataset
        :rtype: AtlasDataset
        :raises ValueError: If snapshot label not found

        Example:
            >>> snapshot_data = cis.get_snapshot("after_step_1")
        """
        for snap_label, snapshot in self._history:
            if snap_label == label:
                return snapshot
        raise ValueError(f"Snapshot '{label}' not found. Available: {self.list_snapshots()}")

    def clear_history(self) -> None:
        """Clear all snapshots from history.

        This can free up significant memory if many snapshots exist.

        Example:
            >>> cis.clear_history()
        """
        self._history.clear()

    def diff(self, other: CurrentInputState | AtlasDataset | None = None, label: str | None = None) -> dict[str, Any]:
        """Compare this CIS with another CIS, dataset, or snapshot.

        :param other: CIS or AtlasDataset to compare with (optional if label is provided)
        :type other: CurrentInputState | AtlasDataset | None
        :param label: If provided, compare with snapshot with this label
        :type label: str | None
        :return: Dictionary showing added/removed/modified objects per model type
        :rtype: dict[str, Any]
        :raises ValueError: If neither other nor label is provided

        Example:
            >>> diff = cis.diff(other_cis)
            >>> print(diff['order']['added'])  # ['new_order_1', 'new_order_2']
            >>> print(diff['thermal']['removed'])  # ['old_thermal_1']
            >>> print(diff['hydro']['modified'])  # ['hydro_1']

            >>> # Compare with snapshot
            >>> cis.create_snapshot("before_changes")
            >>> # ... make changes ...
            >>> diff = cis.diff(label="before_changes")
        """
        if label is not None:
            other_data = self.get_snapshot(label)
        elif other is not None:
            if isinstance(other, CurrentInputState):
                other_data = other.data
            else:
                other_data = other
        else:
            raise ValueError("Either 'other' or 'label' must be provided")

        atlas_diff = self.data.diff(other_data)

        diff_result: dict[str, Any] = {}
        for model_name, changes in atlas_diff.items():
            diff_result[model_name] = {
                "added": changes["only_in_self"],
                "removed": changes["only_in_other"],
                "modified": sorted(changes["modified"].keys()) if changes["modified"] else [],
            }

        return diff_result

    def clone(self) -> CurrentInputState:
        """Create a deep copy of this CIS.

        The clone is completely independent - changes to the clone won't affect the original.
        Note: History is NOT copied to the clone.

        :return: A new CurrentInputState with deep-copied data
        :rtype: CurrentInputState

        Example:
            >>> cis_copy = cis.clone()
            >>> # Modify cis_copy without affecting original cis
        """
        return CurrentInputState(copy.deepcopy(self.data))

    @contextmanager
    def transaction(self):
        """Context manager for transactional CIS modifications with automatic rollback on error.

        If any exception occurs within the context, the CIS is automatically restored to its
        state before entering the context.

        :yields: Self
        :rtype: CurrentInputState

        Example:
            >>> with cis.transaction():
            ...     CISHandler.apply(change_sets, cis)
            ...     # If any error occurs here, CIS is automatically rolled back

            >>> # Advanced: capture the state for later use
            >>> with cis.transaction() as transactional_cis:
            ...     # Make changes to transactional_cis
            ...     module.run(transactional_cis.data, params)
        """
        backup = copy.deepcopy(self.data)
        try:
            yield self
        except Exception:
            self.data = backup
            raise
