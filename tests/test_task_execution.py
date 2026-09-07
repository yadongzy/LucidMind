import pytest

from task_execution import (
    ExecutionControl,
    RetryPolicy,
    TaskCancelled,
    classify_failure,
)
from task_model import FailureReason


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
