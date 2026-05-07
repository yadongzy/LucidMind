"""Evolution Metrics — 进化效果度量。

量化自进化引擎的实际影响:
- 修复成功率
- 健康分趋势
- 平均修复时间
- 回滚频率
- 最活跃问题类型
- 每周进化频率
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from logs import get_logger

from checkup.evolution_log import EvolutionLog

logger = get_logger("checkup.metrics")


@dataclass
class EvolutionMetricsSummary:
    """进化度量快照。"""
    period_days: int
    total_heals: int
    successful_heals: int
    failed_heals: int
    rollbacks: int
    success_rate: float
    avg_duration_ms: float
    avg_score_delta: float
    files_healed_total: int
    top_triggers: list[tuple[str, int]]
    top_actions: list[tuple[str, int]]
    weekly_frequency: float
    health_trend: list[dict]  # [{date, score}]

    def to_dict(self) -> dict:
        return {
            "period_days": self.period_days,
            "total_heals": self.total_heals,
            "successful_heals": self.successful_heals,
            "failed_heals": self.failed_heals,
            "rollbacks": self.rollbacks,
            "success_rate": self.success_rate,
            "avg_duration_ms": round(self.avg_duration_ms),
            "avg_score_delta": round(self.avg_score_delta, 1),
            "files_healed_total": self.files_healed_total,
            "top_triggers": [{"trigger": t, "count": c} for t, c in self.top_triggers],
            "top_actions": [{"action": a, "count": c} for a, c in self.top_actions],
            "weekly_frequency": round(self.weekly_frequency, 1),
            "health_trend": self.health_trend,
        }


_METRICS_DIR = Path(__file__).parent.parent / "data" / "evolution"
_HEALTH_LOG = _METRICS_DIR / "health_trend.jsonl"


class EvolutionMetrics:
    """进化度量计算器。"""

    def __init__(self):
        self.evo_log = EvolutionLog()
        _METRICS_DIR.mkdir(parents=True, exist_ok=True)

    def record_health_point(self, score: int, trigger: str = ""):
        """记录一个健康分数据点。"""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "score": score,
            "trigger": trigger,
        }
        with open(_HEALTH_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def compute_summary(self, days: int = 30) -> EvolutionMetricsSummary:
        """计算最近 N 天的进化度量。"""
        beads = self.evo_log.get_recent(500)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        # 过滤时间范围
        recent = [b for b in beads if b.get("timestamp", "") >= cutoff]

        total = len(recent)
        success = sum(1 for b in recent if b.get("outcome") == "success")
        failure = sum(1 for b in recent if b.get("outcome") == "failure")
        rollbacks = sum(1 for b in recent if b.get("outcome") == "rollback")

        durations = [b.get("duration_ms", 0) for b in recent if b.get("duration_ms")]
        avg_duration = sum(durations) / len(durations) if durations else 0

        # 计算分数变化
        deltas = []
        for b in recent:
            notes = b.get("notes", "")
            if "→" in notes:
                try:
                    parts = notes.split(":")[-1].strip().split("→")
                    d = int(parts[1].strip()) - int(parts[0].strip())
                    deltas.append(d)
                except (ValueError, IndexError):
                    pass
        avg_delta = sum(deltas) / len(deltas) if deltas else 0

        # 文件计数
        files_total = sum(len(b.get("files_changed", [])) for b in recent)

        # 触发源统计
        triggers = Counter(b.get("trigger", "unknown") for b in recent)
        actions = Counter(b.get("action", "")[:40] for b in recent)

        # 每周频率
        weeks = max(days / 7, 1)
        weekly_freq = total / weeks

        # 健康趋势
        health_trend = self._load_health_trend(days)

        return EvolutionMetricsSummary(
            period_days=days,
            total_heals=total,
            successful_heals=success,
            failed_heals=failure,
            rollbacks=rollbacks,
            success_rate=round(success / total, 2) if total else 0,
            avg_duration_ms=avg_duration,
            avg_score_delta=avg_delta,
            files_healed_total=files_total,
            top_triggers=triggers.most_common(5),
            top_actions=actions.most_common(5),
            weekly_frequency=weekly_freq,
            health_trend=health_trend,
        )

    def get_targets(self) -> dict[str, Any]:
        """返回度量目标及当前达成情况。"""
        summary = self.compute_summary(30)
        return {
            "targets": {
                "success_rate": {"target": 0.70, "current": summary.success_rate, "met": summary.success_rate >= 0.70},
                "weekly_frequency": {"target": 3.0, "current": summary.weekly_frequency, "met": summary.weekly_frequency >= 3.0},
                "avg_fix_time_ms": {"target": 300000, "current": summary.avg_duration_ms, "met": summary.avg_duration_ms <= 300000},
            },
            "summary": summary.to_dict(),
        }

    def _load_health_trend(self, days: int) -> list[dict]:
        """加载健康趋势数据。"""
        if not _HEALTH_LOG.exists():
            return []
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        points = []
        try:
            for line in _HEALTH_LOG.read_text("utf-8").strip().splitlines():
                if not line:
                    continue
                entry = json.loads(line)
                if entry.get("timestamp", "") >= cutoff:
                    points.append({
                        "date": entry["timestamp"][:10],
                        "score": entry["score"],
                    })
        except Exception:
            pass
        return points[-100:]  # max 100 points
