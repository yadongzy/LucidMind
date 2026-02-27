"""L4: 真实操作 E2E 测试 — WebSocket对话 + 上传 + Cron CRUD + JWT + 插件Toggle + MCP CRUD。

迁移自以前 v1 测试 (test_s59_e2e, test_e2e_api, test_s42_s48_browser 等)，
更新为当前 v2 架构 (port 8000, Lit frontend)。

运行: pytest tests/test_e2e_realops.py -v
需要: 服务器运行在 http://127.0.0.1:8000
"""

import asyncio
import io
import json
import os
import time

import pytest
import requests

BASE = os.environ.get("LUCIDMIND_TEST_URL", "http://127.0.0.1:8000")
TIMEOUT = 30


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


# ═══════════════════════ 1. WebSocket 真实对话 ═══════════════════════


class TestWebSocketChat:
    """WebSocket 连接 + 心跳 + 真实对话。"""

    def test_ws_heartbeat_pong(self):
        """WebSocket 心跳 ping → pong 响应。"""
        import websockets

        async def _run():
            uri = f"ws://127.0.0.1:8000/ws"
            async with websockets.connect(uri, ping_interval=None) as ws:
                await ws.send(json.dumps({"type": "ping"}))
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                data = json.loads(raw)
                assert data["type"] == "pong"
                assert "ts" in data

        asyncio.get_event_loop().run_until_complete(_run())

    def test_ws_chat_simple(self):
        """WebSocket 真实对话：发消息 → 收到回复 → 收到 complete。"""
        import websockets

        async def _run():
            uri = f"ws://127.0.0.1:8000/ws"
            sid = f"e2e_ws_{int(time.time())}"
            async with websockets.connect(uri, ping_interval=None) as ws:
                await ws.send(json.dumps({
                    "type": "chat",
                    "message": "回复一个字：好",
                    "session_id": sid,
                }))
                got_resp = False
                got_done = False
                t0 = time.time()
                while time.time() - t0 < 60:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=30)
                        d = json.loads(raw)
                        if d["type"] in ("response", "response_delta", "response_start"):
                            got_resp = True
                        elif d["type"] == "complete":
                            got_done = True
                            break
                    except asyncio.TimeoutError:
                        break
                assert got_resp, "应收到 response 消息"
                assert got_done, "应收到 complete 消息"

        asyncio.get_event_loop().run_until_complete(_run())

    def test_http_chat_simple(self):
        """HTTP Chat API：发消息 → 收到回复。"""
        sid = f"e2e_http_{int(time.time())}"
        r = _post("/api/chat", json={
            "message": "回复一个字：好",
            "session_id": sid,
        })
        assert r.status_code == 200
        d = r.json()
        assert "reply" in d
        assert len(d["reply"]) > 0


# ═══════════════════════ 2. 文件上传 ═══════════════════════


class TestFileUpload:
    """文件上传 CRUD。"""

    def test_upload_text_file(self):
        """上传文本文件 → 正确分类为 document。"""
        files = {"file": ("test_e2e.txt", io.BytesIO(b"hello world e2e"), "text/plain")}
        r = _post("/api/upload", files=files)
        assert r.status_code == 200
        d = r.json()
        assert d["filename"] == "test_e2e.txt"
        assert d["size"] == 15
        assert d["kind"] == "document"

    def test_upload_image(self):
        """上传 1x1 PNG → 正确分类为 image。"""
        png = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
               b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00'
               b'\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00'
               b'\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82')
        files = {"file": ("test_e2e.png", io.BytesIO(png), "image/png")}
        r = _post("/api/upload", files=files)
        assert r.status_code == 200
        assert r.json()["kind"] == "image"

    def test_upload_audio(self):
        """上传假 MP3 → 正确分类为 audio。"""
        files = {"file": ("test_e2e.mp3", io.BytesIO(b"\xff\xfb\x90\x00" * 10), "audio/mpeg")}
        r = _post("/api/upload", files=files)
        assert r.status_code == 200
        assert r.json()["kind"] == "audio"

    def test_uploads_list(self):
        """上传列表 API 返回 200。"""
        r = _get("/api/uploads")
        assert r.status_code == 200


# ═══════════════════════ 3. Cron CRUD ═══════════════════════


