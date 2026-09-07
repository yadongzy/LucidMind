"""S49-S57 测试：闭环认证 + 前端体验 + 智能深化。

T1: S49 console.js JWT守卫（检查文件内容）
T2: S50 WebSocket传token（channel adapter有_resolve_user）
T3: S51 登出按钮+用户标识（console.html有logout-btn）
T4: S52 会话搜索框（chat_enhance.js有session-search）
T5: S53 消息搜索+导出（chat_enhance.js有msg-search+export-btn）
T6: S54 移动端适配（chat_enhance.js有@media max-width）
T7: S55 MCP客户端模块可导入
T8: S56 用户画像模块可导入+基本操作
T9: S57 任务追踪器模块可导入+基本操作
T10: 认证API完整流程（需服务器运行）
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest


def test_t1_console_jwt_guard():
    """T1: S49 console.js 包含JWT认证守卫。"""
    js = open("frontend/console.js", encoding="utf-8").read()
    assert "lucidmind_token" in js
    assert "/login" in js
    assert "authToken" in js


def test_t2_ws_token_resolve():
    """T2: S50 WebSocket channel 有token解析。"""
    from adapters.channel.websocket_channel import WebSocketChannelAdapter
    ch = WebSocketChannelAdapter()
    assert hasattr(ch, "_resolve_user")
    assert hasattr(ch, "_isolate_sid")
    # anonymous for empty token
    assert ch._resolve_user("") == "anonymous"


def test_t3_logout_button():
    """T3: S51 console.html 有登出按钮和用户标识。"""
    html = open("frontend/console.html", encoding="utf-8").read()
    assert "logout-btn" in html
    assert "user-badge" in html
    js = open("frontend/console.js", encoding="utf-8").read()
    assert "logout-btn" in js
    assert "removeItem" in js


def test_t4_session_search():
    """T4: S52 chat_enhance.js 有会话搜索。"""
    js = open("frontend/chat_enhance.js", encoding="utf-8").read()
    assert "session-search" in js
    assert "搜索会话" in js


def test_t5_msg_search_export():
    """T5: S53 消息搜索+导出。"""
    js = open("frontend/chat_enhance.js", encoding="utf-8").read()
    assert "msg-search" in js
    assert "export-btn" in js
    assert "导出对话" in js
    assert "text/markdown" in js


def test_t6_mobile_adapt():
    """T6: S54 移动端适配。"""
    js = open("frontend/chat_enhance.js", encoding="utf-8").read()
    assert "max-width: 768px" in js
    assert "isMobile" in js


def test_t7_mcp_client():
    """T7: S55 MCP客户端模块可导入+核心方法存在。"""
    from adapters.tools.mcp_client import MCPClientAdapter
    client = MCPClientAdapter()
    assert hasattr(client, "discover")
    assert hasattr(client, "execute")
    assert client.list_tools() == []


def test_t8_user_profile():
    """T8: S56 用户画像模块可导入+基本操作。"""
    from adapters.memory.user_profile import UserProfileAdapter
    adapter = UserProfileAdapter()
    # 获取不存在的用户
    profile = adapter.get_profile("test_nonexist")
    assert profile["user_id"] == "test_nonexist"
    assert profile["preferences"] == {}
    # 更新偏好
    adapter.update_preference("test_unit", "language", "zh-CN")
    p = adapter.get_profile("test_unit")
    assert p["preferences"]["language"] == "zh-CN"
    # 添加事实
    adapter.add_fact("test_unit", "喜欢Python")
    p2 = adapter.get_profile("test_unit")
    assert "喜欢Python" in p2["facts"]
    # 上下文提示
    ctx = adapter.get_context_prompt("test_unit")
    assert "language=zh-CN" in ctx
    assert "喜欢Python" in ctx
    # 清理
    import pathlib
    pathlib.Path(adapter._path("test_unit")).unlink(missing_ok=True)


def test_t9_task_tracker():
    """T9: S57 任务追踪器模块可导入+基本操作。"""
    from adapters.planner.task_tracker import TaskTracker
    tracker = TaskTracker()
    sid = f"test_tracker_{int(time.time())}"
    # 保存计划
    plan = {
        "goal": "测试任务",
        "status": "active",
        "steps": [
            {"id": 1, "desc": "步骤1", "tool": "", "status": "running", "result": "", "error": ""},
            {"id": 2, "desc": "步骤2", "tool": "web_search", "status": "pending", "result": "", "error": ""},
        ]
    }
    tracker.save_plan(sid, plan)
    loaded = tracker.load_plan(sid)
    assert loaded is not None
    assert loaded["goal"] == "测试任务"
    # 推进步骤
    updated = tracker.advance_step(sid, 1, result="步骤1完成")
    assert updated["steps"][0]["status"] == "done"
    assert updated["steps"][1]["status"] == "running"
    # 上下文
    ctx = tracker.get_current_step_context(sid)
    assert "步骤2" in ctx
    assert "任务追踪" in ctx
    # 完成
    tracker.advance_step(sid, 2, result="步骤2完成")
    final = tracker.load_plan(sid)
    assert final is None  # completed plans return None
    # 清理
    import pathlib
    pathlib.Path(tracker._path(sid)).unlink(missing_ok=True)


def test_t10_auth_flow():
    """T10: 认证API完整流程（需服务器运行）。"""
    import requests
    BASE = "http://127.0.0.1:8765"
    uid = f"s49test_{int(time.time())}"
    # 注册
    r = requests.post(f"{BASE}/api/auth/register",
                      json={"user_id": uid, "password": "pass123"}, timeout=10)
    assert r.status_code == 200
    token = r.json()["token"]
    # 验证
    r2 = requests.get(f"{BASE}/api/auth/validate",
                      params={"token": token}, timeout=10)
    assert r2.json()["valid"] is True
    # 隔离session
    r3 = requests.get(f"{BASE}/api/auth/session",
                      params={"token": token, "session_id": "chat1"}, timeout=10)
    assert "u_" in r3.json()["isolated_session_id"]
    # 登录页
    r4 = requests.get(f"{BASE}/login", timeout=10)
    assert r4.status_code == 200
    assert "logout-btn" not in r4.text  # login page, not console
    # console页有logout
    # (不直接测console因为需要token，但检查静态文件)
    r5 = requests.get(f"{BASE}/static/console.js", timeout=10)
    assert r5.status_code == 200
    assert "lucidmind_token" in r5.text
