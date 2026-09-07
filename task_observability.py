"""Pure task metrics and readiness snapshots for the safety control plane."""

from datetime import datetime
from typing import Optional


def build_task_metrics(
    store: dict,
    *,
    now: Optional[datetime] = None,
) -> dict:
    """Derive bounded operational metrics without mutating persisted tasks."""
    now = now or datetime.now()
    tasks = store.get("tasks", [])
    by_status: dict[str, int] = {}
    attempts = 0
    retries = 0
    execution_durations = []
    waiting_durations = []
    no_progress_durations = []

    for task in tasks:
        status = task.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        attempts += len(task.get("attempts") or [])
        retries += int(task.get("retries") or 0)

        created = _parse_time(task.get("created_at"))
        running = _parse_time(task.get("running_at"))
        completed = _parse_time(task.get("completed_at"))
        updated = _parse_time(task.get("updated_at")) or running or created
        if created and running:
            waiting_durations.append(max(0.0, (running - created).total_seconds()))
        if running:
            execution_durations.append(
                max(0.0, ((completed or now) - running).total_seconds())
            )
        if status in ("ready", "running", "blocked") and updated:
            no_progress_durations.append(max(0.0, (now - updated).total_seconds()))

    terminal = sum(by_status.get(name, 0) for name in (
        "completed", "failed", "escalated", "cancelled"
    ))
    completed_count = by_status.get("completed", 0)
    return {
        "total": len(tasks),
        "by_status": by_status,
        "queue_depth": by_status.get("ready", 0) + by_status.get("blocked", 0),
        "attempts": attempts,
        "retries": retries,
        "success_rate": _ratio(completed_count, terminal),
        "retry_rate": _ratio(retries, attempts),
        "cancel_rate": _ratio(by_status.get("cancelled", 0), terminal),
        "recovery_rate": _recovery_rate(tasks),
        "waiting_time_s": _duration_summary(waiting_durations),
        "execution_time_s": _duration_summary(execution_durations),
        "max_no_progress_s": max(no_progress_durations, default=0.0),
    }


def build_readiness(
    *,
    initialized: bool,
    llm_available: bool,
    daemon_status: Optional[dict] = None,
) -> dict:
    """Return explicit ready/degraded state with machine-readable reasons."""
    reasons = []
    if not initialized:
        reasons.append("not_initialized")
    if initialized and not llm_available:
        reasons.append("llm_unavailable")
    if daemon_status and daemon_status.get("command_queue", {}).get("gateway_draining"):
        reasons.append("gateway_draining")
    return {
        "ready": not reasons,
        "degraded": bool(reasons) and initialized,
        "reasons": reasons,
    }


def _parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _duration_summary(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "avg": 0.0, "max": 0.0}
    return {
        "count": len(values),
        "avg": round(sum(values) / len(values), 3),
        "max": round(max(values), 3),
    }


def _recovery_rate(tasks: list[dict]) -> float:
    interrupted = [
        task for task in tasks
        if task.get("failure_reason") == "system_interrupted"
    ]
    recovered = sum(
        task.get("status") in ("ready", "completed")
        for task in interrupted
    )
    return _ratio(recovered, len(interrupted))