class TestCronCRUD:
    """定时任务完整 CRUD 生命周期。"""

    def test_cron_create_list_delete(self):
        """创建定时任务 → 验证存在 → 删除 → 验证已删除。"""
        # 创建
        r = _post("/api/cron", json={
            "description": "e2e test cron job",
            "interval_seconds": 3600,
            "command": "echo e2e test"
        })
        assert r.status_code == 200
        d = r.json()
        job_id = d["id"]
        assert job_id

        # 验证存在
        lr = _get("/api/cron")
        assert lr.status_code == 200
        jobs = lr.json()["jobs"]
        assert any(j["id"] == job_id for j in jobs), f"Job {job_id} should be in list"

        # 删除
        dr = _delete(f"/api/cron/{job_id}")
        assert dr.status_code == 200

        # 验证已删除
        lr2 = _get("/api/cron")
        jobs2 = lr2.json()["jobs"]
        assert not any(j["id"] == job_id for j in jobs2), f"Job {job_id} should be deleted"


# ═══════════════════════ 4. JWT 认证 ═══════════════════════


class TestJWTAuth:
    """JWT 认证完整流程。"""

    def test_register_login_validate(self):
        """注册 → 登录 → JWT 验证 → 错误密码 401。"""
        uid = f"e2e_user_{int(time.time())}"
        pwd = "securepass_e2e_123"

        # 注册
        r = _post("/api/auth/register", json={"user_id": uid, "password": pwd})
        assert r.status_code == 200
        d = r.json()
        assert "token" in d
        token = d["token"]
        assert len(token) > 20

        # 验证 JWT
        r2 = _get("/api/auth/validate", params={"token": token})
        assert r2.status_code == 200
        assert r2.json()["valid"] is True
        assert r2.json()["user_id"] == uid

        # 正确密码登录
        r3 = _post("/api/auth/login", json={"user_id": uid, "password": pwd})
        assert r3.status_code == 200
        assert "token" in r3.json()

        # 错误密码应失败
        r4 = _post("/api/auth/login", json={"user_id": uid, "password": "wrongpassword"})
        assert r4.status_code in (401, 200)
        if r4.status_code == 200:
            assert r4.json().get("error") or not r4.json().get("token")

    def test_auth_stats(self):
        """认证统计 API。"""
        r = _get("/api/auth/stats")
        assert r.status_code == 200
        d = r.json()
        assert "total_users" in d


# ═══════════════════════ 5. 插件 Toggle + 热加载 ═══════════════════════


class TestPluginToggle:
    """插件禁用/启用 + 热加载完整流程。"""

    def test_plugin_disable_enable_cycle(self):
        """禁用 notes 插件 → 验证 → 重新启用 → 验证。"""
        # 获取初始状态
        r0 = _get("/api/plugins")
        assert r0.status_code == 200
        plugins = r0.json()["plugins"]
        notes = next((p for p in plugins if p["name"] == "notes"), None)
        if not notes:
            pytest.skip("notes 插件不存在")

        # 禁用
        r1 = _put("/api/plugins/notes/toggle", json={"enabled": False})
        assert r1.status_code == 200
        assert "禁用" in r1.json().get("message", "")

        # 验证已禁用
        r2 = _get("/api/plugins")
        notes2 = next(p for p in r2.json()["plugins"] if p["name"] == "notes")
        assert notes2["status"] in ("disabled", "unloaded")

        # 重新启用
        r3 = _put("/api/plugins/notes/toggle", json={"enabled": True})
        assert r3.status_code == 200
        assert "启用" in r3.json().get("message", "")

        # 验证已启用
        r4 = _get("/api/plugins")
        notes4 = next(p for p in r4.json()["plugins"] if p["name"] == "notes")
        assert notes4["status"] in ("running", "loaded")

    def test_hot_reload_preserves_tools(self):
        """热加载后工具列表不为空。"""
        r = _post("/api/plugins/reload")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "ok"
        assert d["plugins"] > 0
        assert d["tools"] > 0

    def test_plugin_fields_complete(self):
        """所有插件包含必需字段。"""
        r = _get("/api/plugins")
        for p in r.json()["plugins"]:
            assert "name" in p
            assert "version" in p
            assert "status" in p
            assert "tools" in p

    def test_pluginhub_search(self):
        """PluginHub 搜索返回结果。"""
        r = _get("/api/plugins/hub/search?q=weather")
        assert r.status_code == 200
        d = r.json()
        assert "results" in d


# ═══════════════════════ 6. MCP CRUD ═══════════════════════


