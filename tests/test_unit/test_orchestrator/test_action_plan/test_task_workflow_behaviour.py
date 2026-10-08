"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Behaviour of a `TaskWorkflow` inside an action plan, from an action plan written as YAML.

Some tests below are marked `xfail(strict=True)`: they describe the documented behaviour, which the code does not
implement yet (see each `reason`). They are strict on purpose: once a bug is fixed the test starts passing, pytest
reports it as a failure, and the `xfail` mark has to be removed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pendulum import DateTime, Duration, duration

from atlas.orchestrator.actionplan.action_plan import ActionPlan
from atlas.orchestrator.actionplan.parameters import TaskWorkflow

# dates are overwritten per iteration by the action plan, only the timestep is kept
MODULE_PARAMETERS = {"temporal": {"timestep": "PT1H"}}
# a `TaskWorkflow` built directly from a `Path` loads its workflow immediately, before any action plan can provide
# the dates: its steps then need complete parameters
MODULE_PARAMETERS_WITH_DATES = {
    "temporal": {
        "start_date": "2028-01-01 00:00:00",
        "end_date": "2028-01-02 00:00:00",
        "execution_date": "2027-12-31 12:00:00",
        "timestep": "PT1H",
    }
}
# a single iteration, so a single job per task (or per workflow step)
SCHEDULE = {"from_": "2028-01-01 00:00:00", "until": "2028-01-01 00:00:00", "frequency": "1d"}
# the same context is used by every test: `forced` and `default` both target the `solver` section
CONTEXT = {"forced": {"solver": {"solver_name": "SCIP"}}, "default": {"solver": {"timeout": "PT9M"}}}


def _write_yaml(path: Path, content: dict) -> Path:
    path.write_text(yaml.safe_dump(content))
    return path


def _module_parameters_file(tmp_path: Path, with_dates: bool = False) -> Path:
    return _write_yaml(
        tmp_path / "module_parameters.yml", MODULE_PARAMETERS_WITH_DATES if with_dates else MODULE_PARAMETERS
    )


def _workflow_config(
    tmp_path: Path, name: str | None = None, context: dict | None = None, with_dates: bool = False
) -> dict:
    (tmp_path / "dataset").mkdir(exist_ok=True)
    config: dict = {
        "dataset_path": str(tmp_path / "dataset"),
        "steps": [{"module": "MarketClearing", "parameters": str(_module_parameters_file(tmp_path, with_dates))}],
    }
    if name is not None:
        config["name"] = name
    if context is not None:
        config["context"] = context
    return config


def _action_plan(tmp_path: Path, task: dict, context: dict | None = None) -> ActionPlan:
    (tmp_path / "dataset").mkdir(exist_ok=True)
    config: dict = {
        "name": "test_action_plan",
        "dataset_path": str(tmp_path / "dataset"),
        "output_dir": str(tmp_path / "results"),
        "tasks": [{**SCHEDULE, **task}],
    }
    if context is not None:
        config["context"] = context
    return ActionPlan.from_file(_write_yaml(tmp_path / "action_plan.yaml", config))


class TestTaskWorkflowDefaultName:
    """Documented rule: a `TaskWorkflow` without `name` is named after the workflow's `name`, or after the file name
    when the workflow is given as a path."""

    @staticmethod
    def _build_task(workflow: Path | str) -> TaskWorkflow:
        return TaskWorkflow(
            workflow=workflow,
            from_=DateTime(2026, 1, 1),
            until=DateTime(2026, 1, 1),
            frequency=Duration(days=1),
        )

    def test_inline_workflow_takes_the_workflow_name(self, tmp_path):
        action_plan = _action_plan(tmp_path, {"workflow": _workflow_config(tmp_path, name="inline_workflow")})

        assert action_plan.parameters.tasks[0].name == "inline_workflow"

    def test_workflow_given_as_a_path_object_takes_the_file_stem(self, tmp_path):
        workflow_file = _write_yaml(tmp_path / "my_workflow.yaml", _workflow_config(tmp_path, with_dates=True))

        task = self._build_task(workflow_file)

        assert task.name == "my_workflow"

    @pytest.mark.xfail(
        strict=True,
        reason="TaskWorkflow._compute_default_name runs in a `before` validator and only handles a `Path`: "
        "a workflow given as a `str` is named 'unnamed'",
    )
    def test_workflow_given_as_a_str_takes_the_file_stem(self, tmp_path):
        workflow_file = _write_yaml(tmp_path / "my_workflow.yaml", _workflow_config(tmp_path, with_dates=True))

        task = self._build_task(str(workflow_file))

        assert task.name == "my_workflow"

    @pytest.mark.xfail(
        strict=True,
        reason="YAML always yields a `str` for the workflow path, so a path-defined TaskWorkflow is named 'unnamed'",
    )
    def test_workflow_path_written_in_yaml_takes_the_file_stem(self, tmp_path):
        workflow_file = _write_yaml(tmp_path / "my_workflow.yaml", _workflow_config(tmp_path))

        action_plan = _action_plan(tmp_path, {"workflow": str(workflow_file)})

        assert action_plan.parameters.tasks[0].name == "my_workflow"


class TestActionPlanContextOnTaskWorkflow:
    """Documented rule: the action plan `context` applies to *every* task's parameters, modules and workflows alike."""

    def test_context_reaches_a_task_module(self, tmp_path):
        """Control: the context is applied to the parameters of a `TaskModule`."""
        action_plan = _action_plan(
            tmp_path,
            {"module": "MarketClearing", "parameters": str(_module_parameters_file(tmp_path))},
            CONTEXT,
        )

        (job,) = list(action_plan.jobs)

        assert job.parameters.solver.solver_name == "SCIP"
        assert job.parameters.solver.timeout == duration(minutes=9)

    @pytest.mark.xfail(
        strict=True,
        reason="The action plan context is applied to the workflow's own parameters (a dict or a WorkflowParameters), "
        "which have no `solver` key: it never reaches the parameters of the workflow steps",
    )
    @pytest.mark.parametrize("workflow_kind", ["inline", "path"])
    def test_context_reaches_the_steps_of_a_task_workflow(self, tmp_path, workflow_kind):
        workflow_config = _workflow_config(tmp_path)
        if workflow_kind == "path":
            workflow = str(_write_yaml(tmp_path / "my_workflow.yaml", workflow_config))
        else:
            workflow = workflow_config
        action_plan = _action_plan(tmp_path, {"workflow": workflow}, CONTEXT)

        (job,) = list(action_plan.jobs)

        assert job.parameters.solver.solver_name == "SCIP"
        assert job.parameters.solver.timeout == duration(minutes=9)

    def test_context_declared_in_the_workflow_file_reaches_its_steps(self, tmp_path):
        """Workaround: a `context` written in the workflow itself does reach the steps."""
        workflow_file = _write_yaml(
            tmp_path / "my_workflow.yaml",
            _workflow_config(tmp_path, context={"forced": {"solver": {"solver_name": "HIGHS"}}}),
        )
        action_plan = _action_plan(tmp_path, {"workflow": str(workflow_file)})

        (job,) = list(action_plan.jobs)

        assert job.parameters.solver.solver_name == "HIGHS"
