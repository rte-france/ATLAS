"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from atlas.core.abstract_class.job import AbstractJob


class WorkflowJob(AbstractJob):
    """
    A job in a workflow, responsible for executing a module using provided parameters
    and producing an output dataset from an input dataset.
    """

    def __repr__(self) -> str:
        """Return a detailed string representation of the workflow job."""
        module_name = self.module.__class__.__name__
        has_output = self._output_dataset is not None
        return f"WorkflowStep(name={self.name!r}, module={module_name}, executed={has_output})"
