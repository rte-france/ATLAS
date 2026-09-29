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
from atlas.custom_errors import UseContextError
from atlas.io_utils.parameters import ContextParameters
from atlas.orchestrator.workflow.job import WorkflowJob
from atlas.orchestrator.workflow.parameters import ResolvedStep, Step, WorkflowParameters


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
        self._raw_steps: list[tuple[Step, str | None]] = []
        self._resolved_steps: list[ResolvedStep] = []
        for step in self.parameters.steps:
            self.add_step(step, prefix_job_name)

    @property
    def jobs(self) -> Iterator[WorkflowJob]:
        """
        Generate and return the workflow jobs.

        :return: The list of WorkflowJob instances.
        """
        for resolved_step in self._resolved_steps:
            parameters = resolved_step.parameters.model_copy(deep=True)
            yield WorkflowJob(f"{resolved_step.name!r}", resolved_step.module.value, parameters)

    @property
    def jobs_count(self) -> int:
        return len(self._resolved_steps)

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
        self._raw_steps.append((step, prefix_job_name))
        resolved_step = self._resolve_step(step, prefix_job_name)
        self._resolved_steps.append(resolved_step)

    def _resolve_step(self, step: Step, prefix_job_name: str | None) -> ResolvedStep:
        """Rename `step` with `prefix_job_name` if given, and resolve its parameters against the
        workflow's current context.

        :raises ValueError: if the step's parameters cannot be resolved.
        """
        # Rename before resolving: the step output directory is derived from step.name, and iterations of a same
        # action plan task only differ by this prefix.
        named_step = step.model_copy(update={"name": f"{prefix_job_name} {step.name}"}) if prefix_job_name else step
        try:
            resolved_parameters = self._build_step_parameters(named_step)
        except Exception as exc:
            raise ValueError(f"Step {named_step.name!r}: unable to resolve parameters ({exc})") from exc

        return ResolvedStep(name=named_step.name, module=named_step.module, parameters=resolved_parameters)

    def _build_step_parameters(self, step: Step) -> AbstractModuleParameters:
        """Build a step's parameters against the workflow's context."""
        parameters_class = step.module.value().get_parameters_class()
        if isinstance(step.parameters, (str, Path)):
            contextualized_parameters = parameters_class.from_file(
                self.parameters.resolve_path(Path(step.parameters)), self.context
            )
        elif isinstance(step.parameters, dict):
            contextualized_parameters = parameters_class.from_dict(step.parameters, self.context)
        elif isinstance(step.parameters, AbstractModuleParameters):
            contextualized_parameters = self.context.apply_on_parameters(step.parameters)
        else:
            contextualized_parameters = step.parameters
        step_output_dir = self.parameters.resolve_path(self.parameters.output_dir) / step.name
        return contextualized_parameters.evolve(
            output=contextualized_parameters.output.evolve(output_dir=step_output_dir)
        )

    def _rebuild(self, previous_context: ContextParameters, attempted_context: ContextParameters) -> None:
        """
        Re-resolve every step already added to this workflow against the attempted context.

        If re-resolving fails (e.g. it produces invalid parameters), raise `UseContextError` (built from `previous_context` and `attempted_context`)
        and leave this workflow entirely unchanged.

        :raises UseContextError: if a step can no longer be resolved with the new context.
        """
        new_resolved_steps: list[ResolvedStep] = []
        for step, prefix_job_name in self._raw_steps:
            try:
                new_resolved_step = self._resolve_step(step, prefix_job_name)
            except Exception as exc:
                raise UseContextError(
                    f"Step {step.name!r}: could not be resolved with the new context ({exc})",
                    job_name=step.name,
                    previous_context=previous_context,
                    attempted_context=attempted_context,
                    original_error=exc,
                ) from exc
            new_resolved_steps.append(new_resolved_step)
        self._resolved_steps = new_resolved_steps

    @property
    def context(self):
        return self.parameters.context

    def __repr__(self) -> str:
        """Return a human-readable string representation of the workflow."""
        step_count = len(self._resolved_steps)
        return f"Workflow '{self.parameters.name}' ({step_count} step{'s' if step_count != 1 else ''})"
