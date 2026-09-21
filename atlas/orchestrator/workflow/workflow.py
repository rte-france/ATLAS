"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from atlas.abstract_class.orchestrator import AbstractOrchestrator
from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.orchestrator.workflow.job import WorkflowJob
from atlas.orchestrator.workflow.parameters import Step, WorkflowParameters


class Workflow(AbstractOrchestrator[WorkflowParameters, WorkflowJob]):
    """A structure for managing the sequential execution of multiple modules through a list of workflow jobs.

    Each job processes the output of the previous one, starting from the input dataset."""

    @classmethod
    def get_param_class(cls):
        return WorkflowParameters

    def __init__(self, parameters: WorkflowParameters, prefix_job_name: str | None = None):
        """Initialize a Workflow instance.

        :param parameters: Name of the workflow.
        :type parameters: WorkflowParameters
        """
        super().__init__(parameters)
        self._steps: list[Step] = []
        self._resolved_parameters: list[AbstractModuleParameters] = []
        for step in self.parameters.steps:
            self.add_step(step, prefix_job_name)

    @property
    def jobs(self) -> Iterator[WorkflowJob]:
        """
        Generate and return the workflow jobs.

        :return: The list of WorkflowJob instances.
        """
        for step, resolved_parameter in zip(self._steps, self._resolved_parameters, strict=True):
            parameters = resolved_parameter.model_copy()
            yield WorkflowJob(f"{step.name!r}", step.module.value, parameters)

    @property
    def jobs_count(self) -> int:
        return len(self._steps)

    def add_step(self, step: Step | list[Step], prefix_job_name: str | None = None) -> None:
        """Add one or multiple step to the end of the workflow."""
        if isinstance(step, list):
            if not all(isinstance(s, Step) for s in step):
                raise TypeError("All items in the list must be Step instances.")
            for s in step:
                self._add_one_step(s, prefix_job_name)
        else:
            if not isinstance(step, Step):
                raise TypeError(f"Expected a Step instance, got {type(step).__name__}.")
            self._add_one_step(step, prefix_job_name)

    def _add_one_step(self, step: Step, prefix_job_name: str | None = None) -> None:
        """Add a single step to the end of the workflow, add the prefix given and build parameters."""
        step.name = f"{prefix_job_name} {step.name}" if prefix_job_name else step.name
        try:
            resolved_parameter = self._resolve_parameters(step)
        except Exception as exc:
            raise ValueError(f"Step {step.name!r}: unable to resolve parameters ({exc})") from exc
        resolved_parameter.output.output_dir = self.parameters.resolve_path(self.parameters.output_dir) / step.name
        self._steps.append(step)
        self._resolved_parameters.append(resolved_parameter)

    def _resolve_parameters(self, step: Step) -> AbstractModuleParameters:
        """Resolve a step's parameters against the workflow's context."""
        parameters_class = step.module.value().get_parameters_class()
        parameters = step.parameters
        if isinstance(parameters, (str, Path)):
            parameters = parameters_class.from_file(
                self.parameters.resolve_path(Path(parameters)), self.parameters.context
            )
        elif isinstance(parameters, dict):
            parameters = parameters_class.from_dict(parameters, self.parameters.context)
        elif isinstance(parameters, AbstractModuleParameters):
            parameters = parameters.model_copy()
        return parameters

    def __repr__(self) -> str:
        """Return a human-readable string representation of the workflow."""
        step_count = len(self._steps)
        return f"Workflow '{self.parameters.name}' ({step_count} step{'s' if step_count != 1 else ''})"
