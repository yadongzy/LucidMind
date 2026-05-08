"""Codex CLI runner — 通过 `codex exec` 非交互式执行代码任务。

统一走 `codex exec`（v0.87+ 验证）:
- codex exec [-C <dir>] [-s <sandbox>] [-o <file>] <prompt>

不使用 `codex exec review`：该子命令只能审查 git 变更（--uncommitted/--base/--commit），
不接受 -C/-o，无法审查任意文件，因此 review() 方法也走 _run_exec + 审查 prompt。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from logs import get_logger

logger = get_logger("codex.runner")


def resolve_codex_executable(executable: str = "codex") -> str | None:
    """Resolve the Codex CLI binary across shell and GUI-launched environments."""
    if executable and executable != "codex":
        path = Path(executable).expanduser()
        if path.exists() and os.access(path, os.X_OK):
            return str(path)
        return shutil.which(executable)

    candidates: list[str] = []
    for value in (
        os.getenv("CODEX_BIN"),
        os.getenv("OPENAI_CODEX_BIN"),
        executable,
        "/opt/homebrew/bin/codex",
        "/usr/local/bin/codex",
    ):
        if value and value not in candidates:
            candidates.append(value)

    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.exists() and os.access(path, os.X_OK):
            return str(path)
        resolved = shutil.which(str(path))
        if resolved:
            return resolved
    return None


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
                 timeout_seconds: int = 300, model: str | None = None):
        self.project_root = Path(project_root).resolve()
        self.executable = executable
        self.timeout_seconds = timeout_seconds
        self.model = model  # None = use codex default

    @staticmethod
    def _normalize_output(value: object) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value or ""

    def explain(self, target: str, question: str = "Explain this repository area.") -> CodexCliResult:
        prompt = (
            f"Read and explain the code in '{target}'. "
            f"Question: {question}. "
            f"Do NOT modify any files. Only read and explain."
        )
        return self._run_exec("codex_explain", prompt, sandbox="read-only")

    def review(self, target: str, question: str = "Review this code for risks and correctness.") -> CodexCliResult:
        # 注意: `codex exec review` 子命令只支持 git 变更审查（--uncommitted/--base/--commit），
        # 不接受 -C/-o，且无法审查任意文件。我们改用 `codex exec` + 审查 prompt 实现通用审查。
        prompt = (
            f"Read-only review request for '{target}'. "
            f"Do not modify files. Read the relevant files and "
            f"Report: bugs, logic errors, security risks, performance issues, "
            f"code style problems, maintainability concerns. "
            f"Additional focus: {question}"
        )
        return self._run_exec("codex_review", prompt, sandbox="read-only")

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
        binary = resolve_codex_executable(self.executable)
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
            timeout_result: CodexCliResult | None = None
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
                timeout_result = CodexCliResult(
                    success=False, tool=tool, prompt=prompt,
                    stdout=self._normalize_output(exc.stdout),
                    stderr=self._normalize_output(exc.stderr),
                    error=f"Codex CLI timed out after {self.timeout_seconds}s.",
                    duration_ms=self._duration(start),
                )

            if timeout_result:
                return timeout_result

            # 读取输出文件（codex -o 写入最终消息）
            output_content = ""
            try:
                output_content = Path(output_file).read_text("utf-8").strip()
            except (OSError, UnicodeDecodeError):
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
        finally:
            try:
                Path(output_file).unlink()
            except OSError:
                pass

    @staticmethod
    def _duration(start: float) -> float:
        return round((time.perf_counter() - start) * 1000, 2)
