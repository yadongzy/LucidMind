"""Governance policy checks for Project Brain tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from governance.config import GovernanceConfigLoader


PROTECTED_PATTERNS = (
    "brain.py",
    "brain_daemon.py",
    "brain_meta.py",
    "task_dispatcher.py",
    "api/main.py",
    "ports/",
    "frontend/",
    "frontend-v2/",
    ".rules/",
)

DANGEROUS_ACTIONS = (
    "delete",
    "remove",
    "rm -rf",
    "git push",
    "git commit",
    "chmod -R",
)


@dataclass
class GovernanceReview:
    approved: bool
    risk_level: str
    requires_confirmation: bool
    reasons: list[str] = field(default_factory=list)
    protected_files: list[str] = field(default_factory=list)
    dangerous_actions: list[str] = field(default_factory=list)


class GovernancePolicy:
    def __init__(
        self,
        protected_patterns: tuple[str, ...] = PROTECTED_PATTERNS,
        dangerous_actions: tuple[str, ...] = DANGEROUS_ACTIONS,
    ):
        self.protected_patterns = self._dedupe((*PROTECTED_PATTERNS, *protected_patterns))
        self.dangerous_actions = self._dedupe((*DANGEROUS_ACTIONS, *dangerous_actions))

    @classmethod
    def from_project_root(cls, root: str | Path) -> "GovernancePolicy":
        config = GovernanceConfigLoader(root).load()
        return cls(
            protected_patterns=config.protected_patterns,
            dangerous_actions=config.dangerous_actions,
        )

    def review(self, changed_files: list[str], actions: list[str] | None = None) -> GovernanceReview:
        actions = actions or []
        protected = [path for path in changed_files if self.is_protected(path)]
        dangerous = [action for action in actions if self.is_dangerous_action(action)]
        reasons: list[str] = []
        if protected:
            reasons.append("Protected files require explicit confirmation.")
        if dangerous:
            reasons.append("Dangerous actions require explicit confirmation.")
        requires_confirmation = bool(protected or dangerous)
        risk_level = "high" if protected or dangerous else "low"
        return GovernanceReview(
            approved=not requires_confirmation,
            risk_level=risk_level,
            requires_confirmation=requires_confirmation,
            reasons=reasons,
            protected_files=protected,
            dangerous_actions=dangerous,
        )

    def is_protected(self, path: str) -> bool:
        normalized = self._normalize(path)
        for pattern in self.protected_patterns:
            if pattern.endswith("/") and normalized.startswith(pattern):
                return True
            if normalized == pattern:
                return True
        return False

    def is_dangerous_action(self, action: str) -> bool:
        lowered = action.lower()
        return any(token.lower() in lowered for token in self.dangerous_actions)

    @staticmethod
    def _normalize(path: str) -> str:
        return Path(path).as_posix().lstrip("./")

    @staticmethod
    def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value not in seen:
                seen.add(value)
                result.append(value)
        return tuple(result)