class TestMCPServerCRUD:
    """MCP Server 完整 CRUD 生命周期。"""

    def test_mcp_add_verify_delete(self):
        """添加 MCP Server → 验证存在 → 删除 → 验证已删除。"""
        name = f"e2e_mcp_{int(time.time())}"

        # 添加
        r1 = _post("/api/mcp/servers", json={
            "name": name,
            "transport": "http",
            "url": "http://localhost:19999",
            "enabled": False,
        })
        assert r1.status_code == 200
        assert r1.json()["status"] == "ok"

        # 验证存在
        r2 = _get("/api/mcp/servers")
        names = [s["name"] for s in r2.json()["servers"]]
        assert name in names, f"{name} should be in server list"

        # 删除
        r3 = _delete(f"/api/mcp/servers/{name}")
        assert r3.status_code == 200

        # 验证已删除
        r4 = _get("/api/mcp/servers")
        names2 = [s["name"] for s in r4.json()["servers"]]
        assert name not in names2, f"{name} should be deleted"

    def test_mcp_discover(self):
        """MCP Discover 返回工具数。"""
        r = _post("/api/mcp/discover")
        assert r.status_code == 200
        d = r.json()
        assert "tools_discovered" in d

    def test_mcp_tools_list(self):
        """MCP 工具列表返回数据。"""
        r = _get("/api/mcp/tools")
        assert r.status_code == 200
        d = r.json()
        assert "tools" in d
        assert isinstance(d["tools"], list)

    def test_mcp_health(self):
        """MCP 健康检查。"""
        r = _get("/api/mcp/health")
        assert r.status_code == 200

    def test_mcp_update_server(self):
        """添加 → 更新 env/enabled → 验证 → 删除。"""
        name = f"e2e_mcp_upd_{int(time.time())}"
        # 添加
        r1 = _post("/api/mcp/servers", json={
            "name": name, "transport": "http",
            "url": "http://localhost:29999", "enabled": False,
        })
        assert r1.status_code == 200
        # 更新
        r2 = _put(f"/api/mcp/servers/{name}", json={
            "env": {"MY_KEY": "test123"}, "enabled": True,
        })
        assert r2.status_code == 200
        srv = r2.json().get("server", {})
        assert srv.get("enabled") is True
        assert srv.get("env", {}).get("MY_KEY") == "test123"
        # 清理
        _delete(f"/api/mcp/servers/{name}")

    def test_mcp_add_reject_unsafe_command(self):
        """安全验证：拒绝 shell 注入的 stdio 命令。"""
        r = _post("/api/mcp/servers", json={
            "name": "evil_test", "transport": "stdio",
            "command": "npx", "args": ["-y", "pkg; rm -rf /"],
        })
        assert r.status_code == 400
        assert "shell" in r.json().get("detail", "").lower()

    def test_mcp_add_reject_protected_env(self):
        """安全验证：拒绝覆盖 PATH 等受保护变量。"""
        r = _post("/api/mcp/servers", json={
            "name": "env_test", "transport": "stdio",
            "command": "npx", "args": [], "env": {"PATH": "/evil"},
        })
        assert r.status_code == 400
        assert "PATH" in r.json().get("detail", "")

    def test_mcp_delete_nonexistent(self):
        """删除不存在的 MCP Server 返回 404。"""
        r = _delete("/api/mcp/servers/nonexistent_server_xyz")
        assert r.status_code == 404


# ═══════════════════════ 7. 会话完整 CRUD ═══════════════════════


class TestSessionsCRUD:
    """会话管理完整 CRUD。"""

    def test_session_create_history_rename_delete(self):
        """创建 → 发消息 → 查历史 → 重命名 → 删除。"""
        # 创建
        r1 = _post("/api/sessions", json={})
        assert r1.status_code == 200
        d = r1.json()
        sid = d.get("session_id") or d.get("id") or d.get("session", {}).get("id")
        assert sid

        # 查历史（应为空或仅有系统消息）
        r2 = _get(f"/api/sessions/{sid}/history")
        assert r2.status_code == 200

        # 重命名
        r3 = _put(f"/api/sessions/{sid}/title", json={"title": "E2E Test Session"})
        assert r3.status_code == 200

        # 验证重命名
        r4 = _get("/api/sessions")
        sessions = r4.json()["sessions"]
        target = next((s for s in sessions if s.get("id") == sid), None)
        if target:
            assert target.get("title") == "E2E Test Session" or target.get("name") == "E2E Test Session"

        # 删除
        r5 = _delete(f"/api/sessions/{sid}")
        assert r5.status_code == 200

        # 验证已删除
        r6 = _get("/api/sessions")
        sids = [s.get("id") for s in r6.json()["sessions"]]
        assert sid not in sids


# ═══════════════════════ 8. 安全配置完整 ═══════════════════════


