"""Governance policy configuration loader."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GovernanceConfig:
    protected_patterns: tuple[str, ...] = field(default_factory=tuple)
    dangerous_actions: tuple[str, ...] = field(default_factory=tuple)


class GovernanceConfigLoader:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.path = self.root / "data" / "governance" / "policies.json"

    def load(self) -> GovernanceConfig:
        if not self.path.exists():
            return GovernanceConfig()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        protected = self._string_tuple(data.get("additional_protected_patterns", []))
        dangerous = self._string_tuple(data.get("additional_dangerous_actions", []))
        return GovernanceConfig(protected_patterns=protected, dangerous_actions=dangerous)

    @staticmethod
    def _string_tuple(value: object) -> tuple[str, ...]:
        if not isinstance(value, list):
            return tuple()
        return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
