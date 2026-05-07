"""Project state indexer for the Project Brain loop."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from project_state.schema import ProjectState


class ProjectStateIndexer:
    def __init__(self, root: str | Path, project_id: str = "lucidmind"):
        self.root = Path(root).resolve()
        self.project_id = project_id

    def build(self) -> ProjectState:
        return ProjectState(
            project_id=self.project_id,
            project_name=self._project_name(),
            root=str(self.root),
            updated_at=datetime.now(timezone.utc).isoformat(),
            languages=self._detect_languages(),
            frameworks=self._detect_frameworks(),
            entrypoints=self._detect_entrypoints(),
            test_commands=self._detect_test_commands(),
            run_commands=self._detect_run_commands(),
            core_files=self._detect_core_files(),
            protected_rules=self._detect_protected_rules(),
            git_branch=self._git(["rev-parse", "--abbrev-ref", "HEAD"]),
            git_commit=self._git(["rev-parse", "--short", "HEAD"]),
            capability_status={
                "project_state": "stable",
                "task_reports": "beta",
                "codex_cli": "experimental",
                "web_cockpit": "planned",
            },
        )

    def _project_name(self) -> str:
        pyproject = self.root / "pyproject.toml"
        if pyproject.exists():
            for line in pyproject.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("name") and "=" in line:
                    return line.split("=", 1)[1].strip().strip('"')
        return self.root.name

    def _detect_languages(self) -> list[str]:
        languages = []
        if any(self.root.glob("**/*.py")):
            languages.append("python")
        if any(self.root.glob("**/*.js")) or any(self.root.glob("**/*.ts")):
            languages.append("javascript")
        if any(self.root.glob("**/*.md")):
            languages.append("markdown")
        return languages

    def _detect_frameworks(self) -> list[str]:
        frameworks = []
        pyproject = self._read_optional("pyproject.toml")
        requirements = self._read_optional("requirements.txt")
        package_json = self._read_optional("frontend-v2/package.json") + self._read_optional("frontend/package.json")
        combined = "\n".join([pyproject, requirements, package_json]).lower()
        for name in ("fastapi", "uvicorn", "pytest", "vite", "lit", "react"):
            if name in combined:
                frameworks.append(name)
        return frameworks

    def _detect_entrypoints(self) -> list[str]:
        candidates = ["api/main.py", "cli.py", "start.sh", "frontend-v2/package.json"]
        return [path for path in candidates if (self.root / path).exists()]

    def _detect_test_commands(self) -> list[str]:
        commands = ["python -m pytest tests/test_brain.py -v"]
        if (self.root / "tests").exists():
            commands.append("python -m pytest tests/ -v --tb=short")
        if (self.root / "tests/test_final_s17.py").exists():
            commands.append("python tests/test_final_s17.py")
        return commands

    def _detect_run_commands(self) -> list[str]:
        commands = []
        if (self.root / "api/main.py").exists():
            commands.append("python -m uvicorn api.main:app --host 0.0.0.0 --port 8765")
        if (self.root / "start.sh").exists():
            commands.append("./start.sh")
        return commands

    def _detect_core_files(self) -> list[str]:
        return [
            "brain.py",
            "brain_daemon.py",
            "brain_meta.py",
            "task_dispatcher.py",
            "api/main.py",
            "ports/",
        ]

    def _detect_protected_rules(self) -> list[str]:
        return [
            "Do not modify core files without explicit user confirmation.",
            "Do not delete files without explicit user confirmation.",
            "Do not modify frontend routes or static mounts without confirmation.",
            "Every implementation task must report test status honestly.",
        ]

    def _read_optional(self, relative_path: str) -> str:
        path = self.root / relative_path
        if not path.exists() or not path.is_file():
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")

    def _git(self, args: list[str]) -> str | None:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.root,
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
        except Exception:
            return None
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None
