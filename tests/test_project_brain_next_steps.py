import json
import subprocess
from pathlib import Path

from execution.evidence import LifecycleEvidence, TestEvidence
from memory.project_memory import ProjectMemoryIntegrator
from skills.codex_cli.runner import CodexCliRunner

ROOT = Path(__file__).resolve().parent.parent


def test_lifecycle_script_writes_report(tmp_path):
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "main.py").write_text("app = object()\n", encoding="utf-8")
    command = [
        "python",
        str(ROOT / "scripts" / "run_project_task_lifecycle.py"),
        "--root",
        str(tmp_path),
        "--project-id",
        "demo",
        "--task-id",
        "script-smoke",
        "--title",
        "Script Smoke",
        "--goal",
        "Verify lifecycle script.",
        "--result",
        "complete",
        "--actions",
        "Ran lifecycle script",
        "--tests",
        "pytest smoke passed",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert (tmp_path / "data" / "projects" / "demo" / "reports" / "script-smoke.md").exists()


def test_project_memory_candidates_and_write(tmp_path):
    evidence = LifecycleEvidence(
        task_id="memory-smoke",
        goal="Verify memory candidates.",
        decisions=["Use concise durable project memories."],
        risks=["Memory pollution must be filtered."],
        actions_taken=["Created memory candidates."],
        files_changed=["memory/project_memory.py"],
    )
    evidence.tests.append(TestEvidence(command="python -m pytest tests/test_project_brain_next_steps.py -v", status="passed"))
    integrator = ProjectMemoryIntegrator(tmp_path / "memory.sqlite3")
    candidates = integrator.candidates_from_evidence(evidence)
    ids = integrator.remember_candidates(candidates)
    collections = {candidate.collection for candidate in candidates}
    assert "project_decisions" in collections
    assert "project_risks" in collections
    assert "test_knowledge" in collections
    assert "task_summaries" in collections
    assert len(ids) == len(candidates)


def test_codex_cli_missing_returns_guidance(tmp_path):
    runner = CodexCliRunner(tmp_path, executable="definitely-missing-codex-binary")
    result = runner.explain("project_state", "Explain indexer.")
    assert result.success is False
    assert "Codex CLI not found" in result.error
    assert result.exit_code is None


def test_codex_cli_read_only_command_construction(tmp_path):
    fake_codex = tmp_path / "fake_codex.py"
    fake_codex.write_text(
        "#!/usr/bin/env python\nimport json, sys\nprint(json.dumps({'argv': sys.argv[1:]}))\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    runner = CodexCliRunner(tmp_path, executable=str(fake_codex))
    result = runner.review("reports/task_reporter.py", "Review report rendering.")
    payload = json.loads(result.stdout)
    assert result.success is True
    assert "Read-only review request" in payload["argv"][0]
    assert "Do not modify files" in payload["argv"][0]
