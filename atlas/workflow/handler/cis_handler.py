"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import atlas.config as cfg
from atlas.workflow.change_set.change_set import ChangeSet
from atlas.workflow.current_input_state import CurrentInputState
from atlas.workflow.handler.changet_set_handler import ChangeSetHandler


class CISHandler:
    @staticmethod
    def apply(change_sets: list[ChangeSet], cis: CurrentInputState):
        for change_set in CISHandler._ordering_change_sets(change_sets):
            ChangeSetHandler.apply(change_set, cis)

    @staticmethod
    def _ordering_change_sets(change_sets: list[ChangeSet]) -> list[ChangeSet]:
        """Return the list of change set ordered in function of MODEL_ORDER_INSTANTIATION"""
        order_index = {name: idx for idx, name in enumerate(cfg.MODEL_ORDER_INSTANTIATION)}

        # Sort using the index; items with no match go last
        return sorted(
            change_sets, key=lambda cs: order_index.get(cfg.INVERSE_MODEL_MAPPING_NAME[cs.model_type], len(order_index))
        )
