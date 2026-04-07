"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from atlas.abstract_class.abstract_step import AbsractStep


class WorkflowStep(AbsractStep):
    """
    A step in a workflow, responsible for executing a module using provided parameters
    and producing an output dataset from an input dataset.
    """

    def __repr__(self) -> str:
        """Return a detailed string representation of the workflow step."""
        module_name = self.module.__class__.__name__
        has_output = self._output_dataset is not None
        return f"WorkflowStep(name={self.name!r}, module={module_name}, executed={has_output})"

    @staticmethod
    def add_index_in_step_name(steps: list) -> None:
        """Append a numeric index suffix to duplicate step names, in-place.

        Steps whose name is unique are left unchanged. Steps sharing a name are
        renamed '<name>_1', '<name>_2', etc., in the order they appear.

        :param steps: List of step parameter objects exposing a 'name' attribute.
        :type steps: list
        """
        name_counts: dict[str, int] = {}
        for step in steps:
            name_counts[step.name] = name_counts.get(step.name, 0) + 1

        name_index: dict[str, int] = {}
        for step in steps:
            if name_counts[step.name] > 1:
                name_index[step.name] = name_index.get(step.name, 0) + 1
                step.name = f"{step.name}_{name_index[step.name]}"