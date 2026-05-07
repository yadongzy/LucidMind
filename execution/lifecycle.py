"""Minimal sequential task lifecycle support."""

from __future__ import annotations

from pathlib import Path

from execution.evidence import LifecycleEvidence
from governance.policy import GovernanceReview
from project_state.indexer import ProjectStateIndexer
from project_state.store import ProjectStateStore
from reports.task_reporter import TaskReport, TaskReportGenerator


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
        return path
