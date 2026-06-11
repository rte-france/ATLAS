"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import atlas.config as cfg
from atlas.config import logger
from atlas.core.orchestrator.change_set import ChangeSet
from atlas.core.orchestrator.current_input_state import CurrentInputState
from atlas.core.orchestrator.handler.change_set_handler import ChangeSetHandler
from atlas.custom_errors import ChangeSetApplicationError


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

        if rollback_on_error:
            touched_types = {cs.model_type for cs in change_sets}
            with cis.transaction(touched_types):
                CISHandler._apply_change_sets(change_sets, cis)
        else:
            CISHandler._apply_change_sets(change_sets, cis)

    @staticmethod
    def _apply_change_sets(change_sets: list[ChangeSet], cis: CurrentInputState) -> None:
        """Internal method to apply change sets without transaction handling.

        :param change_sets: Ordered list of change sets to apply
        :type change_sets: list[ChangeSet]
        :param cis: Current input state to modify
        :type cis: CurrentInputState
        :raises ChangeSetApplicationError: If any change set fails to apply
        """
        try:
            for idx, change_set in enumerate(change_sets):
                try:
                    logger.debug(f"Applying change set {idx + 1}/{len(change_sets)}: {change_set}")
                    ChangeSetHandler.apply(change_set, cis)
                except Exception as e:
                    error_msg = f"Failed to apply change set {idx + 1}/{len(change_sets)} ({change_set}): {e}"
                    logger.error(error_msg)
                    raise ChangeSetApplicationError(error_msg, change_set, e) from e

            logger.info(f"Successfully applied {len(change_sets)} change sets to Current Input State")

        except Exception as e:
            # Catch any unexpected errors and re-raise
            # Transaction will handle rollback if enabled
            error_msg = f"Unexpected error while applying change sets: {type(e).__name__}: {e}"
            logger.error(error_msg)
            raise

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
