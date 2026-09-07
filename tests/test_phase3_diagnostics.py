"""Phase 3 诊断系统测试 — DiagnosticEvent + Collector + API。"""

import os
import sys
import time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from diagnostics import (
    DiagnosticEvent, DiagnosticCollector, get_collector, record_event,
    reset_correlation_id, set_correlation_id,
)


# ─────────────── 节点 3.1: DiagnosticEvent 核心 ───────────────

def test_diagnostic_event_to_dict():
    e = DiagnosticEvent(
        timestamp=1000.0, category="tool_call", action="execute",
        status="success", duration_ms=42.5, input_summary="test",
        output_summary="ok", error=None, metadata={"k": "v"}, level="info",
    )
    d = e.to_dict()
    assert d["category"] == "tool_call"
    assert d["duration_ms"] == 42.5
    assert d["metadata"] == {"k": "v"}


def test_collector_record_and_query():
    c = DiagnosticCollector()
    e = DiagnosticEvent(
        timestamp=time.time(), category="tool_call", action="execute",
        status="success", duration_ms=10.0, input_summary="t1",
        output_summary="ok",
    )
    c.record(e)
    results = c.query(category="tool_call")
    assert len(results) >= 1
    assert results[-1]["input_summary"] == "t1"


def test_collector_query_filters():
    c = DiagnosticCollector()
    now = time.time()
    c.record(DiagnosticEvent(timestamp=now, category="tool_call", action="execute", status="success", duration_ms=10, input_summary="a", output_summary="ok"))
    c.record(DiagnosticEvent(timestamp=now, category="mcp_request", action="discover", status="failure", duration_ms=20, input_summary="b", output_summary="fail", error="timeout"))
    c.record(DiagnosticEvent(timestamp=now, category="tool_call", action="execute", status="failure", duration_ms=30, input_summary="c", output_summary="fail", error="err"))

    assert len(c.query(category="tool_call")) == 2
    assert len(c.query(status="failure")) == 2
    assert len(c.query(category="tool_call", status="failure")) == 1


def test_collector_summary():
    c = DiagnosticCollector()
    now = time.time()
    for i in range(5):
        c.record(DiagnosticEvent(timestamp=now, category="tool_call", action="execute", status="success", duration_ms=10 + i, input_summary="", output_summary=""))
    c.record(DiagnosticEvent(timestamp=now, category="tool_call", action="execute", status="failure", duration_ms=100, input_summary="", output_summary="", error="err"))

    s = c.summary()
    assert s["total"] == 6
    tc = s["categories"]["tool_call"]
    assert tc["success"] == 5
    assert tc["failure"] == 1
    assert tc["success_rate"] == pytest.approx(5 / 6, abs=0.01)
    assert tc["avg_duration_ms"] > 0


def test_collector_memory_limit():
    c = DiagnosticCollector()
    for i in range(1100):
        c.record(DiagnosticEvent(timestamp=time.time(), category="test", action="x", status="success", duration_ms=0, input_summary="", output_summary=""))
    assert len(c._events) <= 1000


def test_record_event_convenience():
    """便捷函数 record_event 应成功记录。"""
    record_event("test_cat", "test_act", "success", 1.0, input_summary="hello")
    results = get_collector().query(category="test_cat")
    assert any(r["action"] == "test_act" for r in results)


def test_record_event_inherits_context_correlation_id():
    token = set_correlation_id("task:abc123")
    try:
        record_event("test_correlation", "execute", "success", 1.0)
    finally:
        reset_correlation_id(token)
    event = get_collector().query(category="test_correlation")[-1]
    assert event["metadata"]["correlation_id"] == "task:abc123"


def test_explicit_correlation_id_takes_precedence():
    token = set_correlation_id("task:context")
    try:
        record_event(
            "test_explicit_correlation", "execute", "success", 1.0,
            metadata={"correlation_id": "request:explicit"},
        )
    finally:
        reset_correlation_id(token)
    event = get_collector().query(category="test_explicit_correlation")[-1]
    assert event["metadata"]["correlation_id"] == "request:explicit"


def test_collector_persistence(tmp_path):
    """JSONL 持久化。"""
    import diagnostics as diag
    old_dir = diag._DATA_DIR
    diag._DATA_DIR = tmp_path
    c = DiagnosticCollector()
    c.record(DiagnosticEvent(timestamp=time.time(), category="test", action="persist", status="success", duration_ms=5, input_summary="", output_summary=""))
    # 检查文件是否创建
    jsonl_files = list(tmp_path.glob("diagnostics_*.jsonl"))
    assert len(jsonl_files) >= 1
    content = jsonl_files[0].read_text()
    assert "persist" in content
    diag._DATA_DIR = old_dir


# ─────────────── 节点 3.3: 诊断 API ───────────────

@pytest.fixture
def api_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.diagnostics import router
    app = FastAPI()
    app.include_router(router)
    # 预先记录一些事件
    record_event("tool_call", "execute", "success", 10.0, input_summary="test_tool")
    record_event("tool_call", "execute", "failure", 50.0, error="err")
    return TestClient(app)


def test_diagnostics_api_query(api_client):
    resp = api_client.get("/api/diagnostics")
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert "total" in data


def test_diagnostics_api_summary(api_client):
    resp = api_client.get("/api/diagnostics/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "categories" in data


def test_diagnostics_api_timeline(api_client):
    resp = api_client.get("/api/diagnostics/timeline?minutes=60")
    assert resp.status_code == 200
    data = resp.json()
    assert "buckets" in data


def test_diagnostics_api_filter(api_client):
    resp = api_client.get("/api/diagnostics?category=tool_call&status=failure")
    assert resp.status_code == 200
    data = resp.json()
    for e in data["events"]:
        assert e["category"] == "tool_call"
        assert e["status"] == "failure"
