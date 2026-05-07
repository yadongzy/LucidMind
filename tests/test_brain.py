"""Rule-required regression smoke entrypoint."""

import asyncio

from execution.evidence import LifecycleEvidence, TestEvidence
from execution.roles import SequentialRoleRunner
from governance.policy import GovernancePolicy


def test_project_brain_core_imports():
    import brain_config
    import brain_context
    import execution
    import governance
    import project_state
    import reports

    assert brain_config is not None
    assert brain_context is not None
    assert execution is not None
    assert governance is not None
    assert project_state is not None
    assert reports is not None


def test_tool_safety_guard_fails_closed_regression():
    from adapters.tools.tool_safety import ToolSafetyGuard

    guard = ToolSafetyGuard()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(guard.check("regression", "run_shell", {"command": "echo hi"}))

    assert result["approved"] is False
    assert "WebSocket" in result["reason"]


def test_governance_rejects_core_file_regression():
    review = GovernancePolicy().review(["brain.py"], ["edit core file"])

    assert review.approved is False
    assert review.requires_confirmation is True
    assert review.protected_files == ["brain.py"]


def test_sequential_roles_safe_task_regression():
    evidence = LifecycleEvidence(task_id="brain-regression-safe", goal="Verify safe task.")
    evidence.tests.append(TestEvidence(command="python -m pytest tests/test_brain.py -v", status="passed"))
    outputs = SequentialRoleRunner().run(evidence, ["Updated non-core test."], ["tests/test_brain.py"])

    assert outputs[2].role == "Reviewer"
    assert outputs[2].status == "approved"


def test_sequential_roles_core_task_rejected_regression():
    evidence = LifecycleEvidence(task_id="brain-regression-core", goal="Verify core rejection.")
    evidence.tests.append(TestEvidence(command="python -m pytest tests/test_brain.py -v", status="passed"))
    outputs = SequentialRoleRunner().run(evidence, ["Edited core file."], ["brain.py"])

    assert outputs[2].role == "Reviewer"
    assert outputs[2].status == "rejected"
    assert evidence.result == "partial"
