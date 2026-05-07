"""Markdown task report generator."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


# Confidence markers
CONFIDENCE_CONFIRMED = "🟢 CONFIRMED"   # 命令/文件/测试直接证明
CONFIDENCE_INFERRED = "🟡 INFERRED"     # 根据代码推断
CONFIDENCE_GAP = "🔴 GAP"               # 需要用户确认


@dataclass
class ConfidenceItem:
    """带置信度标注的报告条目。"""
    text: str
    confidence: str = CONFIDENCE_CONFIRMED  # CONFIRMED | INFERRED | GAP

    def render(self) -> str:
        return f"{self.confidence}: {self.text}"


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
    confidence_items: list[ConfidenceItem] = field(default_factory=list)


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
        sections = [
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
            "## Confidence Assessment",
            "",
            self._render_confidence(report),
            "",
            "## Next Suggested Step",
            "",
            report.next_suggested_step or "No next step recorded.",
            "",
        ]
        return "\n".join(sections)

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
    def _render_confidence(report: TaskReport) -> str:
        if not report.confidence_items:
            # Auto-generate from report content
            items = []
            if report.tests_run:
                items.append(f"{CONFIDENCE_CONFIRMED}: 测试已运行 ({len(report.tests_run)} 条)")
            if report.files_changed:
                items.append(f"{CONFIDENCE_CONFIRMED}: 文件已修改 ({len(report.files_changed)} 个)")
            if report.risks:
                items.append(f"{CONFIDENCE_GAP}: 存在遗留风险 ({len(report.risks)} 项)")
            if not report.tests_run and report.actions_taken:
                items.append(f"{CONFIDENCE_INFERRED}: 执行结果基于代码推断（未运行测试）")
            return "\n".join(f"- {i}" for i in items) if items else "无置信度评估。"
        return "\n".join(f"- {item.render()}" for item in report.confidence_items)

    def writeback_to_memory(self, report: TaskReport) -> list[dict]:
        """将报告中的决策和经验转为记忆条目。"""
        memories = []
        # Decisions become facts
        for d in report.decisions_to_remember:
            memories.append({
                "collection": "facts",
                "content": f"[任务 {report.task_id}] {d}",
                "metadata": {
                    "source_type": "task_report",
                    "source_path": str(self.report_path(report)),
                    "confidence": "confirmed",
                    "task_id": report.task_id,
                },
            })
        # Risks become lessons
        for r in report.risks:
            memories.append({
                "collection": "lessons",
                "content": f"[风险] {r} (任务: {report.title})",
                "metadata": {
                    "source_type": "task_report",
                    "source_path": str(self.report_path(report)),
                    "confidence": "inferred",
                    "task_id": report.task_id,
                },
            })
        # Summary as session memory
        summary = (f"任务『{report.title}』已{report.result}。"
                   f"修改{len(report.files_changed)}文件，"
                   f"运行{len(report.tests_run)}测试。"
                   f"下步: {report.next_suggested_step or '未设定'}")
        memories.append({
            "collection": "sessions",
            "content": summary,
            "metadata": {
                "source_type": "task_report",
                "source_path": str(self.report_path(report)),
                "confidence": "confirmed",
                "task_id": report.task_id,
            },
        })
        return memories

    @staticmethod
    def _slug(value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-")
        return normalized or "task-report"