class TestSecurityConfig:
    """安全配置 CRUD。"""

    def test_security_toggle(self):
        """安全审批开关切换。"""
        # 获取当前状态
        r0 = _get("/api/security/config")
        assert r0.status_code == 200
        was_enabled = r0.json().get("enabled", True)

        # 切换
        r1 = _post("/api/security/toggle", json={"enabled": not was_enabled})
        assert r1.status_code == 200

        # 切换回
        r2 = _post("/api/security/toggle", json={"enabled": was_enabled})
        assert r2.status_code == 200

    def test_dangerous_tools_list(self):
        """危险工具列表。"""
        r = _get("/api/security/dangerous-tools")
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d.get("tools", []), list)

    def test_classify_tool(self):
        """工具分类 API。"""
        r = _post("/api/security/classify", json={"tool_name": "run_command", "level": "dangerous"})
        assert r.status_code == 200


# ═══════════════════════ 9. Brain 生命周期 ═══════════════════════


class TestBrainLifecycle:
    """Brain 唤醒/休眠/暂停/恢复完整生命周期。"""

    def test_brain_full_status(self):
        """Brain 完整状态包含所有字段。"""
        r = _get("/api/brain/status")
        assert r.status_code == 200
        d = r.json()
        assert "awake" in d
        assert "daemon" in d
        assert d["awake"] is True
        daemon = d["daemon"]
        assert "running" in daemon
        assert "paused" in daemon

    def test_brain_pause_resume(self):
        """暂停 → 验证暂停 → 恢复 → 验证恢复。"""
        # 暂停
        r1 = _post("/api/brain/pause")
        assert r1.status_code == 200

        # 验证暂停
        r2 = _get("/api/brain/status")
        assert r2.json()["daemon"]["paused"] is True

        # 恢复
        r3 = _post("/api/brain/resume")
        assert r3.status_code == 200

        # 验证恢复
        r4 = _get("/api/brain/status")
        assert r4.json()["daemon"]["paused"] is False

    def test_brain_goals(self):
        """Brain 目标读取。"""
        r = _get("/api/brain/goals")
        assert r.status_code == 200

    def test_brain_thoughts(self):
        """Brain 思考历史。"""
        r = _get("/api/brain/thoughts")
        assert r.status_code == 200

    def test_brain_soul_history(self):
        """灵魂进化历史。"""
        r = _get("/api/brain/soul/history")
        assert r.status_code == 200


# ═══════════════════════ 10. 数据一致性 ═══════════════════════


class TestDataConsistency:
    """数据读写一致性验证。"""

    def test_user_profile_write_read(self):
        """画像写入后读取一致。"""
        marker = f"e2e_marker_{int(time.time())}"
        # 读取当前画像
        r0 = _get("/api/user-profile")
        original = r0.json().get("profile", "")

        # 写入带标记的画像
        new_profile = f"{original}\n{marker}"
        r1 = _put("/api/user-profile", json={"content": new_profile})
        assert r1.status_code == 200

        # 读取验证
        r2 = _get("/api/user-profile")
        d2 = r2.json()
        actual = d2.get("content", d2.get("profile", ""))
        assert marker in actual

        # 恢复原始
        _put("/api/user-profile", json={"content": original})

    def test_lessons_count_consistent(self):
        """经验列表 count 字段与实际数量一致。"""
        r = _get("/api/lessons")
        assert r.status_code == 200
        d = r.json()
        assert d["count"] == len(d["lessons"])

    def test_channel_status_four_channels(self):
        """通道状态应包含 4 个通道。"""
        r = _get("/api/channel/status")
        assert r.status_code == 200
        channels = r.json()["channels"]
        assert len(channels) == 4
        names = {c["name"] for c in channels}
        assert names == {"telegram", "feishu", "wecom", "wechat"}

    def test_diagnostics_summary(self):
        """诊断摘要字段完整。"""
        r = _get("/api/diagnostics/summary")
        assert r.status_code == 200
        d = r.json()
        assert "total" in d

    def test_status_tools_match_plugins(self):
        """系统状态工具列表应非空且与插件一致。"""
        r_status = _get("/api/status")
        r_plugins = _get("/api/plugins")
        tools = r_status.json()["tools"]
        plugins = r_plugins.json()["plugins"]

        # 至少应有一些工具
        assert len(tools) >= 10, f"工具数应 >= 10，实际: {len(tools)}"

        # 所有 running 插件的工具应在系统工具列表中
        running_plugin_tools = []
        for p in plugins:
            if p["status"] == "running":
                running_plugin_tools.extend(p.get("tools", []))

        for tool_name in running_plugin_tools:
            assert tool_name in tools, f"插件工具 {tool_name} 应在系统工具列表中"
