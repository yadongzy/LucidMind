"""现有任务调度器的正式特征化测试。"""

import json
from datetime import datetime, timedelta

import pytest


@pytest.fixture(autouse=True)
def isolated_queue(tmp_path, monkeypatch):
    """所有 I/O 指向临时目录，禁止接触真实运行队列。"""

    import task_dispatcher_utils as storage

    monkeypatch.setattr(storage, "_DATA", tmp_path)
    monkeypatch.setattr(storage, "_QUEUE_FILE", tmp_path / "task_queue.json")


def stored_task(task_id):
    import task_dispatcher as dispatcher

    return next(task for task in dispatcher._load_store()["tasks"] if task["id"] == task_id)


def test_enqueue_and_dequeue_preserve_priority_and_status():
    import task_dispatcher as dispatcher

    dispatcher.enqueue("低优先级", priority="P3")
    expected = dispatcher.enqueue("高优先级", priority="P0", source="user")
    selected = dispatcher.dequeue()
    assert selected["id"] == expected["id"]
    assert selected["status"] == "running"
    assert selected["running_at"] is not None


def test_duplicate_ready_task_is_idempotent():
    import task_dispatcher as dispatcher

    first = dispatcher.enqueue("同一任务", priority="P1")
    second = dispatcher.enqueue("同一任务", priority="P1")
    assert second["id"] == first["id"]
    assert len(dispatcher._load_store()["tasks"]) == 1


def test_explicit_idempotency_key_deduplicates_across_state_and_payload():
    import task_dispatcher as dispatcher

    first = dispatcher.enqueue("原始任务", idempotency_key="request-42")
    dispatcher.dequeue()
    second = dispatcher.enqueue("重放但内容不同", idempotency_key="request-42")
    assert second["id"] == first["id"]
    assert len(dispatcher._load_store()["tasks"]) == 1


def test_new_task_contains_migration_safe_execution_metadata():
    import task_dispatcher as dispatcher

    task = dispatcher.enqueue("任务", idempotency_key="request-1")
    assert task["version"] == 0
    assert task["lease_owner"] is None
    assert task["attempts"] == []
    assert task["checkpoints"] == []
    assert task["cancel_requested"] is False


def test_task_cancel_request_and_safe_point_completion():
    import task_dispatcher as dispatcher

    task = dispatcher.enqueue("可取消任务")
    dispatcher.dequeue()
    assert dispatcher.request_task_cancel(task["id"]) is True
    assert dispatcher.is_cancel_requested(task["id"]) is True
    assert dispatcher.cancel_task(task["id"], "安全点取消") is True
    stored = dispatcher._load_store()["tasks"][0]
    assert stored["status"] == "cancelled"
    assert stored["failure_reason"] == "cancelled"


def test_complete_clears_running_timestamp():
    import task_dispatcher as dispatcher

    task = dispatcher.enqueue("任务", priority="P1")
    dispatcher.dequeue()
    dispatcher.complete_task(task["id"])
    saved = stored_task(task["id"])
    assert saved["status"] == "completed"
    assert saved["running_at"] is None
    assert saved["version"] == 2


def test_progress_uses_idempotent_central_transition():
    import task_dispatcher as dispatcher

    task = dispatcher.enqueue("任务", priority="P1")
    dispatcher.update_task_progress(task["id"], "处理中")
    first = stored_task(task["id"])
    assert first["status"] == "running"
    assert first["version"] == 1
    dispatcher.update_task_progress(task["id"], "仍在处理")
    second = stored_task(task["id"])
    assert second["version"] == 1


def test_failure_retries_before_escalation(monkeypatch):
    import task_dispatcher as dispatcher

    monkeypatch.setattr(dispatcher, "_notify_escalation", lambda task: None)
    task = dispatcher.enqueue("任务", priority="P1", max_retries=2)
    dispatcher.dequeue()
    dispatcher.fail_task(task["id"], "第一次失败")
    assert stored_task(task["id"])["status"] == "ready"
    dispatcher.dequeue()
    dispatcher.fail_task(task["id"], "第二次失败")
    saved = stored_task(task["id"])
    assert saved["status"] == "escalated"
    assert saved["retries"] == 2


def test_stuck_running_task_is_released_for_retry():
    import task_dispatcher as dispatcher

    task = dispatcher.enqueue("任务", priority="P1", timeout_s=1)
    dispatcher.dequeue()
    store = dispatcher._load_store()
    store["tasks"][0]["running_at"] = (
        datetime.now() - timedelta(seconds=10)
    ).isoformat()
    dispatcher._save_store(store)
    assert dispatcher.release_stuck_tasks() == 1
    saved = stored_task(task["id"])
    assert saved["status"] == "ready"
    assert saved["retries"] == 1


def test_atomic_storage_remains_valid_json():
    import task_dispatcher as dispatcher
    import task_dispatcher_utils as storage

    dispatcher.enqueue("任务1")
    dispatcher.enqueue("任务2")
    dispatcher.enqueue("任务3")
    parsed = json.loads(storage._QUEUE_FILE.read_text("utf-8"))
    assert parsed["version"] == 1
    assert len(parsed["tasks"]) == 3
