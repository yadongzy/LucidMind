"""Persistent storage for project state snapshots."""

from __future__ import annotations

import json
from pathlib import Path

from project_state.schema import ProjectState


class ProjectStateStore:
    def __init__(self, root: str | Path, project_id: str = "lucidmind"):
        self.root = Path(root)
        self.project_id = project_id
        self.path = self.root / "data" / "projects" / project_id / "project_state.json"

    def load(self) -> ProjectState | None:
        if not self.path.exists():
            return None
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return ProjectState.from_dict(data)

    def save(self, state: ProjectState) -> Path:
        previous = self.load()
        if previous:
            if not state.recent_decisions:
                state.recent_decisions = previous.recent_decisions
            if not state.known_risks:
                state.known_risks = previous.known_risks
            if state.last_task_report is None:
                state.last_task_report = previous.last_task_report
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(state.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return self.path
