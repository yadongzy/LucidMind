"""S59 真实操作测试 — 模拟用户完整操作流程。
所有websockets连接禁用库级keepalive，避免Brain处理期间超时断连。
"""
import asyncio
import io
import json
import time
import requests
import websockets

BASE = "http://127.0.0.1:8765"
RESULTS = []
WS_OPTS = {"ping_interval": None, "ping_timeout": None}


def record(name, input_desc, output_desc, elapsed, passed):
    status = "PASS" if passed else "FAIL"
    RESULTS.append({"name": name, "input": input_desc, "output": output_desc,
                     "elapsed": f"{elapsed:.2f}s", "status": status})
    print(f"  [{status}] {name} ({elapsed:.2f}s)")
    if not passed:
        print(f"       output: {output_desc}")


async def main():
    print("=" * 60)
    print("LucidMind S59 Real Operation Test")
    print("=" * 60)

    # === 1: Login ===
    print("\n--- 1: Login ---")
    t0 = time.time()
    try:
        requests.post(f"{BASE}/api/auth/register",
                      json={"user_id": "test_real", "password": "test123"}, timeout=10)
        r = requests.post(f"{BASE}/api/auth/login",
                          json={"user_id": "test_real", "password": "test123"}, timeout=10)
        token = r.json().get("token", "")
        record("Login", "user_id=test_real", f"token={token[:30]}...", time.time() - t0, bool(token))
    except Exception as e:
        record("Login", "register+login", str(e), time.time() - t0, False)
        return False

    uri = f"ws://127.0.0.1:8765/ws?token={token}"

    # === 2: Heartbeat ===
    print("\n--- 2: Heartbeat ---")
    async with websockets.connect(uri, **WS_OPTS) as ws:
        t0 = time.time()
        await ws.send(json.dumps({"type": "ping"}))
        raw = await asyncio.wait_for(ws.recv(), timeout=10)
        pong = json.loads(raw)
        has_brain = "brain" in pong and "queue" in pong
        record("Heartbeat pong", "send ping",
               f"type={pong.get('type')}, brain={pong.get('brain')}, queue={pong.get('queue')}",
               time.time() - t0, pong.get("type") == "pong" and has_brain)

    # === 3: Chat simple ===
    print("\n--- 3: Chat (simple) ---")
    async with websockets.connect(uri, **WS_OPTS) as ws:
        t0 = time.time()
        await ws.send(json.dumps({"type": "chat", "message": "3+4=?", "session_id": "real_test"}))
        reply = ""
        got_complete = False
        while time.time() - t0 < 45:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=30)
                d = json.loads(raw)
                if d.get("type") in ("response", "response_delta"):
                    reply += str(d.get("data", ""))
                elif d.get("type") == "complete":
                    got_complete = True
                    break
            except asyncio.TimeoutError:
                break
        has_7 = "7" in reply
        record("Chat:math", "3+4=?", f"reply={reply[:60]} | has_7={has_7}",
               time.time() - t0, got_complete and has_7)

    # === 4: Queue (2 messages) ===
    print("\n--- 4: Queue ---")
    async with websockets.connect(uri, **WS_OPTS) as ws:
        t0 = time.time()
        await ws.send(json.dumps({"type": "chat", "message": "1+1=?", "session_id": "real_test"}))
        await asyncio.sleep(0.1)
        await ws.send(json.dumps({"type": "chat", "message": "2+2=?", "session_id": "real_test"}))
        completes = 0
        replies = []
        cur = ""
        while time.time() - t0 < 90:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=30)
                d = json.loads(raw)
                if d.get("type") in ("response", "response_delta"):
                    cur += str(d.get("data", ""))
                elif d.get("type") == "complete":
                    completes += 1
                    replies.append(cur)
                    cur = ""
                    if completes >= 2:
                        break
            except asyncio.TimeoutError:
                break
        r1 = replies[0][:40] if replies else "N/A"
        r2 = replies[1][:40] if len(replies) > 1 else "N/A"
        record("Queue", "send '1+1' then '2+2'",
               f"{completes}/2 complete | r1={r1} | r2={r2}",
               time.time() - t0, completes >= 2)

    # === 5-7: File uploads ===
    print("\n--- 5: Upload text ---")
    t0 = time.time()
    files = {"file": ("report.txt", io.BytesIO(b"Test report content."), "text/plain")}
    r = requests.post(f"{BASE}/api/upload", files=files, timeout=10)
    d = r.json()
    record("Upload:text", "report.txt", f"kind={d.get('kind')}, size={d.get('size')}",
           time.time() - t0, r.status_code == 200 and d.get("kind") == "document")

    print("\n--- 6: Upload image ---")
    t0 = time.time()
    png = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
           b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00'
           b'\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00'
           b'\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82')
    files = {"file": ("photo.png", io.BytesIO(png), "image/png")}
    r = requests.post(f"{BASE}/api/upload", files=files, timeout=10)
    record("Upload:image", "photo.png", f"kind={r.json().get('kind')}",
           time.time() - t0, r.status_code == 200 and r.json().get("kind") == "image")

    print("\n--- 7: Upload audio ---")
    t0 = time.time()
    files = {"file": ("voice.mp3", io.BytesIO(b"\xff\xfb\x90\x00" * 100), "audio/mpeg")}
    r = requests.post(f"{BASE}/api/upload", files=files, timeout=10)
    record("Upload:audio", "voice.mp3", f"kind={r.json().get('kind')}",
           time.time() - t0, r.status_code == 200 and r.json().get("kind") == "audio")

    # === 8: Cron CRUD ===
    print("\n--- 8: Cron CRUD ---")
    t0 = time.time()
    r = requests.post(f"{BASE}/api/cron", json={
        "description": "test job", "interval_seconds": 60, "command": "echo test"
    }, timeout=10)
    job_id = r.json().get("id", "")
    lr = requests.get(f"{BASE}/api/cron", timeout=10)
    found = any(j["id"] == job_id for j in lr.json().get("jobs", []))
    dr = requests.delete(f"{BASE}/api/cron/{job_id}", timeout=10)
    lr2 = requests.get(f"{BASE}/api/cron", timeout=10)
    gone = not any(j["id"] == job_id for j in lr2.json().get("jobs", []))
    record("Cron CRUD", "create->list->delete->verify",
           f"id={job_id}, found={found}, gone={gone}",
           time.time() - t0, found and gone)

    # === 9: Tasks API ===
    print("\n--- 9: Tasks API ---")
    t0 = time.time()
    r = requests.get(f"{BASE}/api/tasks", timeout=10)
    record("Tasks API", "GET /api/tasks", f"status={r.status_code}",
           time.time() - t0, r.status_code == 200 and "tasks" in r.json())

    # === 10: Frontend features ===
    print("\n--- 10: Frontend features ---")
    t0 = time.time()
    js = requests.get(f"{BASE}/static/chat_enhance.js", timeout=10).text
    features = {
        "QueueIndicator": "initQueueIndicator" in js,
        "DragDrop": "initDragDropUpload" in js,
        "TaskPanel": "initTaskPanel" in js,
        "CronPanel": "initCronPanel" in js,
        "ClickablePaths": "initClickablePaths" in js,
        "StopButton": "initStopButton" in js,
    }
    all_ok = all(features.values())
    record("Frontend", "check chat_enhance.js",
           " | ".join(f"{k}:{'OK' if v else 'MISS'}" for k, v in features.items()),
           time.time() - t0, all_ok)

    # === Summary ===
    print("\n" + "=" * 60)
    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    total = len(RESULTS)
    for r in RESULTS:
        print(f"  [{r['status']}] {r['name']} ({r['elapsed']})")
    print(f"\nTotal: {passed}/{total}")
    print("ALL PASSED!" if passed == total else "SOME FAILED!")
    return passed == total

if __name__ == "__main__":
    ok = asyncio.run(main())
    exit(0 if ok else 1)
