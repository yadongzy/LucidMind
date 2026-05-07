"""Evolution Log — 进化日志（Bead 模式）。

每次体检→诊断→修复形成一个 "Bead"（珠子），串成进化链。
完整审计：所有决策可追溯、可回滚。

Bead 格式:
{
    "id": "EVOL-001",
    "timestamp": "...",
    "trigger": "checkup | user_request | scheduled",
    "diagnosis_id": "DIAG-003",
    "severity": "L1",
    "action": "ruff --fix F401",
    "executor": "local_cli | codex_patch",
    "outcome": "success | failure | rollback",
    "files_changed": ["path/to/file.py"],
    "test_result": "33/33 pass",
    "approved_by": "auto | user",
    "rollback_commit": "abc123",
}
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from logs import get_logger

logger = get_logger("checkup.evolution_log")

_LOG_DIR = Path(__file__).parent.parent / "data" / "evolution"


@dataclass
class EvolutionBead:
    """一次进化操作的完整记录。"""
    id: str
    timestamp: str
    trigger: str                    # checkup | user_request | scheduled
    diagnosis_id: str = ""
    severity: str = ""              # L0 | L1 | L2 | L3 | L4
    action: str = ""
    executor: str = ""              # local_cli | codex_patch | manual
    outcome: str = "pending"        # pending | success | failure | rollback
    files_changed: list[str] = field(default_factory=list)
    test_result: str = ""
    approved_by: str = "auto"       # auto | user
    rollback_commit: str = ""
    duration_ms: float = 0.0
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class EvolutionLog:
    """进化日志管理器。"""

    def __init__(self, log_dir: Path | None = None):
        self._dir = log_dir or _LOG_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._counter = self._load_counter()

    def record(self, bead: EvolutionBead) -> str:
        """记录一个 Bead 到日志。返回 bead ID。"""
        # 追加到当天文件
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = self._dir / f"evolution_{day}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(bead.to_dict(), ensure_ascii=False) + "\n")
        logger.info(f"进化记录: {bead.id} [{bead.outcome}] {bead.action[:60]}")
        return bead.id

    def create_bead(self, trigger: str, diagnosis_id: str = "",
                    severity: str = "", action: str = "",
                    executor: str = "local_cli") -> EvolutionBead:
        """创建一个新 Bead（预分配 ID）。"""
        self._counter += 1
        self._save_counter()
        bead = EvolutionBead(
            id=f"EVOL-{self._counter:04d}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            trigger=trigger,
            diagnosis_id=diagnosis_id,
            severity=severity,
            action=action,
            executor=executor,
        )
        return bead

    def get_recent(self, limit: int = 20) -> list[dict]:
        """获取最近的进化记录。"""
        all_beads = []
        files = sorted(self._dir.glob("evolution_*.jsonl"), reverse=True)
        for f in files[:7]:  # 最多看 7 天
            try:
                for line in f.read_text("utf-8").strip().splitlines():
                    if line:
                        all_beads.append(json.loads(line))
            except Exception:
                continue
            if len(all_beads) >= limit:
                break
        return all_beads[:limit]

    def get_stats(self) -> dict[str, Any]:
        """进化统计。"""
        recent = self.get_recent(100)
        if not recent:
            return {"total": 0, "success": 0, "failure": 0, "success_rate": 0}
        success = sum(1 for b in recent if b.get("outcome") == "success")
        failure = sum(1 for b in recent if b.get("outcome") == "failure")
        return {
            "total": len(recent),
            "success": success,
            "failure": failure,
            "success_rate": round(success / len(recent), 2) if recent else 0,
        }

    def _load_counter(self) -> int:
        counter_file = self._dir / ".counter"
        if counter_file.exists():
            try:
                return int(counter_file.read_text().strip())
            except (ValueError, OSError):
                pass
        return 0

    def _save_counter(self) -> None:
        counter_file = self._dir / ".counter"
        try:
            counter_file.write_text(str(self._counter))
        except OSError:
            pass
