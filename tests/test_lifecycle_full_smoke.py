import subprocess
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _minimal_project(root: Path):
    (root / "api").mkdir()
    (root / "api" / "main.py").write_text("app = object()\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_smoke.py").write_text("def test_ok(): assert True\n", encoding="utf-8")
    (root / "pyproject.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")


def test_lifecycle_script_safe_task_completes_and_writes_governance_review(tmp_path):
    _minimal_project(tmp_path)
    result = subprocess.run([
        "python",
        str(ROOT / "scripts" / "run_project_task_lifecycle.py"),
        "--root",
        str(tmp_path),
        "--project-id",
        "demo",
        "--task-id",
        "safe-full-smoke",
        "--title",
        "Safe Full Smoke",
        "--goal",
        "Verify safe lifecycle completion.",
        "--result",
        "complete",
        "--actions",
        "Updated non-core lifecycle helper",
        "--files",
        "execution/roles.py",
        "--tests",
        "python -m pytest tests/test_lifecycle_full_smoke.py -v",
        "--run-roles",
    ], capture_output=True, text=True, check=False)
    report = tmp_path / "data" / "projects" / "demo" / "reports" / "safe-full-smoke.md"
    content = report.read_text(encoding="utf-8")
    assert result.returncode == 0
    assert report.exists()
    assert "Reviewer:approved" in result.stdout
    assert "- **Result**: `complete`" in content
    assert "## Governance Review" in content
    assert "- **Governance Result**: `approved`" in content
    assert "- **Protected Files**: None" in content
    assert "- **Required Confirmations**: None" in content
    assert "- **Dangerous Actions**: None" in content


def test_lifecycle_script_core_file_task_is_rejected_but_writes_report(tmp_path):
    _minimal_project(tmp_path)
    result = subprocess.run([
        "python",
        str(ROOT / "scripts" / "run_project_task_lifecycle.py"),
        "--root",
        str(tmp_path),
        "--project-id",
        "demo",
        "--task-id",
        "core-risk-full-smoke",
        "--title",
        "Core Risk Full Smoke",
        "--goal",
        "Verify core file task is rejected.",
        "--result",
        "complete",
        "--actions",
        "Edited core file",
        "--files",
        "brain.py",
        "--tests",
        "python -m pytest tests/test_lifecycle_full_smoke.py -v",
        "--run-roles",
    ], capture_output=True, text=True, check=False)
    report = tmp_path / "data" / "projects" / "demo" / "reports" / "core-risk-full-smoke.md"
    content = report.read_text(encoding="utf-8")
    assert result.returncode == 0
    assert report.exists()
    assert "Reviewer:rejected" in result.stdout
    assert "- **Result**: `partial`" in content
    assert "- **Governance Result**: `requires-confirmation`" in content
    assert "- **Protected Files**: `brain.py`" in content
    assert "- **Required Confirmations**: `Protected files require explicit confirmation.`" in content


def test_lifecycle_script_remember_writes_project_memory(tmp_path):
    _minimal_project(tmp_path)
    result = subprocess.run([
        "python",
        str(ROOT / "scripts" / "run_project_task_lifecycle.py"),
        "--root",
        str(tmp_path),
        "--project-id",
        "demo",
        "--task-id",
        "remember-full-smoke",
        "--title",
        "Remember Full Smoke",
        "--goal",
        "Verify lifecycle report can write durable memories.",
        "--result",
        "complete",
        "--actions",
        "Generated report and memories",
        "--files",
        "scripts/run_project_task_lifecycle.py",
        "--tests",
        "python -m pytest tests/test_lifecycle_full_smoke.py -v",
        "--decisions",
        "Lifecycle script can write project memories with --remember",
        "--risks",
        "Memory pollution must remain filtered",
        "--run-roles",
        "--remember",
    ], capture_output=True, text=True, check=False)
    db_path = tmp_path / "data" / "projects" / "demo" / "project_memory.sqlite3"
    assert result.returncode == 0
    assert "Remembered" in result.stdout
    assert db_path.exists()
    with sqlite3.connect(db_path) as db:
        count = db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        collections = {row[0] for row in db.execute("SELECT DISTINCT collection FROM memories").fetchall()}
    assert count >= 4
    assert "project_decisions" in collections
    assert "project_risks" in collections
    assert "test_knowledge" in collections
    assert "task_summaries" in collections
