"""任务生命周期领域模型。

该模块只定义稳定的数据与状态转换规则，不执行 I/O。旧调度器可逐步接入，
同时继续使用现有持久化字符串，确保迁移期间可回滚、可兼容。
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Optional


class TaskStatus(str, Enum):
    """持久化任务状态。枚举值保持与现有 JSON 格式兼容。"""

    READY = "ready"
    RUNNING = "running"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    ESCALATED = "escalated"
    MEMO = "memo"
    CANCELLED = "cancelled"


class FailureReason(str, Enum):
    """可机器判定的失败分类。"""

    UNKNOWN = "unknown"
    TIMEOUT = "timeout"
    TRANSIENT = "transient"
    VALIDATION = "validation"
    PERMISSION = "permission"
    DEPENDENCY = "dependency"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = frozenset(
    {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.ESCALATED,
        TaskStatus.CANCELLED,
    }
)


_TRANSITIONS = {
    TaskStatus.READY: frozenset(
        {TaskStatus.RUNNING, TaskStatus.BLOCKED, TaskStatus.COMPLETED, TaskStatus.FAILED,
         TaskStatus.ESCALATED, TaskStatus.MEMO, TaskStatus.CANCELLED}
    ),
    TaskStatus.RUNNING: frozenset(
        {TaskStatus.READY, TaskStatus.BLOCKED, TaskStatus.COMPLETED,
         TaskStatus.FAILED, TaskStatus.ESCALATED, TaskStatus.CANCELLED}
    ),
    TaskStatus.BLOCKED: frozenset(
        {TaskStatus.READY, TaskStatus.COMPLETED, TaskStatus.FAILED,
         TaskStatus.ESCALATED, TaskStatus.MEMO, TaskStatus.CANCELLED}
    ),
    TaskStatus.MEMO: frozenset({TaskStatus.READY, TaskStatus.CANCELLED}),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.ESCALATED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


_STATUS_ALIASES = {
    "pending": TaskStatus.READY,
    "done": TaskStatus.COMPLETED,
    "canceled": TaskStatus.CANCELLED,
}


def parse_status(value: TaskStatus | str) -> TaskStatus:
    """解析规范状态或迁移期别名。未知状态会明确失败。"""

    if isinstance(value, TaskStatus):
        return value
    normalized = str(value).strip().lower()
    if normalized in _STATUS_ALIASES:
        return _STATUS_ALIASES[normalized]
    try:
        return TaskStatus(normalized)
    except ValueError as exc:
        raise ValueError(f"未知任务状态: {value!r}") from exc


def can_transition(current: TaskStatus | str, target: TaskStatus | str) -> bool:
    """返回状态转换是否合法。相同状态视为幂等操作。"""

    source = parse_status(current)
    destination = parse_status(target)
    return source == destination or destination in _TRANSITIONS[source]


def transition(task: dict[str, Any], target: TaskStatus | str) -> dict[str, Any]:
    """原地执行已校验的状态转换，并递增乐观版本号。"""

    source = parse_status(task.get("status", TaskStatus.READY.value))
    destination = parse_status(target)
    if not can_transition(source, destination):
        raise ValueError(f"非法任务状态转换: {source.value} -> {destination.value}")
    if source != destination:
        task["status"] = destination.value
        task["version"] = int(task.get("version", 0)) + 1
        task["updated_at"] = datetime.now().isoformat()
    return task


@dataclass(frozen=True)
class TaskAttempt:
    """一次执行尝试的持久化记录。"""

    number: int
    started_at: str
    finished_at: Optional[str] = None
    failure_reason: Optional[FailureReason] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.failure_reason is not None:
            data["failure_reason"] = self.failure_reason.value
        return data


@dataclass(frozen=True)
class Checkpoint:
    """可恢复执行点；payload 只保存可序列化的最小恢复状态。"""

    name: str
    created_at: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "created_at": self.created_at,
            "payload": dict(self.payload),
            "version": self.version,
        }
