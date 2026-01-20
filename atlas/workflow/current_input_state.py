"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Iterable

from atlas import BusinessModel
from atlas.workflow.change_set import ChangeSet


class CurrentInputState:
    def __init__(self, data: dict[str, dict[str, type[BusinessModel]]]):
        """
        data example:
        {
            "equipment": {
                "equipment_1": Equipment(...)
            }
        }
        """
        self.data = data

    def apply(self, change: ChangeSet) -> None:
        """
        Apply one ChangeSet.
        """
        change.apply(self.data)

    def apply_all(self, changes: Iterable[ChangeSet]) -> None:
        """
        Apply a list of ChangeSet
        If an error occurs, apply rollbacks
        """
        applied: list[ChangeSet] = []
        next_to_applied = None

        try:
            for change in changes:
                next_to_applied = change
                change.apply(self.data)
                applied.append(change)
        except Exception:
            # rollback applied ChangeSet in reverse order
            error = f"Error when applying change set : {next_to_applied.__class__}"
            for change in reversed(applied):
                try:
                    change.rollback(self.data)
                except Exception:
                    # rollback best-effort
                    raise ValueError(f"{error}\nCould not rollback change set : {change}")
            raise ValueError(error)
