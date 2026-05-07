"""Read-only Codex CLI runner."""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path


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
    def __init__(self, project_root: str | Path, executable: str = "codex", timeout_seconds: int = 60):
        self.project_root = Path(project_root).resolve()
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    def explain(self, target: str, question: str = "Explain this repository area.") -> CodexCliResult:
        prompt = f"Read-only explain request. Target: {target}. Question: {question}. Do not modify files."
        return self._run("codex_explain", prompt)

    def review(self, target: str, question: str = "Review this code for risks and correctness.") -> CodexCliResult:
        prompt = f"Read-only review request. Target: {target}. Question: {question}. Do not modify files."
        return self._run("codex_review", prompt)

    def patch(self, target: str, instruction: str, approved: bool = False) -> CodexCliResult:
        if not approved:
            return CodexCliResult(
                success=False,
                tool="codex_patch",
                prompt=instruction,
                error="codex_patch requires explicit user approval before execution. Set approved=True after confirmation.",
            )
        prompt = f"Patch request. Target: {target}. Instruction: {instruction}. Apply minimal changes."
        return self._run("codex_patch", prompt, write=True)

    def fix_tests(self, test_command: str, approved: bool = False) -> CodexCliResult:
        if not approved:
            return CodexCliResult(
                success=False,
                tool="codex_fix_tests",
                prompt=test_command,
                error="codex_fix_tests requires explicit user approval before execution. Set approved=True after confirmation.",
            )
        prompt = f"Fix failing tests. Command: {test_command}. Apply minimal fixes only."
        return self._run("codex_fix_tests", prompt, write=True)

    def _run(self, tool: str, prompt: str, write: bool = False) -> CodexCliResult:
        start = time.perf_counter()
        binary = shutil.which(self.executable)
        if not binary:
            return CodexCliResult(
                success=False,
                tool=tool,
                prompt=prompt,
                error="Codex CLI not found. Install Codex CLI or configure the executable path before using this skill.",
                duration_ms=self._duration(start),
            )
        try:
            result = subprocess.run(
                [binary, prompt],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return CodexCliResult(
                success=False,
                tool=tool,
                prompt=prompt,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                error="Codex CLI timed out.",
                duration_ms=self._duration(start),
            )
        return CodexCliResult(
            success=result.returncode == 0,
            tool=tool,
            prompt=prompt,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.returncode,
            duration_ms=self._duration(start),
            error="" if result.returncode == 0 else "Codex CLI returned non-zero exit code.",
        )

    @staticmethod
    def _duration(start: float) -> float:
        return round((time.perf_counter() - start) * 1000, 2)
