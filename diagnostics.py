"""Diagnostics Everywhere — 结构化诊断事件收集系统。

每个有意义的操作产生 DiagnosticEvent，存储到内存 + JSONL 文件。
支持按类别/状态/时间查询，支持按天自动轮转。
"""

import json
import pathlib
import threading
import time
from contextvars import ContextVar, Token
from dataclasses import dataclass, field, asdict
from typing import Any

from logs import get_logger

logger = get_logger("diagnostics")

_DATA_DIR = pathlib.Path(__file__).parent / "data"
_MAX_MEMORY_EVENTS = 1000
_correlation_id: ContextVar[str] = ContextVar("diagnostic_correlation_id", default="")


def set_correlation_id(value: str) -> Token:
    """Bind a correlation ID to the current async execution context."""
    return _correlation_id.set(value)


def reset_correlation_id(token: Token) -> None:
    """Restore the previous correlation ID for the current context."""
    _correlation_id.reset(token)


def get_correlation_id() -> str:
    return _correlation_id.get()


@dataclass
class DiagnosticEvent:
    """结构化诊断事件 — 系统中每个有意义操作的记录。"""
    timestamp: float
    category: str       # "tool_call" | "plugin_load" | "mcp_request" | "security_check" | "brain_process" | "api_request"
    action: str         # "execute" | "install" | "scan" | "discover" | ...
    status: str         # "success" | "failure" | "blocked" | "timeout" | "skipped"
    duration_ms: float  # 耗时（毫秒）
    input_summary: str  # 输入摘要（≤200字符）
    output_summary: str  # 输出摘要（≤200字符）
    error: str | None = None
    metadata: dict = field(default_factory=dict)
    level: str = "info"  # "debug" | "info" | "warning" | "error"

    def to_dict(self) -> dict:
        return asdict(self)


class DiagnosticCollector:
    """诊断事件收集器 — 单例，全局使用。"""

    def __init__(self):
        self._events: list[DiagnosticEvent] = []
        self._lock = threading.Lock()
        self._current_day: str = ""
        self._file = None

    def record(self, event: DiagnosticEvent) -> None:
        """记录事件到内存 + 持久化到 JSONL 文件。"""
        with self._lock:
            self._events.append(event)
            if len(self._events) > _MAX_MEMORY_EVENTS:
                self._events = self._events[-_MAX_MEMORY_EVENTS:]
        # 异步持久化（非阻塞）
        try:
            self._persist(event)
        except Exception as e:
            logger.debug(f"诊断持久化失败: {e}")

    def _persist(self, event: DiagnosticEvent) -> None:
        """追加写入当天的 JSONL 文件。"""
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        day = time.strftime("%Y-%m-%d", time.localtime(event.timestamp))
        if day != self._current_day:
            if self._file:
                try:
                    self._file.close()
                except Exception:
                    pass
            self._current_day = day
            path = _DATA_DIR / f"diagnostics_{day}.jsonl"
            self._file = open(path, "a", encoding="utf-8")
        if self._file:
            self._file.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
            self._file.flush()

    def query(self, category: str | None = None, status: str | None = None,
              since: float | None = None, limit: int = 50) -> list[dict]:
        """查询诊断事件。"""
        with self._lock:
            results = list(self._events)
        if category:
            results = [e for e in results if e.category == category]
        if status:
            results = [e for e in results if e.status == status]
        if since:
            results = [e for e in results if e.timestamp >= since]
        return [e.to_dict() for e in results[-limit:]]

    def summary(self, since: float | None = None) -> dict[str, Any]:
        """生成诊断摘要（各类别的成功率、平均耗时等）。"""
        with self._lock:
            events = list(self._events)
        if since:
            events = [e for e in events if e.timestamp >= since]

        if not events:
            return {"total": 0, "categories": {}}

        cats: dict[str, dict] = {}
        for e in events:
            c = cats.setdefault(e.category, {"total": 0, "success": 0, "failure": 0, "durations": []})
            c["total"] += 1
            if e.status == "success":
                c["success"] += 1
            elif e.status in ("failure", "timeout", "error"):
                c["failure"] += 1
            c["durations"].append(e.duration_ms)

        result_cats = {}
        for cat, data in cats.items():
            durations = sorted(data["durations"])
            total = data["total"]
            result_cats[cat] = {
                "total": total,
                "success": data["success"],
                "failure": data["failure"],
                "success_rate": round(data["success"] / total, 3) if total else 0,
                "avg_duration_ms": round(sum(durations) / len(durations), 1) if durations else 0,
                "p50_duration_ms": durations[len(durations) // 2] if durations else 0,
                "p95_duration_ms": durations[int(len(durations) * 0.95)] if durations else 0,
            }

        return {"total": len(events), "categories": result_cats}


# 全局单例
_collector: DiagnosticCollector | None = None


def get_collector() -> DiagnosticCollector:
    """获取全局诊断收集器单例。"""
    global _collector
    if _collector is None:
        _collector = DiagnosticCollector()
    return _collector


def record_event(category: str, action: str, status: str, duration_ms: float,
                 input_summary: str = "", output_summary: str = "",
                 error: str | None = None, metadata: dict | None = None,
                 level: str = "info") -> None:
    """便捷函数 — 记录一个诊断事件。"""
    event_metadata = dict(metadata or {})
    correlation_id = get_correlation_id()
    if correlation_id and not event_metadata.get("correlation_id"):
        event_metadata["correlation_id"] = correlation_id
    event = DiagnosticEvent(
        timestamp=time.time(),
        category=category,
        action=action,
        status=status,
        duration_ms=round(duration_ms, 2),
        input_summary=input_summary[:200],
        output_summary=output_summary[:200],
        error=error,
        metadata=event_metadata,
        level=level,
    )
    get_collector().record(event)
