"""ExecutorPort — 外部执行器抽象接口。

所有执行器（Codex CLI、本地工具、浏览器等）统一通过此接口接入。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutorContext:
    """执行器上下文 — 任务执行所需信息。"""
    project_root: str = ""
    project_id: str = "lucidmind"
    session_id: str = ""
    approved: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutorResult:
    """执行器统一返回结果。"""
    run_id: str
    executor: str                      # 执行器名称
    success: bool
    status: str = "completed"          # running | completed | failed | timeout
    stdout: str = ""
    stderr: str = ""
    files_changed: list[str] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "executor": self.executor,
            "success": self.success,
            "status": self.status,
            "stdout": self.stdout[:2000],
            "stderr": self.stderr[:1000],
            "files_changed": self.files_changed,
            "artifacts": self.artifacts,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


class ExecutorPort(ABC):
    """外部执行器抽象端口。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """执行器名称。"""

    @abstractmethod
    def can_handle(self, task: dict) -> bool:
        """判断本执行器是否能处理该任务。

        Args:
            task: 任务字典，至少包含 content, type 字段。
        """

    @abstractmethod
    async def run(self, task: dict, context: ExecutorContext) -> ExecutorResult:
        """执行任务。

        Args:
            task: 任务字典。
            context: 执行上下文。
        Returns:
            ExecutorResult
        """

    async def status(self, run_id: str) -> str:
        """查询运行状态（默认返回 completed）。"""
        return "completed"

    async def collect_artifacts(self, run_id: str) -> dict[str, Any]:
        """收集执行产物（默认空）。"""
        return {}
