import asyncio
import json
from pathlib import Path

from execution.evidence import TestEvidence
from execution.lifecycle import TaskLifecycle
from project_state.indexer import ProjectStateIndexer
from project_state.store import ProjectStateStore
from reports.task_reporter import TaskReport, TaskReportGenerator


def _write_minimal_project(root: Path):
    (root / "api").mkdir()
    (root / "api" / "main.py").write_text("app = object()\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_brain.py").write_text("def test_ok(): assert True\n", encoding="utf-8")
    (root / "pyproject.toml").write_text('[project]\nname = "demo"\ndependencies = ["fastapi"]\n', encoding="utf-8")
    (root / "requirements.txt").write_text("uvicorn\npytest\n", encoding="utf-8")


def test_project_state_indexer_detects_minimal_project(tmp_path):
    _write_minimal_project(tmp_path)
    state = ProjectStateIndexer(tmp_path, project_id="demo").build()
    assert state.project_id == "demo"
    assert state.project_name == "demo"
    assert "python" in state.languages
    assert "fastapi" in state.frameworks
    assert "api/main.py" in state.entrypoints
    assert "python -m pytest tests/test_brain.py -v" in state.test_commands
    assert "api/main.py" in state.core_files
    assert state.capability_status["project_state"] == "stable"


def test_project_state_store_preserves_decisions_and_risks(tmp_path):
    _write_minimal_project(tmp_path)
    store = ProjectStateStore(tmp_path, project_id="demo")
    state = ProjectStateIndexer(tmp_path, project_id="demo").build()
    state.recent_decisions = ["Use project brain loop first."]
    state.known_risks = ["Avoid open-ended swarm first."]
    store.save(state)
    refreshed = ProjectStateIndexer(tmp_path, project_id="demo").build()
    store.save(refreshed)
    loaded = store.load()
    assert loaded is not None
    assert loaded.recent_decisions == ["Use project brain loop first."]
    assert loaded.known_risks == ["Avoid open-ended swarm first."]


def test_task_report_generator_uses_project_scoped_path(tmp_path):
    report = TaskReport(
        task_id="task 001",
        title="Demo",
        goal="Generate a report.",
        project_id="demo",
        tests_run=[],
    )
    path = TaskReportGenerator(tmp_path).save(report)
    assert path == tmp_path / "data" / "projects" / "demo" / "reports" / "task-001.md"
    content = path.read_text(encoding="utf-8")
    assert "Tests were not run." in content
    assert "# Task Report: Demo" in content


def test_task_lifecycle_writes_report_and_updates_project_state(tmp_path):
    _write_minimal_project(tmp_path)
    lifecycle = TaskLifecycle(tmp_path, project_id="demo")
    evidence = lifecycle.create_evidence("task-123", "Implement minimal lifecycle.")
    evidence.actions_taken.append("Created lifecycle evidence.")
    evidence.files_changed.append("execution/lifecycle.py")
    evidence.tests.append(TestEvidence(command="python -m pytest tests/test_project_brain_loop.py -v", status="passed", output_summary="4 passed"))
    evidence.result = "complete"
    path = lifecycle.write_report(evidence, title="Minimal Lifecycle", next_step="Expose report in UI.")
    assert path.exists()
    state_data = json.loads((tmp_path / "data" / "projects" / "demo" / "project_state.json").read_text(encoding="utf-8"))
    assert state_data["last_task_report"] == "data/projects/demo/reports/task-123.md"


def test_tool_safety_guard_fails_closed_without_websocket():
    from adapters.tools.tool_safety import ToolSafetyGuard
    guard = ToolSafetyGuard()
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(guard.check("session", "run_shell", {"command": "echo hi"}))
    assert result["approved"] is False
    assert "WebSocket" in result["reason"]
