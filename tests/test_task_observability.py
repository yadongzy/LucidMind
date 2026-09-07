from datetime import datetime, timedelta

from task_observability import build_readiness, build_task_metrics


def test_metrics_cover_required_task_signals_without_mutation():
    now = datetime(2026, 9, 7, 12, 0, 0)
    created = now - timedelta(seconds=30)
    running = now - timedelta(seconds=20)
    store = {"tasks": [
        {
            "status": "completed", "created_at": created.isoformat(),
            "running_at": running.isoformat(), "completed_at": now.isoformat(),
            "retries": 1, "attempts": [{}, {}],
        },
        {
            "status": "cancelled", "created_at": created.isoformat(),
            "running_at": running.isoformat(), "completed_at": now.isoformat(),
            "retries": 0, "attempts": [{}],
        },
        {
            "status": "ready", "created_at": created.isoformat(),
            "updated_at": created.isoformat(), "retries": 0, "attempts": [],
            "failure_reason": "system_interrupted",
        },
    ]}
    original = repr(store)
    metrics = build_task_metrics(store, now=now)
    assert metrics["queue_depth"] == 1
    assert metrics["success_rate"] == 0.5
    assert metrics["retry_rate"] == 0.3333
    assert metrics["cancel_rate"] == 0.5
    assert metrics["recovery_rate"] == 1.0
    assert metrics["waiting_time_s"] == {"count": 2, "avg": 10.0, "max": 10.0}
    assert metrics["execution_time_s"] == {"count": 2, "avg": 20.0, "max": 20.0}
    assert metrics["max_no_progress_s"] == 30.0
    assert repr(store) == original


def test_readiness_distinguishes_uninitialized_degraded_and_ready():
    assert build_readiness(initialized=False, llm_available=False) == {
        "ready": False, "degraded": False, "reasons": ["not_initialized"]
    }
    assert build_readiness(initialized=True, llm_available=False) == {
        "ready": False, "degraded": True, "reasons": ["llm_unavailable"]
    }
    assert build_readiness(initialized=True, llm_available=True) == {
        "ready": True, "degraded": False, "reasons": []
    }


def test_readiness_refuses_new_work_while_gateway_is_draining():
    result = build_readiness(
        initialized=True, llm_available=True,
        daemon_status={"command_queue": {"gateway_draining": True}},
    )
    assert result == {
        "ready": False, "degraded": True, "reasons": ["gateway_draining"]
    }
