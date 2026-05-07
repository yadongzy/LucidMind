"""Append-only governance decision log."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class GovernanceDecision:
    task_id: str
    action: str
    approved: bool
    risk_level: str
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GovernanceDecisionLog:
    def __init__(self, root: str | Path, project_id: str = "lucidmind"):
        self.root = Path(root)
        self.project_id = project_id
        self.path = self.root / "data" / "projects" / project_id / "governance_decisions.jsonl"

    def append(self, decision: GovernanceDecision) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(decision.to_dict(), ensure_ascii=False) + "\n")
        return self.path

    def read_all(self) -> list[GovernanceDecision]:
        if not self.path.exists():
            return []
        decisions: list[GovernanceDecision] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            decisions.append(GovernanceDecision(**data))
        return decisions
