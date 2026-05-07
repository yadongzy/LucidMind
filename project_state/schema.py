"""Structured project state models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ProjectState:
    project_id: str
    project_name: str
    root: str
    updated_at: str
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    entrypoints: list[str] = field(default_factory=list)
    test_commands: list[str] = field(default_factory=list)
    run_commands: list[str] = field(default_factory=list)
    core_files: list[str] = field(default_factory=list)
    protected_rules: list[str] = field(default_factory=list)
    recent_decisions: list[str] = field(default_factory=list)
    known_risks: list[str] = field(default_factory=list)
    last_task_report: str | None = None
    git_branch: str | None = None
    git_commit: str | None = None
    capability_status: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectState":
        fields = cls.__dataclass_fields__.keys()
        return cls(**{key: data.get(key) for key in fields if key in data})
