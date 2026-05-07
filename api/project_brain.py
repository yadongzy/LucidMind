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


# ──────────────────────────────────────────────
# POST /api/project-brain/checkup
# ──────────────────────────────────────────────
@router.post("/checkup")
def run_checkup(project_id: str = "lucidmind") -> dict[str, Any]:
    """执行项目体检，返回完整报告。"""
    from checkup.runner import ProjectCheckupRunner
    runner = ProjectCheckupRunner(_project_root(), project_id)
    report = runner.run_all()
    return report.to_dict()


# ──────────────────────────────────────────────
# GET /api/project-brain/checkup/latest
# ──────────────────────────────────────────────
@router.get("/checkup/latest")
def get_latest_checkup(project_id: str = "lucidmind") -> dict[str, Any]:
    """获取最近一次体检报告。"""
    report_dir = _project_root() / "data" / "checkup"
    if not report_dir.exists():
        raise HTTPException(status_code=404, detail="无体检报告")
    files = sorted(report_dir.glob("report_*.json"), reverse=True)
    if not files:
        raise HTTPException(status_code=404, detail="无体检报告")
    return json.loads(files[0].read_text("utf-8"))


# ──────────────────────────────────────────────
# POST /api/project-brain/diagnose
# ──────────────────────────────────────────────
@router.post("/diagnose")
def run_diagnosis(project_id: str = "lucidmind") -> dict[str, Any]:
    """体检 + 诊断（不修复），返回诊断报告含分级。"""
    from checkup.runner import ProjectCheckupRunner
    from checkup.diagnosis import diagnose_checkup
    runner = ProjectCheckupRunner(_project_root(), project_id)
    checkup = runner.run_all()
    diagnosis = diagnose_checkup(checkup.to_dict())
    return {
        "checkup_score": checkup.score,
        "diagnosis": diagnosis.to_dict(),
    }


# ──────────────────────────────────────────────
# POST /api/project-brain/auto-repair
# ──────────────────────────────────────────────
@router.post("/auto-repair")
def run_auto_repair(project_id: str = "lucidmind") -> dict[str, Any]:
    """完整闭环: 体检 → 诊断 → 自动修复 L0/L1 → 重新验证。"""
    from checkup.auto_repair import AutoRepairPipeline
    pipeline = AutoRepairPipeline(_project_root(), project_id)
    return pipeline.run_full_pipeline()


# ──────────────────────────────────────────────
# GET /api/project-brain/evolution
# ──────────────────────────────────────────────
@router.get("/evolution")
def get_evolution_log(limit: int = 20) -> dict[str, Any]:
    """获取进化日志。"""
    from checkup.evolution_log import EvolutionLog
    log = EvolutionLog()
    return {
        "stats": log.get_stats(),
        "recent": log.get_recent(limit),
    }


# ──────────────────────────────────────────────
# GET /api/project-brain/behavior
# ──────────────────────────────────────────────
@router.get("/behavior")
def get_behavior_patterns() -> dict[str, Any]:
    """分析用户行为模式，返回模式 + 建议。"""
    from checkup.user_behavior import UserBehaviorAnalyzer
    analyzer = UserBehaviorAnalyzer()
    patterns = analyzer.analyze()
    suggestions = analyzer.generate_suggestions(patterns)
    return {
        "patterns": [p.to_dict() for p in patterns],
        "suggestions": [s.to_dict() for s in suggestions],
    }


# ──────────────────────────────────────────────
# POST /api/project-brain/negotiate
# ──────────────────────────────────────────────
@router.post("/negotiate")
def negotiate(problem: str, context: str = "") -> dict[str, Any]:
    """创建 Brain-Codex 协商请求，返回 prompt（供 Codex 消费）。"""
    from checkup.negotiation import NegotiationProtocol
    proto = NegotiationProtocol()
    req = proto.create_request(problem, context)
    return {
        "request": req.to_dict(),
        "prompt": req.to_prompt(),
    }


# ──────────────────────────────────────────────
# POST /api/project-brain/reflection
# ──────────────────────────────────────────────
@router.post("/reflection")
def generate_reflection_report(project_id: str = "lucidmind") -> dict[str, Any]:
    """生成 REFLECTION.md 并返回内容。"""
    from checkup.runner import ProjectCheckupRunner
    from checkup.evolution_log import EvolutionLog
    from checkup.user_behavior import UserBehaviorAnalyzer
    from checkup.reflection_gen import save_reflection

    runner = ProjectCheckupRunner(_project_root(), project_id)
    checkup = runner.run_all()

    evo = EvolutionLog()
    analyzer = UserBehaviorAnalyzer()
    patterns = analyzer.analyze()
    suggestions = analyzer.generate_suggestions(patterns)

    path = save_reflection(
        checkup_report=checkup.to_dict(),
        evolution_stats=evo.get_stats(),
        behavior_patterns=[p.to_dict() for p in patterns],
        suggestions=[s.to_dict() for s in suggestions],
    )
    content = path.read_text("utf-8")
    return {"path": str(path), "content": content}


# ──────────────────────────────────────────────
# POST /api/project-brain/repair-plan
# ──────────────────────────────────────────────
@router.post("/repair-plan")
def get_repair_plan(project_id: str = "lucidmind") -> dict[str, Any]:
    """生成 L2-L3 修复计划 + L4 报告（不执行）。"""
    from checkup.runner import ProjectCheckupRunner
    from checkup.diagnosis import diagnose_checkup
    from checkup.codex_repair import CodexRepairEngine

    runner = ProjectCheckupRunner(_project_root(), project_id)
    checkup = runner.run_all()
    diagnosis = diagnose_checkup(checkup.to_dict())

    engine = CodexRepairEngine(_project_root(), project_id)
    l2_l3_plans = engine.plan_repairs(diagnosis)
    l4_reports = engine.generate_l4_report(diagnosis)

    return {
        "checkup_score": checkup.score,
        "l2_l3_plans": l2_l3_plans,
        "l4_reports": l4_reports,
        "total_issues": len(diagnosis.items),
    }
