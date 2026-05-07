"""Checkup 模块单元测试 — 覆盖进化引擎全部 8 个模块。"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ─── 1. Runner ────────────────────────────────────────

class TestProjectCheckupRunner:
    def test_run_all_returns_report(self):
        from checkup.runner import ProjectCheckupRunner
        runner = ProjectCheckupRunner(".", "test")
        report = runner.run_all()
        assert 0 <= report.score <= 100
        assert len(report.checks) == 7
        assert report.project_id == "test"
        assert report.timestamp

    def test_report_to_dict(self):
        from checkup.runner import ProjectCheckupRunner
        runner = ProjectCheckupRunner(".", "test")
        report = runner.run_all()
        d = report.to_dict()
        assert "score" in d
        assert "checks" in d
        assert isinstance(d["checks"], list)

    def test_report_to_markdown(self):
        from checkup.runner import ProjectCheckupRunner
        runner = ProjectCheckupRunner(".", "test")
        report = runner.run_all()
        md = report.to_markdown()
        assert "# 项目体检报告" in md
        assert "健康分数" in md

    def test_check_item_statuses(self):
        from checkup.runner import ProjectCheckupRunner
        runner = ProjectCheckupRunner(".", "test")
        report = runner.run_all()
        valid = {"pass", "warn", "fail", "skip", "pending"}
        for c in report.checks:
            assert c.status in valid, f"{c.name} has invalid status: {c.status}"

    def test_score_calculation(self):
        from checkup.runner import CheckItem, ProjectCheckupRunner
        items = [
            CheckItem(name="a", status="pass"),
            CheckItem(name="b", status="fail"),
        ]
        score = ProjectCheckupRunner._calc_score(items)
        assert score == 50  # (100 + 0) / 2

    def test_summary_calculation(self):
        from checkup.runner import CheckItem, ProjectCheckupRunner
        items = [
            CheckItem(name="a", status="pass"),
            CheckItem(name="b", status="pass"),
            CheckItem(name="c", status="fail"),
        ]
        summary = ProjectCheckupRunner._calc_summary(items)
        assert summary == {"pass": 2, "fail": 1}


# ─── 2. Diagnosis ─────────────────────────────────────

class TestDiagnosis:
    def _make_checkup(self):
        from checkup.runner import ProjectCheckupRunner
        return ProjectCheckupRunner(".", "test").run_all().to_dict()

    def test_diagnose_returns_report(self):
        from checkup.diagnosis import diagnose_checkup
        diag = diagnose_checkup(self._make_checkup())
        assert "total" in diag.summary
        assert isinstance(diag.items, list)

    def test_severity_levels(self):
        from checkup.diagnosis import diagnose_checkup
        diag = diagnose_checkup(self._make_checkup())
        for item in diag.items:
            assert 0 <= item.severity_level <= 4

    def test_classify_severity(self):
        from checkup.diagnosis import classify_severity
        assert classify_severity("F401") == 1
        assert classify_severity("frozen_file_modified") == 4
        assert classify_severity("doc_missing") == 0
        assert classify_severity("unknown_code") == 2  # default

    def test_auto_fixable_filter(self):
        from checkup.diagnosis import diagnose_checkup, get_auto_fixable
        diag = diagnose_checkup(self._make_checkup())
        auto = get_auto_fixable(diag)
        for item in auto:
            assert item.auto_fixable is True
            assert item.severity_level <= 1


# ─── 3. Evolution Log ─────────────────────────────────

class TestEvolutionLog:
    def test_create_and_record_bead(self):
        from checkup.evolution_log import EvolutionLog
        with tempfile.TemporaryDirectory() as td:
            log = EvolutionLog(Path(td))
            bead = log.create_bead("test", "D-001", "L0", "action")
            assert bead.id.startswith("EVOL-")
            assert bead.trigger == "test"
            bead.outcome = "success"
            log.record(bead)

    def test_get_recent(self):
        from checkup.evolution_log import EvolutionLog
        with tempfile.TemporaryDirectory() as td:
            log = EvolutionLog(Path(td))
            for i in range(5):
                b = log.create_bead("test", f"D-{i}", "L0", f"action-{i}")
                b.outcome = "success"
                log.record(b)
            recent = log.get_recent(3)
            assert len(recent) == 3

    def test_get_stats(self):
        from checkup.evolution_log import EvolutionLog
        with tempfile.TemporaryDirectory() as td:
            log = EvolutionLog(Path(td))
            b1 = log.create_bead("test"); b1.outcome = "success"; log.record(b1)
            b2 = log.create_bead("test"); b2.outcome = "failure"; log.record(b2)
            stats = log.get_stats()
            assert stats["total"] == 2
            assert stats["success"] == 1
            assert stats["failure"] == 1
            assert stats["success_rate"] == 0.5

    def test_counter_persistence(self):
        from checkup.evolution_log import EvolutionLog
        with tempfile.TemporaryDirectory() as td:
            log1 = EvolutionLog(Path(td))
            log1.create_bead("test")
            log1.create_bead("test")
            log2 = EvolutionLog(Path(td))
            b = log2.create_bead("test")
            assert b.id == "EVOL-0003"


# ─── 4. User Behavior ─────────────────────────────────

class TestUserBehavior:
    def test_analyze_empty(self):
        from checkup.user_behavior import UserBehaviorAnalyzer
        with tempfile.TemporaryDirectory() as td:
            az = UserBehaviorAnalyzer(Path(td))
            patterns = az.analyze({})
            assert patterns == []

    def test_detect_frequent_queries(self):
        from checkup.user_behavior import UserBehaviorAnalyzer
        with tempfile.TemporaryDirectory() as td:
            az = UserBehaviorAnalyzer(Path(td))
            stats = {"topic_counts": {"python": 5, "rust": 1}}
            patterns = az.analyze(stats)
            freq = [p for p in patterns if p.pattern_type == "frequent_query"]
            assert len(freq) == 1
            assert "python" in freq[0].description

    def test_detect_repeated_questions(self):
        from checkup.user_behavior import UserBehaviorAnalyzer
        with tempfile.TemporaryDirectory() as td:
            az = UserBehaviorAnalyzer(Path(td))
            stats = {"repeated_questions": 5, "total_messages": 20}
            patterns = az.analyze(stats)
            assert any(p.pattern_type == "frequent_query" for p in patterns)

    def test_generate_suggestions(self):
        from checkup.user_behavior import UserBehaviorAnalyzer, BehaviorPattern
        with tempfile.TemporaryDirectory() as td:
            az = UserBehaviorAnalyzer(Path(td))
            patterns = [BehaviorPattern(
                pattern_type="error_hotspot",
                description="loops",
                suggestion="fix it",
                confidence=0.8,
            )]
            sug = az.generate_suggestions(patterns)
            assert len(sug) == 1
            assert sug[0].source_pattern == "error_hotspot"

    def test_low_confidence_filtered(self):
        from checkup.user_behavior import UserBehaviorAnalyzer, BehaviorPattern
        with tempfile.TemporaryDirectory() as td:
            az = UserBehaviorAnalyzer(Path(td))
            patterns = [BehaviorPattern(
                pattern_type="test", description="x",
                suggestion="y", confidence=0.3,
            )]
            sug = az.generate_suggestions(patterns)
            assert len(sug) == 0


# ─── 5. Negotiation ───────────────────────────────────

class TestNegotiation:
    def test_create_request(self):
        from checkup.negotiation import NegotiationProtocol
        proto = NegotiationProtocol()
        req = proto.create_request("problem X", "ctx", ["no delete"])
        assert req.id.startswith("NEG-")
        assert req.problem == "problem X"
        assert "no delete" in req.constraints

    def test_to_prompt(self):
        from checkup.negotiation import NegotiationProtocol
        proto = NegotiationProtocol()
        req = proto.create_request("problem X")
        prompt = req.to_prompt()
        assert "problem X" in prompt
        assert "JSON" in prompt

    def test_parse_response_valid_json(self):
        from checkup.negotiation import NegotiationProtocol
        proto = NegotiationProtocol()
        raw = json.dumps([
            {"id": "A", "title": "Fix", "description": "d",
             "approach": "fix_code", "estimated_risk": "low",
             "estimated_effort": "small", "files_affected": [],
             "pros": ["fast"], "cons": ["risky"]},
            {"id": "B", "title": "Refactor", "description": "d2",
             "approach": "refactor", "estimated_risk": "high",
             "estimated_effort": "large", "files_affected": [],
             "pros": [], "cons": []},
        ])
        resp = proto.parse_response("NEG-001", raw)
        assert len(resp.proposals) == 2

    def test_parse_response_invalid_fallback(self):
        from checkup.negotiation import NegotiationProtocol
        proto = NegotiationProtocol()
        resp = proto.parse_response("NEG-001", "just some text")
        assert len(resp.proposals) == 1
        assert resp.proposals[0].id == "A"

    def test_evaluate_prefers_low_risk(self):
        from checkup.negotiation import NegotiationProtocol, Proposal
        proto = NegotiationProtocol()
        proposals = [
            Proposal(id="A", title="a", description="", approach="fix_code",
                     estimated_risk="high", estimated_effort="small"),
            Proposal(id="B", title="b", description="", approach="fix_code",
                     estimated_risk="low", estimated_effort="medium"),
        ]
        best = proto.evaluate_proposals(proposals)
        assert best.id == "B"

    def test_record_decision(self):
        from checkup.negotiation import NegotiationProtocol
        proto = NegotiationProtocol()
        d = proto.record_decision("NEG-001", "A", "approved", decided_by="user")
        assert d.selected_proposal_id == "A"
        assert d.decided_by == "user"


# ─── 6. Reflection Generator ──────────────────────────

class TestReflectionGen:
    def test_generate_with_no_data(self):
        from checkup.reflection_gen import generate_reflection
        content = generate_reflection()
        assert "# REFLECTION.md" in content
        assert "未运行体检" in content

    def test_generate_with_checkup(self):
        from checkup.reflection_gen import generate_reflection
        checkup = {
            "score": 80,
            "checks": [
                {"name": "测试", "status": "pass", "message": "OK"},
                {"name": "lint", "status": "warn", "message": "5 issues"},
            ],
        }
        content = generate_reflection(checkup_report=checkup)
        assert "80/100" in content
        assert "测试" in content

    def test_save_reflection(self):
        from checkup.reflection_gen import generate_reflection
        content = generate_reflection()
        assert "下一步行动" in content

    def test_next_actions_generated(self):
        from checkup.reflection_gen import generate_reflection
        checkup = {
            "score": 50,
            "checks": [{"name": "X", "status": "fail", "message": "broken"}],
        }
        content = generate_reflection(checkup_report=checkup)
        assert "修复" in content


# ─── 7. Codex Repair ──────────────────────────────────

class TestCodexRepair:
    def test_plan_repairs_l2_only(self):
        from checkup.codex_repair import CodexRepairEngine
        from checkup.diagnosis import DiagnosisReport, DiagnosisItem
        engine = CodexRepairEngine(".", "test")
        diag = DiagnosisReport(items=[
            DiagnosisItem(id="D-1", source_check="test", issue_code="F401",
                         severity_level=1, title="unused", description="x"),
            DiagnosisItem(id="D-2", source_check="test", issue_code="test_failure",
                         severity_level=2, title="fail", description="y"),
            DiagnosisItem(id="D-3", source_check="test", issue_code="frozen_file_modified",
                         severity_level=4, title="frozen", description="z"),
        ])
        plans = engine.plan_repairs(diag)
        assert len(plans) == 1  # only L2
        assert plans[0]["severity"] == "L2"

    def test_l4_report(self):
        from checkup.codex_repair import CodexRepairEngine
        from checkup.diagnosis import DiagnosisReport, DiagnosisItem
        engine = CodexRepairEngine(".", "test")
        diag = DiagnosisReport(items=[
            DiagnosisItem(id="D-3", source_check="test", issue_code="frozen",
                         severity_level=4, title="frozen", description="z"),
        ])
        l4 = engine.generate_l4_report(diag)
        assert len(l4) == 1
        assert l4[0]["action"] == "MANUAL_REVIEW_ONLY"

    def test_execute_without_approval(self):
        from checkup.codex_repair import CodexRepairEngine
        engine = CodexRepairEngine(".", "test")
        result = engine.execute_repair({"severity": "L2"}, approved=False)
        assert result["status"] == "pending_approval"

    def test_constraints_l3(self):
        from checkup.codex_repair import CodexRepairEngine
        engine = CodexRepairEngine(".", "test")
        c = engine._get_constraints(3)
        assert any("不得删除" in x for x in c)


# ─── 8. Auto Repair Pipeline ──────────────────────────

class TestAutoRepair:
    def test_pipeline_import(self):
        from checkup.auto_repair import AutoRepairPipeline
        pipeline = AutoRepairPipeline(".", "test")
        assert pipeline.root.exists()

    def test_get_pending_l2_plus(self):
        from checkup.auto_repair import AutoRepairPipeline
        from checkup.diagnosis import DiagnosisReport, DiagnosisItem
        pipeline = AutoRepairPipeline(".", "test")
        diag = DiagnosisReport(items=[
            DiagnosisItem(id="D-1", source_check="t", issue_code="x",
                         severity_level=1, title="a", description="b"),
            DiagnosisItem(id="D-2", source_check="t", issue_code="y",
                         severity_level=3, title="c", description="d"),
        ])
        pending = pipeline.get_pending_l2_plus(diag)
        assert len(pending) == 1
        assert pending[0]["id"] == "D-2"
