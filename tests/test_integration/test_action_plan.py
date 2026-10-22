from pathlib import Path
from typing import cast

import pendulum
import pytest

from atlas.orchestrator.current_input_state import CurrentInputState
from atlas.orchestrator.actionplan.action_plan import ActionPlan
from tests.utils import check_execution_time

DAY_AHEAD_ACTION_PLAN_CONFIG = Path("tests/dataset/parameters/day_ahead/action_plan.yml")

ACTION_PLAN_CONFIGS = [
    pytest.param(
        DAY_AHEAD_ACTION_PLAN_CONFIG,
        id="day_ahead",
        marks=pytest.mark.skipif(
            not DAY_AHEAD_ACTION_PLAN_CONFIG.exists(),
            reason=f"Action plan config not found: {DAY_AHEAD_ACTION_PLAN_CONFIG}",
        ),
    ),
]


@pytest.fixture(scope="class", params=ACTION_PLAN_CONFIGS)
def executed_action_plan(request):
    action_plan_config = request.param
    action_plan = ActionPlan.from_file(action_plan_config)
    initial_cis = CurrentInputState.from_directory(action_plan.parameters.resolve_path(action_plan.parameters.dataset_path))
    start = pendulum.now()
    final_cis = action_plan.execute()
    elapsed = (pendulum.now() - start).total_seconds()
    print(f"Action_plan completed in {elapsed:.3f}s")
    return action_plan, initial_cis, final_cis, elapsed, action_plan_config


class TestActionPlanIntegration:
    def test_action_plan_produce_output(self, executed_action_plan):
        action_plan, _, _, _, _ = executed_action_plan
        action_plan = cast(ActionPlan, action_plan)
        assert action_plan.final_result is not None

    def test_action_plan_cis_is_modified_after_execution(self, executed_action_plan):
        _, initial_cis, final_cis, _, _ = executed_action_plan
        diff = final_cis.diff(initial_cis)
        assert any(len(changes) > 0 for model_diff in diff.values() for changes in model_diff.values()), (
            "CIS was not modified after action plan execution"
        )

    @pytest.mark.perf
    def test_action_plan_execution_time_within_threshold(self, executed_action_plan):
        _, _, _, elapsed, action_plan_config = executed_action_plan
        key = action_plan_config.parent.name
        check_execution_time(f"actionplan[{key}]", elapsed, key, field="action_plan_execution_max_seconds")
