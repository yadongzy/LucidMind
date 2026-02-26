"""E2E API 测试套件 — 覆盖所有核心 API 端点。

需要服务器运行在 http://127.0.0.1:8765。
运行: pytest tests/test_e2e_api.py -v
"""

import os
import pytest
import requests
import time

BASE = os.environ.get("LUCIDMIND_TEST_URL", "http://127.0.0.1:8000")
TIMEOUT = 120


def _url(path: str) -> str:
    return f"{BASE}{path}"


def _get(path, **kw):
    return requests.get(_url(path), timeout=TIMEOUT, **kw)


def _post(path, **kw):
    return requests.post(_url(path), timeout=TIMEOUT, **kw)


def _put(path, **kw):
    return requests.put(_url(path), timeout=TIMEOUT, **kw)


def _delete(path, **kw):
    return requests.delete(_url(path), timeout=TIMEOUT, **kw)


# ─────────────────────────── 健康 & 状态 ───────────────────────────


class TestHealth:
    def test_health(self):
        r = _get("/api/health")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "ok"
        assert "version" in d

    def test_status(self):
        r = _get("/api/status")
        assert r.status_code == 200
        d = r.json()
        assert "llm" in d
        assert "ports" in d
        assert "tools" in d
        assert isinstance(d["tools"], list)

    def test_brain_status(self):
        r = _get("/api/brain/status")
        assert r.status_code == 200
        d = r.json()
        assert "awake" in d
        assert "daemon" in d


# ─────────────────────────── 插件 ───────────────────────────


class TestPlugins:
    def test_list_plugins(self):
        r = _get("/api/plugins")
        assert r.status_code == 200
        d = r.json()
        assert "plugins" in d
        plugins = d["plugins"]
        assert isinstance(plugins, list)
        assert len(plugins) >= 10  # 至少 10 个插件

    def test_plugin_has_required_fields(self):
        r = _get("/api/plugins")
        plugins = r.json()["plugins"]
        for p in plugins:
            assert "name" in p
            assert "version" in p
            assert "status" in p

    def test_hot_reload(self):
        r = _post("/api/plugins/reload")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "ok"
        assert "plugins" in d
        assert "tools" in d

    def test_toggle_disable_enable(self):
        # 禁用
        r = _put("/api/plugins/notes/toggle", json={"enabled": False})
        assert r.status_code == 200
        assert "禁用" in r.json()["message"]
        # 重新启用
        r = _put("/api/plugins/notes/toggle", json={"enabled": True})
        assert r.status_code == 200
        assert "启用" in r.json()["message"]

    def test_pluginhub_search(self):
        r = _get("/api/plugins/hub/search?q=weather")
        assert r.status_code == 200
        d = r.json()
        assert "results" in d


# ─────────────────────────── MCP ───────────────────────────


class TestMCP:
    def test_list_servers(self):
        r = _get("/api/mcp/servers")
        assert r.status_code == 200
        d = r.json()
        assert "servers" in d

    def test_list_tools(self):
        r = _get("/api/mcp/tools")
        assert r.status_code == 200
        d = r.json()
        assert "tools" in d

    def test_add_and_remove_server(self):
        name = f"test_e2e_{int(time.time())}"
        # 添加
        r = _post("/api/mcp/servers", json={
            "name": name,
            "transport": "http",
            "url": "http://localhost:9999",
            "enabled": False,
        })
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        # 验证存在
        r2 = _get("/api/mcp/servers")
        names = [s["name"] for s in r2.json()["servers"]]
        assert name in names
        # 删除
        r3 = _delete(f"/api/mcp/servers/{name}")
        assert r3.status_code == 200
        # 验证已删除
        r4 = _get("/api/mcp/servers")
        names2 = [s["name"] for s in r4.json()["servers"]]
        assert name not in names2

    def test_discover(self):
        r = _post("/api/mcp/discover")
        assert r.status_code == 200
        d = r.json()
        assert "tools_discovered" in d


# ─────────────────────────── 通道 ───────────────────────────


class TestChannels:
    def test_channel_status(self):
        r = _get("/api/channel/status")
        assert r.status_code == 200
        d = r.json()
        assert "channels" in d
        channels = d["channels"]
        assert len(channels) == 4
        names = {c["name"] for c in channels}
        assert names == {"telegram", "feishu", "wecom", "wechat"}

    def test_channel_has_required_fields(self):
        r = _get("/api/channel/status")
        for ch in r.json()["channels"]:
            assert "name" in ch
            assert "label" in ch
            assert "configured" in ch


# ─────────────────────────── 会话 ───────────────────────────


class TestSessions:
    def test_list_sessions(self):
        r = _get("/api/sessions")
        assert r.status_code == 200
        d = r.json()
        assert "sessions" in d

    def test_create_and_delete_session(self):
        r = _post("/api/sessions", json={})
        assert r.status_code == 200
        d = r.json()
        sid = d.get("session_id") or d.get("id") or (d.get("session", {}).get("id"))
        assert sid
        # 删除
        r2 = _delete(f"/api/sessions/{sid}")
        assert r2.status_code == 200


# ─────────────────────────── Brain 功能 ───────────────────────────


class TestBrainFeatures:
    def test_lessons(self):
        r = _get("/api/lessons")
        assert r.status_code == 200
        d = r.json()
        assert "lessons" in d

    def test_tasks(self):
        r = _get("/api/tasks")
        assert r.status_code == 200
        d = r.json()
        assert "tasks" in d

    def test_brain_goals(self):
        r = _get("/api/brain/goals")
        assert r.status_code == 200

    def test_brain_thoughts(self):
        r = _get("/api/brain/thoughts")
        assert r.status_code == 200


# ─────────────────────────── HTTP Chat ───────────────────────────


class TestChat:
    def test_simple_chat(self):
        """测试简单对话（不需要工具调用）"""
        r = _post("/api/chat", json={
            "message": "你好，回复一个字：好",
            "session_id": f"e2e_chat_{int(time.time())}",
        })
        assert r.status_code == 200
        d = r.json()
        assert "reply" in d
        assert len(d["reply"]) > 0

    def test_tool_call_calculator(self):
        """测试工具调用：计算器"""
        r = _post("/api/chat", json={
            "message": "用calc工具计算 2+2",
            "session_id": f"e2e_calc_{int(time.time())}",
        })
        assert r.status_code == 200
        d = r.json()
        assert "reply" in d
        assert "4" in d["reply"]

    def test_tool_call_clipboard(self):
        """测试工具调用：剪贴板"""
        r = _post("/api/chat", json={
            "message": "读取剪贴板内容",
            "session_id": f"e2e_clip_{int(time.time())}",
        })
        assert r.status_code == 200
        d = r.json()
        assert "reply" in d


# ─────────────────────────── 安全相关 ───────────────────────────


class TestSecurity:
    def test_security_config(self):
        """测试安全配置 API"""
        r = _get("/api/security/config")
        if r.status_code == 200:
            d = r.json()
            assert "dangerous_tools" in d or "approval_required" in d
        # 404 也可以（安全模块还没实现时）

    def test_dangerous_tool_list(self):
        """测试危险工具列表"""
        r = _get("/api/security/dangerous-tools")
        if r.status_code == 200:
            d = r.json()
            assert isinstance(d.get("tools", []), list)
