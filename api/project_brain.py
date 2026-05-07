"""Project Brain read-only API router.

This router is NOT mounted in api/main.py yet.
To activate, add the following to api/main.py (requires user confirmation
since api/main.py is a core file):

    from api.project_brain import router as project_brain_router
    app.include_router(project_brain_router)
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from governance.decision_log import GovernanceDecisionLog
from governance.policy import GovernancePolicy
from project_state.store import ProjectStateStore
from reports.task_reporter import TaskReport

router = APIRouter(prefix="/api/project-brain", tags=["project-brain"])

_ROOT = Path(__file__).resolve().parent.parent


def _project_root() -> Path:
    return _ROOT


def _reports_dir(project_id: str) -> Path:
    return _project_root() / "data" / "projects" / project_id / "reports"


# ──────────────────────────────────────────────
# GET /api/project-brain/projects/{project_id}/state
# ──────────────────────────────────────────────
@router.get("/projects/{project_id}/state")
def get_project_state(project_id: str) -> dict[str, Any]:
    store = ProjectStateStore(_project_root(), project_id)
    state = store.load()
    if state is None:
        raise HTTPException(status_code=404, detail=f"Project state not found for '{project_id}'.")
    return state.to_dict()


# ──────────────────────────────────────────────
# GET /api/project-brain/projects/{project_id}/reports
# ──────────────────────────────────────────────
@router.get("/projects/{project_id}/reports")
def list_reports(project_id: str) -> list[dict[str, Any]]:
    reports_dir = _reports_dir(project_id)
    if not reports_dir.is_dir():
        return []
    summaries: list[dict[str, Any]] = []
    for md_file in sorted(reports_dir.glob("*.md")):
        summaries.append({
            "project_id": project_id,
            "task_id": md_file.stem,
            "path": str(md_file.relative_to(_project_root())),
            "size_bytes": md_file.stat().st_size,
        })
    return summaries


# ──────────────────────────────────────────────
# GET /api/project-brain/projects/{project_id}/reports/{task_id}
# ──────────────────────────────────────────────
@router.get("/projects/{project_id}/reports/{task_id}")
def get_report(project_id: str, task_id: str) -> dict[str, Any]:
    reports_dir = _reports_dir(project_id)
    md_path = reports_dir / f"{task_id}.md"
    if not md_path.is_file():
        raise HTTPException(status_code=404, detail=f"Report '{task_id}' not found.")
    return {
        "project_id": project_id,
        "task_id": task_id,
        "path": str(md_path.relative_to(_project_root())),
        "markdown": md_path.read_text(encoding="utf-8"),
    }


# ──────────────────────────────────────────────
# POST /api/project-brain/projects/{project_id}/governance/review
# ──────────────────────────────────────────────
@router.post("/projects/{project_id}/governance/review")
def governance_review(
    project_id: str,
    files: list[str] | None = Query(default=None),
    actions: list[str] | None = Query(default=None),
) -> dict[str, Any]:
    policy = GovernancePolicy.from_project_root(_project_root())
    review = policy.review(files or [], actions or [])
    return {
        "project_id": project_id,
        **asdict(review),
    }


# ──────────────────────────────────────────────
# GET /api/project-brain/projects/{project_id}/governance/decisions
# ──────────────────────────────────────────────
@router.get("/projects/{project_id}/governance/decisions")
def list_governance_decisions(project_id: str) -> list[dict[str, Any]]:
    log = GovernanceDecisionLog(_project_root(), project_id)
    return [d.to_dict() for d in log.read_all()]


# ──────────────────────────────────────────────
# GET /api/project-brain/projects/{project_id}/memory/candidates
# ──────────────────────────────────────────────
@router.get("/projects/{project_id}/memory/candidates")
def list_memory_candidates(
    project_id: str,
    task_id: str | None = Query(default=None),
) -> dict[str, Any]:
    db_path = _project_root() / "data" / "projects" / project_id / "project_memory.db"
    if not db_path.exists():
        return {"project_id": project_id, "candidates": [], "total": 0}

    import sqlite3

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, collection, content, metadata FROM memories ORDER BY id DESC LIMIT 200"
        ).fetchall()
    except Exception:
        return {"project_id": project_id, "candidates": [], "total": 0}
    finally:
        conn.close()

    candidates: list[dict[str, Any]] = []
    for row in rows:
        meta = {}
        try:
            meta = json.loads(row["metadata"]) if row["metadata"] else {}
        except (json.JSONDecodeError, TypeError):
            pass
        if task_id and meta.get("task_id") != task_id:
            continue
        candidates.append({
            "memory_id": row["id"],
            "collection": row["collection"],
            "content": row["content"],
            "metadata": meta,
            "status": "remembered",
        })
    return {"project_id": project_id, "candidates": candidates, "total": len(candidates)}


# ──────────────────────────────────────────────
# GET /api/project-brain/projects/{project_id}/metrics
# ──────────────────────────────────────────────
@router.get("/projects/{project_id}/metrics")
def get_metrics_summary(project_id: str) -> dict[str, Any]:
    from reports.metrics import MetricsCollector
    collector = MetricsCollector(_project_root(), project_id)
    return {"project_id": project_id, **collector.summary()}


# ──────────────────────────────────────────────
# GET /api/project-brain/projects/{project_id}/metrics/history
# ──────────────────────────────────────────────
@router.get("/projects/{project_id}/metrics/history")
def get_metrics_history(project_id: str) -> list[dict[str, Any]]:
    from reports.metrics import MetricsCollector
    collector = MetricsCollector(_project_root(), project_id)
    return [m.to_dict() for m in collector.read_all()]
