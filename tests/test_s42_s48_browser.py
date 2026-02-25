"""S42-S48 浏览器真实测试。

T1: S42 对话规划器 — 复杂任务触发规划
T2: S43 记忆摘要 — 模块可导入+压缩逻辑
T3: S44 自我评估 — 模块可导入+评估逻辑
T4: S45 JWT认证 — 注册→登录→验证→错误密码401
T5: S46 登录页 — 页面可访问+表单存在
T6: S48 性能 — health API < 500ms
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
import requests

BASE = "http://127.0.0.1:8765"


def test_t1_planner_module():
    """T1: S42 对话规划器模块可导入+核心函数存在。"""
    from planner import TaskPlan, TaskStep, create_plan, format_plan_for_stream
    step = TaskStep(1, "搜索天气", "web_search")
    plan = TaskPlan("测试任务", [step])
    assert plan.progress == "0/1"
    assert step.status == "pending"
    text = format_plan_for_stream(plan)
    assert "任务规划" in text
    assert "搜索天气" in text


def test_t2_summarizer_module():
    """T2: S43 记忆摘要模块可导入+压缩阈值正确。"""
    from adapters.memory.summarizer import (
        _COMPRESS_THRESHOLD, _KEEP_RECENT, get_summaries
    )
    assert _COMPRESS_THRESHOLD == 40
    assert _KEEP_RECENT == 15
    # 空会话无摘要
    result = get_summaries("nonexistent_session")
    assert result == []


def test_t3_self_eval_module():
    """T3: S44 自我评估模块可导入+空输入处理。"""
    import asyncio
    from self_eval import evaluate_reply
    # 空回复应返回 score=0
    result = asyncio.get_event_loop().run_until_complete(
        evaluate_reply("test", "", None)
    )
    assert result["score"] == 0
    assert result["should_learn"] is False


def test_t4_jwt_auth():
    """T4: S45 JWT认证完整流程。"""
    uid = f"testuser_{int(time.time())}"
    pwd = "securepass123"

    # 注册
    r = requests.post(f"{BASE}/api/auth/register",
                      json={"user_id": uid, "password": pwd}, timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert "token" in data
    token = data["token"]
    assert len(token) > 20  # JWT 格式

    # 验证 JWT
    r2 = requests.get(f"{BASE}/api/auth/validate",
                      params={"token": token}, timeout=10)
    assert r2.status_code == 200
    assert r2.json()["valid"] is True
    assert r2.json()["user_id"] == uid

    # 正确密码登录
    r3 = requests.post(f"{BASE}/api/auth/login",
                       json={"user_id": uid, "password": pwd}, timeout=10)
    assert r3.status_code == 200
    assert "token" in r3.json()

    # 错误密码
    r4 = requests.post(f"{BASE}/api/auth/login",
                       json={"user_id": uid, "password": "wrong"}, timeout=10)
    assert r4.status_code == 401

    # 隔离 session
    r5 = requests.get(f"{BASE}/api/auth/session",
                      params={"token": token, "session_id": "chat1"}, timeout=10)
    assert r5.status_code == 200
    isolated = r5.json()["isolated_session_id"]
    assert uid[:4] not in isolated or "u_" in isolated  # 有前缀隔离


def test_t5_login_page():
    """T5: S46 登录页可访问+关键元素存在。"""
    r = requests.get(f"{BASE}/login", timeout=10)
    assert r.status_code == 200
    html = r.text
    assert "LucidMind" in html
    assert "username" in html
    assert "password" in html
    assert "doLogin" in html
    assert "doRegister" in html


def test_t6_health_performance():
    """T6: S48 性能 — health API 响应 < 500ms。"""
    # 预热
    requests.get(f"{BASE}/api/health", timeout=10)
    # 测量
    times = []
    for _ in range(3):
        t0 = time.time()
        r = requests.get(f"{BASE}/api/health", timeout=10)
        elapsed = (time.time() - t0) * 1000
        times.append(elapsed)
        assert r.status_code == 200
    avg = sum(times) / len(times)
    assert avg < 500, f"health API 平均 {avg:.0f}ms > 500ms"


def test_t7_brain_daemon_actions():
    """T7: Daemon 自主行动验证。"""
    r = requests.get(f"{BASE}/api/brain/status", timeout=10)
    assert r.status_code == 200
    data = r.json()
    daemon = data.get("daemon", {})
    assert daemon.get("running") is True
    assert daemon.get("action_count", 0) >= 1
    assert daemon.get("thought_count", 0) >= 1
