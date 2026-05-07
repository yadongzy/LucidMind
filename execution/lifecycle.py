"""Task lifecycle support with state machine.

State machine:
  draft → planned → approved → running → verifying → done
                                  ↓          ↓
                               blocked     failed
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from execution.evidence import LifecycleEvidence
from governance.policy import GovernanceReview
from project_state.indexer import ProjectStateIndexer
from project_state.store import ProjectStateStore
from reports.task_reporter import TaskReport, TaskReportGenerator
from logs import get_logger

logger = get_logger("execution.lifecycle")

# Valid state transitions
_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"planned", "failed"},
    "planned": {"approved", "failed"},
    "approved": {"running", "failed"},
    "running": {"verifying", "blocked", "failed"},
    "blocked": {"running", "failed"},
    "verifying": {"done", "failed", "running"},
    "done": set(),
    "failed": {"draft"},  # allow retry from failed
}


@dataclass
class ManagedTask:
    """带状态机的任务。"""
    id: str
    title: str
    goal: str
    status: str = "draft"          # draft|planned|approved|running|blocked|verifying|done|failed
    project_id: str = "lucidmind"
    plan: list[str] = field(default_factory=list)
    scope: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    verification_cmd: str = ""
    rollback_strategy: str = ""
    files_changed: list[str] = field(default_factory=list)
    result: str = ""
    error: str = ""
    created_at: str = ""
    updated_at: str = ""
    history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def transition(self, new_status: str, reason: str = "") -> bool:
        """Attempt state transition. Returns True if valid."""
        allowed = _TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            logger.warning(f"Task {self.id}: invalid transition {self.status} → {new_status}")
            return False
        old = self.status
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc).isoformat()
        self.history.append({
            "from": old, "to": new_status,
            "reason": reason, "at": self.updated_at,
        })
        logger.info(f"Task {self.id}: {old} → {new_status} ({reason})")
        return True


class TaskStateStore:
    """Persists managed tasks to data/tasks/."""

    def __init__(self, root: Path):
        self._dir = root / "data" / "tasks"
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, task: ManagedTask) -> Path:
        path = self._dir / f"{task.id}.json"
        path.write_text(json.dumps(task.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load(self, task_id: str) -> ManagedTask | None:
        path = self._dir / f"{task_id}.json"
        if not path.exists():
            return None
        try:
            d = json.loads(path.read_text("utf-8"))
            return ManagedTask(**{k: v for k, v in d.items() if k in ManagedTask.__dataclass_fields__})
        except Exception as e:
            logger.warning(f"Failed to load task {task_id}: {e}")
            return None

    def list_tasks(self, status: str | None = None, limit: int = 20) -> list[ManagedTask]:
        tasks = []
        for f in sorted(self._dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            t = self.load(f.stem)
            if t and (status is None or t.status == status):
                tasks.append(t)
            if len(tasks) >= limit:
                break
        return tasks

    def create(self, title: str, goal: str, project_id: str = "lucidmind") -> ManagedTask:
        now = datetime.now(timezone.utc).isoformat()
        task = ManagedTask(
            id=f"TASK-{uuid.uuid4().hex[:8]}",
            title=title,
            goal=goal,
            project_id=project_id,
            created_at=now,
            updated_at=now,
        )
        self.save(task)
        logger.info(f"Created task {task.id}: {title}")
        return task


class TaskLifecycle:
    def __init__(self, root: str | Path, project_id: str = "lucidmind"):
        self.root = Path(root)
        self.project_id = project_id
        self.state_store = ProjectStateStore(self.root, project_id=project_id)
        self.reporter = TaskReportGenerator(self.root)

    def load_project_state(self):
        state = ProjectStateIndexer(self.root, project_id=self.project_id).build()
        self.state_store.save(state)
        return state

    def create_evidence(self, task_id: str, goal: str) -> LifecycleEvidence:
        state = self.load_project_state()
        return LifecycleEvidence(
            task_id=task_id,
            goal=goal,
            project_id=self.project_id,
            context_loaded=[
                f"project_state:{state.project_name}",
                f"frameworks:{','.join(state.frameworks) or 'unknown'}",
            ],
            plan=[
                "Load project state and rules.",
                "Execute bounded task through approved tools.",
                "Verify with tests or record why tests were not run.",
                "Generate task report and memory candidates.",
            ],
        )

    def write_report(
        self,
        evidence: LifecycleEvidence,
        title: str,
        next_step: str = "",
        governance_review: GovernanceReview | None = None,
    ) -> Path:
        governance_result = "not-reviewed"
        protected_files: list[str] = []
        required_confirmations: list[str] = []
        dangerous_actions: list[str] = []
        if governance_review:
            governance_result = "approved" if governance_review.approved else "requires-confirmation"
            protected_files = governance_review.protected_files
            required_confirmations = governance_review.reasons
            dangerous_actions = governance_review.dangerous_actions
        report = TaskReport(
            task_id=evidence.task_id,
            title=title,
            goal=evidence.goal,
            project_id=evidence.project_id,
            context_loaded=evidence.context_loaded,
            plan=evidence.plan,
            actions_taken=evidence.actions_taken,
            files_changed=evidence.files_changed,
            tests_run=evidence.tests_as_lines(),
            result=evidence.result,
            risks=evidence.risks,
            decisions_to_remember=evidence.decisions,
            governance_result=governance_result,
            protected_files=protected_files,
            required_confirmations=required_confirmations,
            dangerous_actions=dangerous_actions,
            next_suggested_step=next_step,
        )
        path = self.reporter.save(report)
        state = self.state_store.load()
        if state:
            state.last_task_report = str(path.relative_to(self.root))
            self.state_store.save(state)
        # Writeback to memory
        self._writeback_report(report)
        return path

    def _writeback_report(self, report: TaskReport) -> None:
        """将报告关键信息写回记忆系统。"""
        try:
            from memory.store import MemoryStore
            store = MemoryStore()
            entries = self.reporter.writeback_to_memory(report)
            for entry in entries:
                store.add(
                    content=entry["content"],
                    collection=entry["collection"],
                    metadata=entry["metadata"],
                )
            logger.info(f"Report writeback: {len(entries)} memories for task {report.task_id}")
        except Exception as e:
            logger.debug(f"Report writeback failed: {e}")

    def generate_plan(self, task: ManagedTask) -> ManagedTask:
        """为任务生成执行计划（基于项目状态）。"""
        state = self.load_project_state()
        task.plan = [
            f"目标: {task.goal}",
            f"项目: {state.project_name} ({', '.join(state.frameworks)})",
            "加载项目状态和规则",
            "通过已审批工具执行任务",
            f"验证: {state.test_commands[0] if state.test_commands else '手动验证'}",
            "生成任务报告并写入记忆",
        ]
        task.scope = [f for f in state.core_files[:5]]
        task.risks = ["修改可能影响现有测试", "需确认不涉及冻结文件"]
        task.verification_cmd = state.test_commands[0] if state.test_commands else ""
        task.rollback_strategy = "git stash / git checkout -- <files>"
        task.transition("planned", "plan generated from project state")
        return task
