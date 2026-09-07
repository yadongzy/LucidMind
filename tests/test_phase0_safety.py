"""Phase 0 安全修复测试 — ToolSafetyGuard 闭环 + 路径穿越防护 + HTTP 错误码。"""

import asyncio
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ─────────────── 节点 0.1: ToolSafetyGuard 审批链 ───────────────

class _MockAdapter:
    """模拟一个简单的 ToolPort adapter。"""
    def list_tools(self):
        return [{"type": "function", "function": {"name": "safe_tool", "description": "safe", "parameters": {}}}]

    async def execute(self, tool_name, params, **kw):
        return {"success": True, "result": f"executed {tool_name}", "error": None}


class _MockDangerousAdapter:
    def list_tools(self):
        return [{"type": "function", "function": {"name": "run_shell", "description": "shell", "parameters": {}}}]

    async def execute(self, tool_name, params, **kw):
        return {"success": True, "result": f"executed {tool_name}", "error": None}


class _MockSafetyGuard:
    """模拟 ToolSafetyGuard，可配置 check 返回值。"""
    def __init__(self, approved=True, reason=""):
        self._approved = approved
        self._reason = reason
        self.check_called = False
        self.last_tool_name = None

    async def check(self, session_id, tool_name, params):
        self.check_called = True
        self.last_tool_name = tool_name
        if self._approved:
            return {"approved": True}
        return {"approved": False, "reason": self._reason}


class _FailingSafetyGuard:
    async def check(self, session_id, tool_name, params):
        raise RuntimeError("guard unavailable")


@pytest.fixture
def composite_with_guard():
    from adapters.tools.composite import CompositeToolAdapter
    adapter = CompositeToolAdapter([_MockAdapter(), _MockDangerousAdapter()])
    guard = _MockSafetyGuard(approved=True)
    adapter.set_safety_guard(guard)
    return adapter, guard


@pytest.fixture
def composite_blocking_guard():
    from adapters.tools.composite import CompositeToolAdapter
    adapter = CompositeToolAdapter([_MockAdapter(), _MockDangerousAdapter()])
    guard = _MockSafetyGuard(approved=False, reason="用户拒绝")
    adapter.set_safety_guard(guard)
    return adapter, guard


@pytest.fixture
def composite_no_guard():
    from adapters.tools.composite import CompositeToolAdapter
    return CompositeToolAdapter([_MockAdapter()])


def test_composite_safety_guard_allows_safe(composite_with_guard):
    adapter, guard = composite_with_guard
    result = asyncio.get_event_loop().run_until_complete(
        adapter.execute("safe_tool", {}, session_id="test"))
    assert result["success"] is True
    assert guard.check_called is True
    assert guard.last_tool_name == "safe_tool"


def test_composite_safety_guard_blocks_dangerous(composite_blocking_guard):
    adapter, guard = composite_blocking_guard
    result = asyncio.get_event_loop().run_until_complete(
        adapter.execute("run_shell", {"command": "ls"}, session_id="test"))
    assert result["success"] is False
    assert "安全审批未通过" in result["error"]
    assert result.get("blocked") is True, "ISS-007: 安全拦截应返回 blocked=True"
    assert guard.check_called is True


def test_composite_without_guard_works(composite_no_guard):
    """向后兼容：无 guard 时直接执行。"""
    adapter = composite_no_guard
    result = asyncio.get_event_loop().run_until_complete(
        adapter.execute("safe_tool", {}))
    assert result["success"] is True


def test_composite_safety_guard_fails_closed():
    from adapters.tools.composite import CompositeToolAdapter
    adapter = CompositeToolAdapter([_MockDangerousAdapter()])
    adapter.set_safety_guard(_FailingSafetyGuard())
    result = asyncio.get_event_loop().run_until_complete(
        adapter.execute("run_shell", {"command": "ls"}, session_id="test"))
    assert result["success"] is False
    assert result["blocked"] is True
    assert "安全审批异常" in result["error"]


