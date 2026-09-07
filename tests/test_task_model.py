"""任务领域模型的契约测试。"""

from datetime import datetime

import pytest

from task_model import (
    Checkpoint,
    FailureReason,
    TaskAttempt,
    TaskStatus,
    can_transition,
    parse_status,
    transition,
)


def test_status_values_preserve_existing_storage_format():
    assert TaskStatus.READY.value == "ready"
    assert TaskStatus.RUNNING.value == "running"
    assert TaskStatus.COMPLETED.value == "completed"


@pytest.mark.parametrize(
    ("legacy", "canonical"),
    [
        ("pending", TaskStatus.READY),
        ("done", TaskStatus.COMPLETED),
        ("canceled", TaskStatus.CANCELLED),
    ],
)
def test_parse_status_supports_migration_aliases(legacy, canonical):
    assert parse_status(legacy) is canonical


def test_parse_status_rejects_unknown_value():
    with pytest.raises(ValueError, match="未知任务状态"):
        parse_status("mystery")


@pytest.mark.parametrize(
    ("source", "target"),
    [
        ("ready", "running"),
        ("running", "blocked"),
        ("running", "completed"),
        ("running", "ready"),
        ("blocked", "ready"),
        ("memo", "ready"),
    ],
)
def test_expected_lifecycle_transitions_are_allowed(source, target):
    assert can_transition(source, target)


def test_terminal_status_cannot_restart():
    assert not can_transition("completed", "running")
    assert not can_transition("failed", "ready")


def test_transition_updates_version_and_timestamp():
    task = {"status": "ready", "version": 2}
    result = transition(task, TaskStatus.RUNNING)
    assert result is task
    assert task["status"] == "running"
    assert task["version"] == 3
    datetime.fromisoformat(task["updated_at"])


def test_same_status_transition_is_idempotent():
    task = {"status": "running", "version": 4}
    transition(task, "running")
    assert task == {"status": "running", "version": 4}


def test_illegal_transition_does_not_mutate_task():
    task = {"status": "completed", "version": 1}
    with pytest.raises(ValueError, match="非法任务状态转换"):
        transition(task, "running")
    assert task == {"status": "completed", "version": 1}


def test_attempt_serializes_failure_reason_as_string():
    attempt = TaskAttempt(
        number=1,
        started_at="2026-09-07T12:00:00",
        finished_at="2026-09-07T12:00:01",
        failure_reason=FailureReason.TIMEOUT,
        error="deadline exceeded",
    )
    assert attempt.to_dict()["failure_reason"] == "timeout"


def test_checkpoint_copies_payload_for_serialization():
    payload = {"cursor": 3}
    checkpoint = Checkpoint(
        name="after-plan",
        created_at="2026-09-07T12:00:00",
        payload=payload,
    )
    serialized = checkpoint.to_dict()
    assert serialized["payload"] == {"cursor": 3}
    assert serialized["version"] == 1
