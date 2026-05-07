import json
import subprocess
from pathlib import Path

from execution.evidence import LifecycleEvidence, TestEvidence
from execution.roles import SequentialRoleRunner
from governance.decision_log import GovernanceDecision, GovernanceDecisionLog
from governance.policy import GovernancePolicy

ROOT = Path(__file__).resolve().parent.parent


def test_governance_policy_allows_non_core_files():
    review = GovernancePolicy().review(["execution/roles.py", "tests/test_governance_and_roles.py"])
    assert review.approved is True
    assert review.risk_level == "low"
    assert review.requires_confirmation is False


def test_governance_policy_blocks_core_files_and_dangerous_actions():
    review = GovernancePolicy().review(["brain.py", "frontend-v2/app.js"], ["git push origin main"])
    assert review.approved is False
    assert review.risk_level == "high"
    assert review.requires_confirmation is True
    assert "brain.py" in review.protected_files
    assert "frontend-v2/app.js" in review.protected_files
    assert review.dangerous_actions == ["git push origin main"]


def test_governance_decision_log_roundtrip(tmp_path):
    log = GovernanceDecisionLog(tmp_path, project_id="demo")
    path = log.append(GovernanceDecision(
        task_id="gov-smoke",
        action="check",
        approved=True,
        risk_level="low",
        reasons=[],
        metadata={"files": ["execution/roles.py"]},
    ))
    loaded = log.read_all()
    assert path.exists()
    assert len(loaded) == 1
    assert loaded[0].task_id == "gov-smoke"
    assert loaded[0].metadata["files"] == ["execution/roles.py"]


def test_check_governance_script_logs_decision(tmp_path):
    result = subprocess.run([
        "python",
        str(ROOT / "scripts" / "check_governance.py"),
        "--root",
        str(tmp_path),
        "--project-id",
        "demo",
        "--task-id",
        "script-gov",
        "--files",
        "execution/roles.py",
        "--write-log",
    ], capture_output=True, text=True, check=False)
    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload["approved"] is True
    assert (tmp_path / "data" / "projects" / "demo" / "governance_decisions.jsonl").exists()


def test_sequential_roles_approve_safe_tested_task():
    evidence = LifecycleEvidence(task_id="roles-ok", goal="Verify roles.")
    evidence.tests.append(TestEvidence(command="python -m pytest tests/test_governance_and_roles.py -v", status="passed"))
    outputs = SequentialRoleRunner().run(evidence, ["Edited execution roles."], ["execution/roles.py"])
    assert [output.role for output in outputs] == ["Planner", "Executor", "Reviewer", "Reporter"]
    assert outputs[2].status == "approved"


def test_sequential_roles_reject_missing_tests_or_core_file():
    evidence = LifecycleEvidence(task_id="roles-risk", goal="Verify rejection.")
    outputs = SequentialRoleRunner().run(evidence, ["Edited core file."], ["brain.py"])
    assert outputs[2].status == "rejected"
    assert evidence.result == "partial"
    assert "Tests not recorded." in evidence.risks
