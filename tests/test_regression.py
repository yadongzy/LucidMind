"""Unified regression smoke tests for LucidMind infrastructure."""

import asyncio


def test_core_modules_import():
    import brain_config
    import brain_context
    import brain_tool_guard
    import project_state
    import reports
    import execution

    assert brain_config is not None
    assert brain_context is not None
    assert brain_tool_guard is not None
    assert project_state is not None
    assert reports is not None
    assert execution is not None


def test_project_brain_loop_smoke(tmp_path):
    from execution.evidence import TestEvidence
    from execution.lifecycle import TaskLifecycle

    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "main.py").write_text("app = object()\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_brain.py").write_text("def test_ok(): assert True\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")

    lifecycle = TaskLifecycle(tmp_path, project_id="demo")
    evidence = lifecycle.create_evidence("regression-smoke", "Verify lifecycle smoke.")
    evidence.tests.append(TestEvidence(command="python -m pytest tests/test_regression.py -v", status="not-run", output_summary="smoke placeholder"))
    path = lifecycle.write_report(evidence, "Regression Smoke")

    assert path.exists()
    assert (tmp_path / "data" / "projects" / "demo" / "project_state.json").exists()


def test_tool_safety_guard_fail_closed_smoke():
    from adapters.tools.tool_safety import ToolSafetyGuard

    guard = ToolSafetyGuard()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(guard.check("regression", "run_shell", {"command": "echo hi"}))

    assert result["approved"] is False
    assert "WebSocket" in result["reason"]


def test_memory_store_import_smoke():
    from memory.store import MemoryStore

    assert MemoryStore is not None
