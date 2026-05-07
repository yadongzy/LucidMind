"""Codex CLI runner — 通过 `codex exec` 非交互式执行代码任务。

正确使用 OpenAI Codex CLI:
- codex exec <prompt>                    → 非交互式执行
- codex exec review <prompt>             → 代码审查
- codex exec --full-auto <prompt>        → 全自动执行（带沙箱）
- -C <dir>                               → 指定工作目录
- --json                                 → JSONL 输出
- -o <file>                              → 输出最后消息到文件
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from logs import get_logger

logger = get_logger("codex.runner")


@dataclass
class CodexCliResult:
    success: bool
    tool: str
    prompt: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    duration_ms: float = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class CodexCliRunner:
    def __init__(self, project_root: str | Path, executable: str = "codex",
                 timeout_seconds: int = 120, model: str | None = None):
        self.project_root = Path(project_root).resolve()
        self.executable = executable
        self.timeout_seconds = timeout_seconds
        self.model = model  # None = use codex default

    def explain(self, target: str, question: str = "Explain this repository area.") -> CodexCliResult:
        prompt = (
            f"Read and explain the code in '{target}'. "
            f"Question: {question}. "
            f"Do NOT modify any files. Only read and explain."
        )
        return self._run_exec("codex_explain", prompt, sandbox="read-only")

    def review(self, target: str, question: str = "Review this code for risks and correctness.") -> CodexCliResult:
        prompt = (
            f"Review the code in '{target}'. "
            f"Check for: bugs, logic errors, security risks, code style, maintainability. "
            f"{question}"
        )
        return self._run_review("codex_review", prompt)

    def patch(self, target: str, instruction: str, approved: bool = False) -> CodexCliResult:
        if not approved:
            return CodexCliResult(
                success=False,
                tool="codex_patch",
                prompt=instruction,
                error="codex_patch requires explicit user approval before execution. Set approved=True after confirmation.",
            )
        prompt = (
            f"Fix the following issue. Target file/area: {target}. "
            f"Instruction: {instruction}. "
            f"Apply minimal, focused changes only."
        )
        return self._run_exec("codex_patch", prompt, sandbox="workspace-write")

    def fix_tests(self, test_command: str, approved: bool = False) -> CodexCliResult:
        if not approved:
            return CodexCliResult(
                success=False,
                tool="codex_fix_tests",
                prompt=test_command,
                error="codex_fix_tests requires explicit user approval before execution. Set approved=True after confirmation.",
            )
        prompt = (
            f"Run '{test_command}' and fix any failing tests. "
            f"Apply minimal fixes only. Do not delete tests."
        )
        return self._run_exec("codex_fix_tests", prompt, sandbox="workspace-write")

    def _run_exec(self, tool: str, prompt: str, sandbox: str = "read-only") -> CodexCliResult:
        """使用 `codex exec` 非交互式执行。"""
        start = time.perf_counter()
        binary = shutil.which(self.executable)
        if not binary:
            return CodexCliResult(
                success=False, tool=tool, prompt=prompt,
                error="Codex CLI not found. Install: npm install -g @openai/codex",
                duration_ms=self._duration(start),
            )

        # 使用临时文件捕获输出
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
            output_file = tmp.name

        cmd = [
            binary, "exec",
            "-C", str(self.project_root),
            "-s", sandbox,
            "-o", output_file,
            prompt,
        ]
        if self.model:
            cmd.insert(2, "-m")
            cmd.insert(3, self.model)

        logger.info(f"Codex exec [{tool}] sandbox={sandbox}: {prompt[:80]}...")

        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            logger.warning(f"Codex timed out after {self.timeout_seconds}s")
            return CodexCliResult(
                success=False, tool=tool, prompt=prompt,
                stdout=exc.stdout or "", stderr=exc.stderr or "",
                error=f"Codex CLI timed out after {self.timeout_seconds}s.",
                duration_ms=self._duration(start),
            )

        # 读取输出文件（codex -o 写入最终消息）
        output_content = ""
        try:
            output_content = Path(output_file).read_text("utf-8").strip()
        except (OSError, UnicodeDecodeError):
            pass
        finally:
            try:
                Path(output_file).unlink()
            except OSError:
                pass

        # 合并 stdout + output file
        full_output = result.stdout
        if output_content:
            full_output = output_content if not full_output else f"{full_output}\n\n{output_content}"

        duration = self._duration(start)
        success = result.returncode == 0

        if success:
            logger.info(f"Codex [{tool}] 成功 ({duration:.0f}ms)")
        else:
            logger.warning(f"Codex [{tool}] 失败 (exit={result.returncode}): {result.stderr[:200]}")

        return CodexCliResult(
            success=success,
            tool=tool,
            prompt=prompt,
            stdout=full_output,
            stderr=result.stderr,
            exit_code=result.returncode,
            duration_ms=duration,
            error="" if success else (result.stderr[:300] or "Codex CLI returned non-zero exit code."),
        )

    def _run_review(self, tool: str, prompt: str) -> CodexCliResult:
        """使用 `codex exec review` 执行代码审查。"""
        start = time.perf_counter()
        binary = shutil.which(self.executable)
        if not binary:
            return CodexCliResult(
                success=False, tool=tool, prompt=prompt,
                error="Codex CLI not found.",
                duration_ms=self._duration(start),
            )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
            output_file = tmp.name

        cmd = [
            binary, "exec", "review",
            "-C", str(self.project_root),
            "-o", output_file,
            prompt,
        ]

        logger.info(f"Codex review: {prompt[:80]}...")

        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return CodexCliResult(
                success=False, tool=tool, prompt=prompt,
                error=f"Codex review timed out after {self.timeout_seconds}s.",
                duration_ms=self._duration(start),
            )

        output_content = ""
        try:
            output_content = Path(output_file).read_text("utf-8").strip()
        except (OSError, UnicodeDecodeError):
            pass
        finally:
            try:
                Path(output_file).unlink()
            except OSError:
                pass

        full_output = output_content or result.stdout
        return CodexCliResult(
            success=result.returncode == 0,
            tool=tool,
            prompt=prompt,
            stdout=full_output,
            stderr=result.stderr,
            exit_code=result.returncode,
            duration_ms=self._duration(start),
            error="" if result.returncode == 0 else (result.stderr[:300] or "Review failed."),
        )

    @staticmethod
    def _duration(start: float) -> float:
        return round((time.perf_counter() - start) * 1000, 2)
