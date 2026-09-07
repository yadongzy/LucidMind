"""S59 真实端到端测试：心跳/排队/上传/Cron/异步任务/WebSocket对话。"""
import asyncio
import io
import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import requests

BASE = "http://127.0.0.1:8765"


def _login():
    # 先尝试注册（首次），再登录
    requests.post(f"{BASE}/api/auth/register",
                  json={"user_id": "yadong", "password": "yadong123"}, timeout=10)
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"user_id": "yadong", "password": "yadong123"}, timeout=10)
    return r.json().get("token", "")


def test_login():
    token = _login()
    assert token, "Login failed"


def test_cron_api():
    r = requests.get(f"{BASE}/api/cron", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert "jobs" in data


def test_tasks_api():
    r = requests.get(f"{BASE}/api/tasks", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert "tasks" in data


def test_upload_file():
    files = {"file": ("test.txt", io.BytesIO(b"hello world"), "text/plain")}
    r = requests.post(f"{BASE}/api/upload", files=files, timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert data["filename"] == "test.txt"
    assert data["size"] == 11
    assert data["kind"] == "document"


def test_upload_image():
    # 1x1 PNG
    png = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
           b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00'
           b'\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00'
           b'\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82')
    files = {"file": ("test.png", io.BytesIO(png), "image/png")}
    r = requests.post(f"{BASE}/api/upload", files=files, timeout=10)
    assert r.status_code == 200
    assert r.json()["kind"] == "image"


def test_upload_audio():
    files = {"file": ("test.mp3", io.BytesIO(b"\xff\xfb\x90\x00" * 10), "audio/mpeg")}
    r = requests.post(f"{BASE}/api/upload", files=files, timeout=10)
    assert r.status_code == 200
    assert r.json()["kind"] == "audio"


def test_heartbeat_pong():
    """心跳pong返回Brain状态。"""
    token = _login()
    import websockets

    async def _test():
        uri = f"ws://127.0.0.1:8765/ws?token={token}"
        async with websockets.connect(uri, ping_interval=None) as ws:
            await ws.send(json.dumps({"type": "ping"}))
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
            data = json.loads(raw)
            assert data["type"] == "pong"
            assert "ts" in data
            assert "brain" in data  # S59: Brain状态
            assert "queue" in data  # S59: 队列长度

    asyncio.get_event_loop().run_until_complete(_test())


def test_chat_e2e():
    """真实WebSocket对话：发消息→收到回复→收到complete。"""
    token = _login()
    import websockets

    async def _test():
        uri = f"ws://127.0.0.1:8765/ws?token={token}"
        async with websockets.connect(uri, ping_interval=None) as ws:
            await ws.send(json.dumps({
                "type": "chat", "message": "3+4=?", "session_id": "e2e_s59"
            }))
            got_resp = False
            got_done = False
            t0 = time.time()
            while time.time() - t0 < 30:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=15)
                    d = json.loads(raw)
                    if d["type"] in ("response", "response_delta"):
                        got_resp = True
                    elif d["type"] == "complete":
                        got_done = True
                        break
                except asyncio.TimeoutError:
                    break
            assert got_resp, "No response received"
            assert got_done, "No complete received"

    asyncio.get_event_loop().run_until_complete(_test())


def test_frontend_features():
    """前端包含所有S59功能。"""
    r = requests.get(f"{BASE}/static/chat_enhance.js", timeout=10)
    assert r.status_code == 200
    js = r.text
    assert "initDragDropUpload" in js
    assert "initTaskPanel" in js
    assert "initCronPanel" in js
    assert "initQueueIndicator" in js
    assert "initStopButton" in js
    assert "initTextareaEnhance" in js
    assert "initReconnectBanner" in js


def test_cron_create_delete():
    """Cron创建和删除。"""
    r = requests.post(f"{BASE}/api/cron", json={
        "description": "test job",
        "interval_seconds": 60,
        "command": "echo test"
    }, timeout=10)
    assert r.status_code == 200
    job_id = r.json()["id"]

    # Verify it exists
    lr = requests.get(f"{BASE}/api/cron", timeout=10)
    assert any(j["id"] == job_id for j in lr.json()["jobs"])

    # Delete
    dr = requests.delete(f"{BASE}/api/cron/{job_id}", timeout=10)
    assert dr.status_code == 200

    # Verify deleted
    lr2 = requests.get(f"{BASE}/api/cron", timeout=10)
    assert not any(j["id"] == job_id for j in lr2.json()["jobs"])