def test_composite_unknown_tool_returns_error(composite_no_guard):
    adapter = composite_no_guard
    result = asyncio.get_event_loop().run_until_complete(
        adapter.execute("nonexistent_tool", {}))
    assert result["success"] is False
    assert "未知工具" in result["error"]


# ─────────────── 节点 0.2: 路径穿越防护 ───────────────

from skills import _validate_plugin_name


def test_validate_plugin_name_normal():
    assert _validate_plugin_name("my_cool_plugin") is True
    assert _validate_plugin_name("clipboard") is True
    assert _validate_plugin_name("web-search") is True
    assert _validate_plugin_name("tool123") is True


def test_validate_plugin_name_path_traversal():
    assert _validate_plugin_name("../../evil") is False
    assert _validate_plugin_name("../etc") is False
    assert _validate_plugin_name("a/b/c") is False


def test_validate_plugin_name_backslash():
    assert _validate_plugin_name("a\\b") is False


def test_validate_plugin_name_empty():
    assert _validate_plugin_name("") is False


def test_validate_plugin_name_too_long():
    assert _validate_plugin_name("a" * 65) is False
    assert _validate_plugin_name("a" * 64) is True


def test_validate_plugin_name_special_chars():
    assert _validate_plugin_name("hello world") is False
    assert _validate_plugin_name("hello@world") is False
    assert _validate_plugin_name(".hidden") is False
    assert _validate_plugin_name("_private") is False  # 不以字母/数字开头


def test_validate_plugin_name_unicode():
    assert _validate_plugin_name("插件") is False


def test_validate_plugin_name_control_chars():
    assert _validate_plugin_name("hello\x00world") is False
    assert _validate_plugin_name("hello\nworld") is False


def test_install_from_hub_rejects_traversal():
    from skills import install_from_hub
    result = install_from_hub("../../etc")
    assert result["success"] is False
    assert "不合法" in result["error"]


# ─────────────── 节点 0.3: HTTP 错误码 ───────────────
# 这些测试需要 FastAPI TestClient

@pytest.fixture
def client():
    """创建 FastAPI 测试客户端（仅 plugins + mcp 路由）。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.plugins import router as plugins_router
    from api.mcp import router as mcp_router
    app = FastAPI()
    app.include_router(plugins_router)
    app.include_router(mcp_router)
    return TestClient(app)


def test_get_nonexistent_plugin_returns_404(client):
    resp = client.get("/api/plugins/nonexistent_plugin_xyz")
    assert resp.status_code == 404


def test_toggle_nonexistent_plugin_returns_404(client):
    resp = client.put("/api/plugins/nonexistent_plugin_xyz/toggle",
                      json={"enabled": True})
    assert resp.status_code == 404


def test_install_empty_name_returns_400(client):
    resp = client.post("/api/plugins/hub/install", json={})
    assert resp.status_code == 400


def test_install_traversal_name_returns_400(client):
    resp = client.post("/api/plugins/hub/install", json={"name": "../../evil"})
    assert resp.status_code == 400


def test_mcp_add_server_missing_name_returns_400(client):
    from api import mcp as mcp_api
    from unittest.mock import MagicMock
    mock_client = MagicMock()
    mcp_api._mcp_client = mock_client
    try:
        resp = client.post("/api/mcp/servers", json={"transport": "stdio"})
        assert resp.status_code == 400
    finally:
        mcp_api._mcp_client = None


def test_mcp_delete_nonexistent_returns_404(client):
    # 需要 mcp_client 已初始化
    from api import mcp as mcp_api
    from unittest.mock import MagicMock
    mock_client = MagicMock()
    mock_client.remove_server.return_value = False
    mcp_api._mcp_client = mock_client
    try:
        resp = client.delete("/api/mcp/servers/nonexistent_xyz")
        assert resp.status_code == 404
    finally:
        mcp_api._mcp_client = None
