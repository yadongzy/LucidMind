"""CodexExecutor — Codex CLI adapter implementing ExecutorPort.

Routes coding tasks (fix, patch, review, explain) to Codex CLI.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from ports.executor_port import ExecutorPort, ExecutorContext, ExecutorResult
from skills.codex_cli.runner import CodexCliRunner
from logs import get_logger

logger = get_logger("executor.codex")

# Keywords that indicate a coding task suitable for Codex
_CODING_KEYWORDS = [
    "fix", "patch", "refactor", "修复", "补丁", "重构",
    "test", "测试", "review", "审查", "explain", "解释",
    "implement", "实现", "bug", "error", "错误",
]


class CodexExecutor(ExecutorPort):
    """Codex CLI executor — delegates coding tasks to Codex."""

    @property
    def name(self) -> str:
        return "codex"

    def can_handle(self, task: dict) -> bool:
        content = task.get("content", "").lower()
        task_type = task.get("type", "")
        if task_type in ("code", "fix", "patch", "review"):
            return True
        return any(kw in content for kw in _CODING_KEYWORDS)

    async def run(self, task: dict, context: ExecutorContext) -> ExecutorResult:
        run_id = f"codex-{uuid.uuid4().hex[:8]}"
        root = Path(context.project_root) if context.project_root else Path.cwd()
        runner = CodexCliRunner(root)

        content = task.get("content", "")
        task_type = task.get("type", "task")

        try:
            # Route to appropriate Codex command
            if task_type == "review" or "review" in content.lower():
                cli_result = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: runner.review(str(root), content))
            elif task_type == "explain" or "explain" in content.lower():
                cli_result = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: runner.explain(str(root), content))
            elif task_type == "fix" or "fix_test" in content.lower():
                cli_result = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: runner.fix_tests(content, approved=context.approved))
            else:
                # Default: patch
                cli_result = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: runner.patch(str(root), content, approved=context.approved))

            return ExecutorResult(
                run_id=run_id,
                executor=self.name,
                success=cli_result.success,
                status="completed" if cli_result.success else "failed",
                stdout=cli_result.stdout,
                stderr=cli_result.stderr,
                duration_ms=cli_result.duration_ms,
                error=cli_result.error,
                artifacts={"tool": cli_result.tool, "prompt": cli_result.prompt},
            )
        except Exception as e:
            logger.warning(f"Codex execution failed: {e}")
            return ExecutorResult(
                run_id=run_id,
                executor=self.name,
                success=False,
                status="failed",
                error=str(e)[:500],
            )
