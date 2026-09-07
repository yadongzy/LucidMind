import pytest

from task_execution import (
    ExecutionControl, ExecutionPlan,
    RetryPolicy,
    TaskCancelled,
    classify_failure,
    compare_execution_plans,
)
from task_model import FailureReason


def test_safe_control_flags_are_fail_closed_by_default():
    import os
    import subprocess
    import sys

    env = os.environ.copy()
    for name in (
        "LUCIDMIND_SAFE_PIPELINE_ENABLED",
        "LUCIDMIND_SAFE_PIPELINE_SHADOW",
        "LUCIDMIND_ORPHAN_RECOVERY_ENABLED",
    ):
        env.pop(name, None)
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import brain_config as c; "
                "assert not c.SAFE_PIPELINE_ENABLED; "
                "assert not c.SAFE_PIPELINE_SHADOW; "
                "assert not c.ORPHAN_RECOVERY_ENABLED"
            ),
        ],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert probe.returncode == 0, probe.stderr


def test_retry_policy_applies_bounded_exponential_backoff_and_jitter():
    policy = RetryPolicy(base_delay_s=2, max_delay_s=5, jitter_ratio=0.25)
    assert policy.delay(1, random_value=0.5) == 2
    assert policy.delay(2, random_value=1) == 5
    assert policy.delay(9, random_value=0.5) == 5


def test_child_timeout_is_capped_by_parent_deadline():
    control = ExecutionControl(deadline_monotonic=110, clock=lambda: 100)
    assert control.remaining_timeout(30) == 10
    assert control.remaining_timeout(3) == 3


def test_expired_parent_deadline_stops_before_child_step():
    control = ExecutionControl(deadline_monotonic=99, clock=lambda: 100)
    with pytest.raises(TimeoutError):
        control.remaining_timeout(30)


def test_cooperative_cancellation_is_observed_only_at_safe_point():
    control = ExecutionControl(
        deadline_monotonic=200,
        clock=lambda: 100,
        is_cancel_requested=lambda: True,
    )
    with pytest.raises(TaskCancelled):
        control.checkpoint()


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (TaskCancelled(), FailureReason.CANCELLED),
        (TimeoutError(), FailureReason.TIMEOUT),
        (PermissionError(), FailureReason.PERMISSION),
        (ConnectionError(), FailureReason.INFRASTRUCTURE),
        (ValueError(), FailureReason.VALIDATION),
        (RuntimeError(), FailureReason.UNKNOWN),
    ],
)
def test_failure_classification(error, reason):
    assert classify_failure(error) is reason


def test_shadow_plan_comparison_is_pure_and_structured():
    plan = ExecutionPlan("t1", 120, 4, "task", False).to_dict()
    assert compare_execution_plans(plan, dict(plan)) == {}
    changed = dict(plan, timeout_s=30)
    assert compare_execution_plans(plan, changed) == {
        "timeout_s": {"legacy": 120, "safe": 30}
    }
