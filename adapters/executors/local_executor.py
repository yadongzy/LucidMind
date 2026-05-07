"""LocalToolExecutor — 本地 Python 工具 / MCP 执行器。

处理本地自动化任务：脚本执行、文件操作、MCP 工具调用等。
"""

from __future__ import annotations

import asyncio
import subprocess
import time
import uuid
from pathlib import Path

from ports.executor_port import ExecutorPort, ExecutorContext, ExecutorResult
from logs import get_logger

logger = get_logger("executor.local")

_LOCAL_KEYWORDS = [
    "run", "script", "shell", "命令", "脚本", "执行",
    "file", "文件", "目录", "list", "search", "搜索",
    "monitor", "监控", "reminder", "提醒",
    "mcp", "tool", "工具",
]


class LocalToolExecutor(ExecutorPort):
    """本地工具执行器 — 处理本地自动化和 MCP 任务。"""

    @property
    def name(self) -> str:
        return "local"

    def can_handle(self, task: dict) -> bool:
        content = task.get("content", "").lower()
        task_type = task.get("type", "")
        if task_type in ("local", "script", "automation", "mcp"):
            return True
        return any(kw in content for kw in _LOCAL_KEYWORDS)

    async def run(self, task: dict, context: ExecutorContext) -> ExecutorResult:
        run_id = f"local-{uuid.uuid4().hex[:8]}"
        content = task.get("content", "")
        root = Path(context.project_root) if context.project_root else Path.cwd()

        # Extract command from task content if it looks like a shell command
        command = context.extra.get("command", "")
        if not command:
            # Fallback: if content looks like a command, run it
            if content.startswith("!") or content.startswith("$"):
                command = content.lstrip("!$").strip()

        if not command:
            return ExecutorResult(
                run_id=run_id,
                executor=self.name,
                success=False,
                status="failed",
                error="No executable command found in task. Use context.extra['command'] to specify.",
            )

        if not context.approved:
            return ExecutorResult(
                run_id=run_id,
                executor=self.name,
                success=False,
                status="failed",
                error="Local execution requires user approval. Set context.approved=True.",
            )

        start = time.perf_counter()
        try:
            proc = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    command, shell=True, cwd=root,
                    capture_output=True, text=True, timeout=120,
                ),
            )
            duration = round((time.perf_counter() - start) * 1000, 2)
            return ExecutorResult(
                run_id=run_id,
                executor=self.name,
                success=proc.returncode == 0,
                status="completed" if proc.returncode == 0 else "failed",
                stdout=proc.stdout[:5000],
                stderr=proc.stderr[:2000],
                duration_ms=duration,
                error="" if proc.returncode == 0 else f"Exit code: {proc.returncode}",
            )
        except subprocess.TimeoutExpired:
            return ExecutorResult(
                run_id=run_id, executor=self.name,
                success=False, status="timeout",
                error="Command timed out (120s)",
                duration_ms=round((time.perf_counter() - start) * 1000, 2),
            )
        except Exception as e:
            return ExecutorResult(
                run_id=run_id, executor=self.name,
                success=False, status="failed",
                error=str(e)[:500],
            )
