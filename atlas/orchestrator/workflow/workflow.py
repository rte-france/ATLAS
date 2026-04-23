"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pathlib import Path

from atlas.abstract_class.dataset import AbstractDataset
from atlas.abstract_class.orchestrator import AbstractOrchestrator
from atlas.io_utils.parameters import ContextParameters
from atlas.orchestrator.workflow.job import Step, WorkflowJob
from atlas.orchestrator.workflow.parameters import WorkflowParameters


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
        self.build_jobs()

    @classmethod
    def from_file(cls, file_path: str | Path, context: ContextParameters | None = None) -> Workflow:
        file_path = Path(file_path)
        parameters = WorkflowParameters.from_file(file_path=file_path)
        if context is not None:
            parameters.context.use(context)
        parameters._orchestrator_path = file_path.parent
        return cls(parameters=parameters)

    def build_jobs(self):
        Step.add_index_in_step_name(self.parameters.steps)

        for step in self.parameters.steps:
            parameters = (
                step.module.value()
                .get_parameters_class()
                .from_file(self.parameters.resolve_path(step.parameters_path), self.parameters.context)
            )
            parameters.output.output_dir = self.parameters.resolve_path(self.parameters.output_dir) / step.name
            workflow_job = WorkflowJob(step.name, step.module.value, parameters)
            self.add_job(workflow_job)

    @property
    def jobs(self) -> list[WorkflowJob]:
        """
        Access the workflow jobs.

        :return: The list of WorkflowJob instances.
        """
        return self._jobs

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

    def get_output_dataset(self) -> AbstractDataset | None:
        """Returns the final dataset of the workflow"""
        return self.jobs[-1].get_output_dataset()

    def __repr__(self) -> str:
        """Return a human-readable string representation of the workflow."""
        step_count = len(self._jobs)
        return f"Workflow '{self.parameters.name}' ({step_count} step{'s' if step_count != 1 else ''})"
