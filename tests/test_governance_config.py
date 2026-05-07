import json
import subprocess
from pathlib import Path

from governance.config import GovernanceConfigLoader
from governance.policy import GovernancePolicy

ROOT = Path(__file__).resolve().parent.parent


def _write_policy(root: Path, protected=None, dangerous=None):
    path = root / "data" / "governance" / "policies.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "additional_protected_patterns": protected or [],
        "additional_dangerous_actions": dangerous or [],
    }), encoding="utf-8")
    return path


def test_governance_config_loader_missing_file_returns_empty(tmp_path):
    config = GovernanceConfigLoader(tmp_path).load()
    assert config.protected_patterns == tuple()
    assert config.dangerous_actions == tuple()


def test_governance_config_loader_reads_additional_rules(tmp_path):
    _write_policy(tmp_path, protected=["deploy/"], dangerous=["terraform apply"])
    config = GovernanceConfigLoader(tmp_path).load()
    assert config.protected_patterns == ("deploy/",)
    assert config.dangerous_actions == ("terraform apply",)


def test_governance_policy_config_extends_but_does_not_weaken_core_rules(tmp_path):
    _write_policy(tmp_path, protected=["deploy/"], dangerous=["terraform apply"])
    policy = GovernancePolicy.from_project_root(tmp_path)
    core_review = policy.review(["brain.py"], [])
    custom_review = policy.review(["deploy/prod.yaml"], ["terraform apply -auto-approve"])
    safe_review = policy.review(["docs/readme.md"], ["documented plan"])
    assert core_review.approved is False
    assert core_review.protected_files == ["brain.py"]
    assert custom_review.approved is False
    assert custom_review.protected_files == ["deploy/prod.yaml"]
    assert custom_review.dangerous_actions == ["terraform apply -auto-approve"]
    assert safe_review.approved is True


def test_check_governance_script_uses_project_policy_config(tmp_path):
    _write_policy(tmp_path, protected=["deploy/"], dangerous=["terraform apply"])
    result = subprocess.run([
        "python",
        str(ROOT / "scripts" / "check_governance.py"),
        "--root",
        str(tmp_path),
        "--project-id",
        "demo",
        "--task-id",
        "configured-governance",
        "--files",
        "deploy/prod.yaml",
        "--actions",
        "terraform apply -auto-approve",
    ], capture_output=True, text=True, check=False)
    payload = json.loads(result.stdout)
    assert result.returncode == 2
    assert payload["approved"] is False
    assert payload["protected_files"] == ["deploy/prod.yaml"]
    assert payload["dangerous_actions"] == ["terraform apply -auto-approve"]
