"""Tests for codex_patch gating, metrics collection, and milestone demo."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skills.codex_cli.runner import CodexCliRunner, CodexCliResult
from reports.metrics import TaskMetrics, MetricsCollector


class TestCodexPatch:
    def test_patch_blocked_without_approval(self, tmp_path):
        runner = CodexCliRunner(tmp_path)
        result = runner.patch("src/foo.py", "Add logging")
        assert not result.success
        assert "approval" in result.error.lower()

    def test_patch_with_approval_but_missing_cli(self, tmp_path):
        runner = CodexCliRunner(tmp_path, executable="definitely-missing-codex")
        result = runner.patch("src/foo.py", "Add logging", approved=True)
        assert not result.success
        assert "not found" in result.error.lower()

    def test_fix_tests_blocked_without_approval(self, tmp_path):
        runner = CodexCliRunner(tmp_path)
        result = runner.fix_tests("pytest tests/ -v")
        assert not result.success
        assert "approval" in result.error.lower()

    def test_fix_tests_with_approval_but_missing_cli(self, tmp_path):
        runner = CodexCliRunner(tmp_path, executable="definitely-missing-codex")
        result = runner.fix_tests("pytest tests/ -v", approved=True)
        assert not result.success
        assert "not found" in result.error.lower()


class TestMetricsCollector:
    def test_record_and_read(self, tmp_path):
        collector = MetricsCollector(tmp_path, "test-proj")
        m = TaskMetrics(project_id="test-proj", task_id="t1", files_changed=3, tests_passed=5, completion_status="complete")
        collector.record(m)

        all_metrics = collector.read_all()
        assert len(all_metrics) == 1
        assert all_metrics[0].task_id == "t1"
        assert all_metrics[0].files_changed == 3

    def test_summary(self, tmp_path):
        collector = MetricsCollector(tmp_path, "test-proj")
        collector.record(TaskMetrics(project_id="test-proj", task_id="t1", files_changed=2, completion_status="complete", report_generated=True))
        collector.record(TaskMetrics(project_id="test-proj", task_id="t2", files_changed=1, completion_status="partial", report_generated=True))
        collector.record(TaskMetrics(project_id="test-proj", task_id="t3", completion_status="blocked"))

        s = collector.summary()
        assert s["total_tasks"] == 3
        assert s["complete"] == 1
        assert s["partial"] == 1
        assert s["blocked"] == 1
        assert s["total_files_changed"] == 3
        assert s["reports_generated"] == 2

    def test_empty_summary(self, tmp_path):
        collector = MetricsCollector(tmp_path, "empty")
        s = collector.summary()
        assert s["total_tasks"] == 0


class TestMetricsAPI:
    def test_metrics_endpoint(self, tmp_path, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.project_brain import router
        import api.project_brain as mod

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        monkeypatch.setattr(mod, "_project_root", lambda: tmp_path)

        resp = client.get("/api/project-brain/projects/demo/metrics")
        assert resp.status_code == 200
        assert resp.json()["total_tasks"] == 0

    def test_metrics_history_endpoint(self, tmp_path, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api.project_brain import router
        import api.project_brain as mod

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        monkeypatch.setattr(mod, "_project_root", lambda: tmp_path)

        resp = client.get("/api/project-brain/projects/demo/metrics/history")
        assert resp.status_code == 200
        assert resp.json() == []
