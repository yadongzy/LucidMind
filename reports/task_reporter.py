"""Markdown task report generator."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class TaskReport:
    task_id: str
    title: str
    goal: str
    project_id: str = "lucidmind"
    context_loaded: list[str] = field(default_factory=list)
    plan: list[str] = field(default_factory=list)
    actions_taken: list[str] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    tests_run: list[str] = field(default_factory=list)
    result: str = "partial"
    risks: list[str] = field(default_factory=list)
    decisions_to_remember: list[str] = field(default_factory=list)
    governance_result: str = "not-reviewed"
    protected_files: list[str] = field(default_factory=list)
    required_confirmations: list[str] = field(default_factory=list)
    dangerous_actions: list[str] = field(default_factory=list)
    next_suggested_step: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TaskReportGenerator:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def report_path(self, report: TaskReport) -> Path:
        slug = self._slug(report.task_id)
        return self.root / "data" / "projects" / report.project_id / "reports" / f"{slug}.md"

    def save(self, report: TaskReport) -> Path:
        path = self.report_path(report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render(report), encoding="utf-8")
        return path

    def render(self, report: TaskReport) -> str:
        return "\n".join([
            f"# Task Report: {report.title}",
            "",
            f"- **Task ID**: `{report.task_id}`",
            f"- **Project**: `{report.project_id}`",
            f"- **Created At**: `{report.created_at}`",
            f"- **Result**: `{report.result}`",
            "",
            "## Goal",
            "",
            report.goal or "Not provided.",
            "",
            "## Context Loaded",
            "",
            self._list(report.context_loaded, "No context recorded."),
            "",
            "## Plan",
            "",
            self._list(report.plan, "No plan recorded."),
            "",
            "## Actions Taken",
            "",
            self._list(report.actions_taken, "No actions recorded."),
            "",
            "## Files Changed",
            "",
            self._list(report.files_changed, "No files changed."),
            "",
            "## Tests Run",
            "",
            self._list(report.tests_run, "Tests were not run."),
            "",
            "## Risks / Unfinished Work",
            "",
            self._list(report.risks, "No known risks recorded."),
            "",
            "## Governance Review",
            "",
            f"- **Governance Result**: `{report.governance_result}`",
            f"- **Protected Files**: {self._inline_list(report.protected_files)}",
            f"- **Required Confirmations**: {self._inline_list(report.required_confirmations)}",
            f"- **Dangerous Actions**: {self._inline_list(report.dangerous_actions)}",
            "",
            "## Decisions to Remember",
            "",
            self._list(report.decisions_to_remember, "No durable decisions recorded."),
            "",
            "## Next Suggested Step",
            "",
            report.next_suggested_step or "No next step recorded.",
            "",
        ])

    @staticmethod
    def _list(items: list[str], empty: str) -> str:
        if not items:
            return empty
        return "\n".join(f"- {item}" for item in items)

    @staticmethod
    def _inline_list(items: list[str]) -> str:
        if not items:
            return "None"
        return ", ".join(f"`{item}`" for item in items)

    @staticmethod
    def _slug(value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-")
        return normalized or "task-report"
