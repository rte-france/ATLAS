"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from collections.abc import Iterator

from atlas.abstract_class.orchestrator import AbstractOrchestrator
from atlas.orchestrator.workflow.job import WorkflowJob
from atlas.orchestrator.workflow.parameters import Step, WorkflowParameters


class Workflow(AbstractOrchestrator[WorkflowParameters, WorkflowJob]):
    """A structure for managing the sequential execution of multiple modules through a list of workflow jobs.

    Each job processes the output of the previous one, starting from the input dataset."""

    @classmethod
    def get_param_class(cls):
        return WorkflowParameters

    def __init__(self, parameters: WorkflowParameters, prefix_job_name: str = ""):
        """Initialize a Workflow instance.

        :param parameters: Name of the workflow.
        :type parameters: WorkflowParameters
        """
        super().__init__(parameters)
        self._jobs: list[WorkflowJob] = []
        self.build_jobs(prefix_job_name)

    def build_jobs(self, prefix_job_name: str):
        Step.add_index_in_step_name(self.parameters.steps)

        for step in self.parameters.steps:
            parameters_class = step.module.value().get_parameters_class()
            if step.parameters_path is not None:
                parameters = parameters_class.from_file(
                    self.parameters.resolve_path(step.parameters_path), self.parameters.context
                )
            else:
                parameters = parameters_class.from_dict(step.parameters, self.parameters.context)
            parameters.output.output_dir = self.parameters.resolve_path(self.parameters.output_dir) / step.name
            if prefix_job_name == "":
                job_name = step.name
            else:
                job_name = f"{prefix_job_name} {step.name}"
            workflow_job = WorkflowJob(f"{job_name!r}", step.module.value, parameters)
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
