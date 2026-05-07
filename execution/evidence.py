"""Evidence objects for project task lifecycle reports."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ToolCallEvidence:
    tool_name: str
    status: str
    duration_ms: float | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TestEvidence:
    __test__ = False

    command: str
    status: str
    output_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LifecycleEvidence:
    task_id: str
    goal: str
    project_id: str = "lucidmind"
    context_loaded: list[str] = field(default_factory=list)
    plan: list[str] = field(default_factory=list)
    actions_taken: list[str] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    tests: list[TestEvidence] = field(default_factory=list)
    tool_calls: list[ToolCallEvidence] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    result: str = "partial"

    def tests_as_lines(self) -> list[str]:
        return [f"`{item.command}` — {item.status}: {item.output_summary}" for item in self.tests]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["tests"] = [item.to_dict() for item in self.tests]
        data["tool_calls"] = [item.to_dict() for item in self.tool_calls]
        return data
