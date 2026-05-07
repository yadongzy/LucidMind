"""Task metrics collection for Project Brain (§15 of execution plan)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class TaskMetrics:
    project_id: str
    task_id: str
    files_inspected: int = 0
    files_changed: int = 0
    tools_called: int = 0
    test_commands_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    recovery_attempts: int = 0
    approvals_requested: int = 0
    report_generated: bool = False
    memory_candidates: int = 0
    completion_status: str = "partial"
    duration_ms: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


class MetricsCollector:
    def __init__(self, root: str | Path, project_id: str = "lucidmind"):
        self.root = Path(root)
        self.project_id = project_id
        self.path = self.root / "data" / "projects" / project_id / "metrics.jsonl"

    def record(self, metrics: TaskMetrics) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(metrics.to_dict(), ensure_ascii=False) + "\n")
        return self.path

    def read_all(self) -> list[TaskMetrics]:
        if not self.path.exists():
            return []
        results: list[TaskMetrics] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            results.append(TaskMetrics(**{k: v for k, v in data.items() if k in TaskMetrics.__dataclass_fields__}))
        return results

    def summary(self) -> dict:
        all_metrics = self.read_all()
        if not all_metrics:
            return {"total_tasks": 0}
        return {
            "total_tasks": len(all_metrics),
            "complete": sum(1 for m in all_metrics if m.completion_status == "complete"),
            "partial": sum(1 for m in all_metrics if m.completion_status == "partial"),
            "blocked": sum(1 for m in all_metrics if m.completion_status == "blocked"),
            "total_files_changed": sum(m.files_changed for m in all_metrics),
            "total_tools_called": sum(m.tools_called for m in all_metrics),
            "total_tests_run": sum(m.test_commands_run for m in all_metrics),
            "total_approvals": sum(m.approvals_requested for m in all_metrics),
            "total_memory_candidates": sum(m.memory_candidates for m in all_metrics),
            "reports_generated": sum(1 for m in all_metrics if m.report_generated),
        }
