"""Tests for the Project Brain read-only API router."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.project_brain import router, _project_root

# ---------------------------------------------------------------------------
# Fixture: standalone FastAPI app with the project brain router
# ---------------------------------------------------------------------------

from fastapi import FastAPI

_app = FastAPI()
_app.include_router(router)
client = TestClient(_app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_project_state(tmp_path: Path, project_id: str = "test-proj") -> Path:
    state_dir = tmp_path / "data" / "projects" / project_id
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "project_state.json"
    state_path.write_text(json.dumps({
        "project_id": project_id,
        "project_name": "Test Project",
        "root": str(tmp_path),
        "updated_at": "2026-01-01T00:00:00+00:00",
        "languages": ["python"],
        "frameworks": ["fastapi"],
        "entrypoints": [],
        "test_commands": [],
        "run_commands": [],
        "core_files": ["brain.py"],
        "protected_rules": [],
        "recent_decisions": [],
        "known_risks": [],
        "last_task_report": None,
        "git_branch": "main",
        "git_commit": "abc1234",
        "capability_status": {"project_state": "stable"},
    }), encoding="utf-8")
    return state_path


def _ensure_report(tmp_path: Path, project_id: str, task_id: str) -> Path:
    reports_dir = tmp_path / "data" / "projects" / project_id / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    md_path = reports_dir / f"{task_id}.md"
    md_path.write_text(f"# Report: {task_id}\n\nSample content.\n", encoding="utf-8")
    return md_path


# ---------------------------------------------------------------------------
# Tests — using monkeypatch to override _project_root
# ---------------------------------------------------------------------------

class TestGetProjectState:
    def test_returns_state(self, tmp_path, monkeypatch):
        _ensure_project_state(tmp_path, "demo")
        import api.project_brain as mod
        monkeypatch.setattr(mod, "_project_root", lambda: tmp_path)
        resp = client.get("/api/project-brain/projects/demo/state")
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == "demo"
        assert body["project_name"] == "Test Project"

    def test_returns_404_when_missing(self, tmp_path, monkeypatch):
        import api.project_brain as mod
        monkeypatch.setattr(mod, "_project_root", lambda: tmp_path)
        resp = client.get("/api/project-brain/projects/nope/state")
        assert resp.status_code == 404


class TestListReports:
    def test_returns_empty_when_no_reports(self, tmp_path, monkeypatch):
        import api.project_brain as mod
        monkeypatch.setattr(mod, "_project_root", lambda: tmp_path)
        resp = client.get("/api/project-brain/projects/demo/reports")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_lists_reports(self, tmp_path, monkeypatch):
        _ensure_report(tmp_path, "demo", "smoke-test")
        _ensure_report(tmp_path, "demo", "another-test")
        import api.project_brain as mod
        monkeypatch.setattr(mod, "_project_root", lambda: tmp_path)
        resp = client.get("/api/project-brain/projects/demo/reports")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 2
        task_ids = {item["task_id"] for item in items}
        assert "smoke-test" in task_ids
        assert "another-test" in task_ids


class TestGetReport:
    def test_returns_report_markdown(self, tmp_path, monkeypatch):
        _ensure_report(tmp_path, "demo", "my-report")
        import api.project_brain as mod
        monkeypatch.setattr(mod, "_project_root", lambda: tmp_path)
        resp = client.get("/api/project-brain/projects/demo/reports/my-report")
        assert resp.status_code == 200
        body = resp.json()
        assert body["task_id"] == "my-report"
        assert "# Report: my-report" in body["markdown"]

    def test_returns_404_when_missing(self, tmp_path, monkeypatch):
        import api.project_brain as mod
        monkeypatch.setattr(mod, "_project_root", lambda: tmp_path)
        resp = client.get("/api/project-brain/projects/demo/reports/nonexistent")
        assert resp.status_code == 404


class TestGovernanceReview:
    def test_safe_files_approved(self, tmp_path, monkeypatch):
        import api.project_brain as mod
        monkeypatch.setattr(mod, "_project_root", lambda: tmp_path)
        resp = client.post(
            "/api/project-brain/projects/demo/governance/review",
            params={"files": ["scripts/foo.py"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["approved"] is True
        assert body["risk_level"] == "low"

    def test_protected_file_requires_confirmation(self, tmp_path, monkeypatch):
        import api.project_brain as mod
        monkeypatch.setattr(mod, "_project_root", lambda: tmp_path)
        resp = client.post(
            "/api/project-brain/projects/demo/governance/review",
            params={"files": ["brain.py"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["approved"] is False
        assert body["requires_confirmation"] is True
        assert "brain.py" in body["protected_files"]

    def test_dangerous_action_requires_confirmation(self, tmp_path, monkeypatch):
        import api.project_brain as mod
        monkeypatch.setattr(mod, "_project_root", lambda: tmp_path)
        resp = client.post(
            "/api/project-brain/projects/demo/governance/review",
            params={"actions": ["git push origin main"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["approved"] is False
        assert body["risk_level"] == "high"


class TestGovernanceDecisions:
    def test_returns_empty_when_no_log(self, tmp_path, monkeypatch):
        import api.project_brain as mod
        monkeypatch.setattr(mod, "_project_root", lambda: tmp_path)
        resp = client.get("/api/project-brain/projects/demo/governance/decisions")
        assert resp.status_code == 200
        assert resp.json() == []


class TestMemoryCandidates:
    def test_returns_empty_when_no_db(self, tmp_path, monkeypatch):
        import api.project_brain as mod
        monkeypatch.setattr(mod, "_project_root", lambda: tmp_path)
        resp = client.get("/api/project-brain/projects/demo/memory/candidates")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["candidates"] == []
