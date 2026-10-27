"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import copy
from typing import TYPE_CHECKING, Any

import atlas.config as cfg
from atlas.config import logger
from atlas.custom_errors import ChangeSetApplicationError
from atlas.orchestrator.change_set import ChangeSet, UpdateObject
from atlas.orchestrator.current_input_state import CurrentInputState
from atlas.orchestrator.handler.change_set_handler import ChangeSetHandler

if TYPE_CHECKING:
    from atlas.enums import BusinessModelName
    from atlas.io_utils.container import Container
    from atlas.objects.business_model import BusinessModel


class _UndoLog:
    """Record what a batch of change sets touches, so that a failed batch can be undone.

    Nothing is deep copied: a container is copied shallowly (references only) the first time it is
    touched, and an updated object keeps its previous field values. Rolling back puts the very same
    instances back, so references between objects keep pointing to the live objects.
    """

    def __init__(self, cis: CurrentInputState):
        self._cis = cis
        self._containers: dict[BusinessModelName, Container] = {}
        self._objects: dict[int, tuple[BusinessModel, dict[str, Any]]] = {}

    def record(self, change_set: ChangeSet) -> None:
        """Save the state *change_set* is about to modify. Must be called before applying it."""
        container = self._cis.data.get_container_by_type(change_set.model_type)
        if change_set.model_type not in self._containers:
            self._containers[change_set.model_type] = copy.copy(container)
        if isinstance(change_set, UpdateObject) and change_set.data.get("name") in container:
            obj = container.get(change_set.data["name"])
            self._objects.setdefault(id(obj), (obj, obj.__dict__.copy()))

    def rollback(self) -> None:
        """Restore every recorded object and container."""
        for obj, fields in self._objects.values():
            obj.__dict__.update(fields)
        for model_type, container in self._containers.items():
            setattr(self._cis.data, model_type.value, container)


class CISHandler:
    @staticmethod
    def apply(change_sets: list[ChangeSet], cis: CurrentInputState, rollback_on_error: bool = True):
        """Apply a list of change sets to the current input state.


        :param change_sets: List of change sets to apply
        :type change_set: list[ChangeSet]
        :param cis: Current input state to modify
        :type cis: CurrentInputState
        :param rollback_on_error: If True, rollback all changes if any change set fails (default: True)
        :type rollback_on_error: bool
        """
        if not change_sets:
            logger.debug("No change sets to apply")
            return

        change_sets = CISHandler._ordering_change_sets(change_sets)
        CISHandler._validate_no_duplicates(change_sets)
        logger.debug(f"Applying {len(change_sets)} change sets to Current Input State")

        if not rollback_on_error:
            CISHandler._apply_change_sets(change_sets, cis)
            return

        undo_log = _UndoLog(cis)
        try:
            CISHandler._apply_change_sets(change_sets, cis, undo_log)
        except Exception:
            undo_log.rollback()
            raise

    @staticmethod
    def _apply_change_sets(
        change_sets: list[ChangeSet], cis: CurrentInputState, undo_log: _UndoLog | None = None
    ) -> None:
        """Internal method to apply change sets, recording them in *undo_log* if given.

        :param change_sets: Ordered list of change sets to apply
        :type change_sets: list[ChangeSet]
        :param cis: Current input state to modify
        :type cis: CurrentInputState
        :param undo_log: Undo log recording the state before each change set
        :type undo_log: _UndoLog | None
        :raises ChangeSetApplicationError: If any change set fails to apply
        """
        for idx, change_set in enumerate(change_sets):
            try:
                logger.debug(f"Applying change set {idx + 1}/{len(change_sets)}: {change_set}")
                if undo_log is not None:
                    undo_log.record(change_set)
                ChangeSetHandler.apply(change_set, cis)
            except Exception as e:
                error_msg = f"Failed to apply change set {idx + 1}/{len(change_sets)} ({change_set}): {e}"
                logger.error(error_msg)
                raise ChangeSetApplicationError(error_msg, change_set, e) from e

        logger.info(f"Successfully applied {len(change_sets)} change sets to Current Input State")

    @staticmethod
    def _validate_no_duplicates(change_sets: list[ChangeSet]) -> None:
        """Validate that there are no duplicate change sets targeting the same object.

        Multiple updates to the same object in a single batch can lead to undefined behavior.
        This validation logs warnings for duplicates.

        :param change_sets: List of change sets to apply
        :type change_set: list[ChangeSet]
        """
        seen_objects: dict[tuple[str, str], list[int]] = {}

        for idx, change_set in enumerate(change_sets):
            identifier = change_set.get_object_identifier()
            if identifier in seen_objects:
                seen_objects[identifier].append(idx)
            else:
                seen_objects[identifier] = [idx]

        # Log warnings for duplicates
        for (model_type, obj_name), indices in seen_objects.items():
            if len(indices) > 1:
                logger.warning(
                    f"Multiple change sets ({len(indices)}) target the same object: "
                    f"{model_type} '{obj_name}' at indices {indices}. "
                    f"This may lead to unexpected behavior."
                )

    @staticmethod
    def _ordering_change_sets(change_sets: list[ChangeSet]) -> list[ChangeSet]:
        """Return the list of change set ordered in function of MODEL_ORDER_INSTANTIATION"""
        order_index = {name: idx for idx, name in enumerate(cfg.MODEL_ORDER_INSTANTIATION)}

        # Sort using the index; items with no match go last
        return sorted(
            change_sets,
            key=lambda cs: order_index.get(
                cs.model_type,
                len(order_index),
            ),
        )
