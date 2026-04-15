"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from atlas.abstract_class.orchestrator import AbstractOrchestrator
from atlas.orchestrator.workflow.job import WorkflowJob
from atlas.orchestrator.workflow.parameters import Step, WorkflowParameters


class Workflow(AbstractOrchestrator[WorkflowParameters, WorkflowJob]):
    """A structure for managing the sequential execution of multiple modules through a list of workflow jobs.

    Each job processes the output of the previous one, starting from the input dataset."""

    def __init__(self, parameters: WorkflowParameters):
        """Initialize a Workflow instance.

        :param parameters: Name of the workflow.
        :type parameters: WorkflowParameters
        """
        self.parameters = parameters
        self._jobs: list[WorkflowJob] = []

        self.build_generic_module_parameters()  # FIXME we have to run this function in any __init__() that inherit the class AbstractOrchestrator, any way to ensure that is done? super().__init()__ seems impossible
        self.build_jobs()

    @classmethod
    def from_file(cls, file_path: str | Path) -> Workflow:
        file_path = Path(file_path)
        parameters = WorkflowParameters.from_file(file_path=file_path)
        parameters._orchestrator_path = file_path.parent
        return cls(parameters=parameters)

    def build_jobs(self):
        Step.add_index_in_step_name(self.parameters.steps)

        for step in self.parameters.steps:
            parameters = self.build_module_parameters(self.parameters.resolve_path(step.parameters_path))
            if "output" not in parameters:
                parameters["output"] = {}
            parameters["output"]["output_dir"] = self.parameters.resolve_path(self.parameters.output_dir) / step.name
            workflow_job = WorkflowJob(step.name, step.module.value, parameters)
            self.add_job(workflow_job)

    @property
    def jobs(self) -> Iterator[WorkflowJob]:
        """
        Access the workflow jobs.

        :return: The list of WorkflowJob instances.
        """
        return iter(self._jobs)

    @property
    def jobs_count(self) -> int:
        return len(self._jobs)

    def add_job(self, job: WorkflowJob | list[WorkflowJob]) -> None:
        """Add one or multiple jobs to the end of the workflow."""
        if isinstance(job, list):
            if not all(isinstance(s, WorkflowJob) for s in job):
                raise TypeError("All items in the list must be WorkflowJob instances.")
            self._jobs.extend(job)
        else:
            if not isinstance(job, WorkflowJob):
                raise TypeError(f"Expected a WorkflowJob instance, got {type(job).__name__}.")
            self._jobs.append(job)

    def __repr__(self) -> str:
        """Return a human-readable string representation of the workflow."""
        step_count = len(self._jobs)
        return f"Workflow '{self.parameters.name}' ({step_count} step{'s' if step_count != 1 else ''})"
