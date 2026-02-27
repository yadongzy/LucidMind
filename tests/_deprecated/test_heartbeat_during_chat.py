"""S59 关键测试：AI回复期间心跳是否正常响应（不阻塞）。
模拟浏览器行为：发消息 → 同时发ping → 验证pong正常返回。
"""
import asyncio
import json
import time
import requests
import websockets

BASE = "http://127.0.0.1:8765"


async def main():
    # 登录
    requests.post(f"{BASE}/api/auth/register",
                  json={"user_id": "hb_test", "password": "test123"}, timeout=10)
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"user_id": "hb_test", "password": "test123"}, timeout=10)
    token = r.json().get("token", "")
    assert token, "Login failed"

    uri = f"ws://127.0.0.1:8765/ws?token={token}"
    async with websockets.connect(uri) as ws:
        # 发一条需要AI处理的消息（会耗时3-5秒）
        await ws.send(json.dumps({
            "type": "chat",
            "message": "Please explain what is quantum computing in 3 sentences.",
            "session_id": "hb_test"
        }))
        print(f"[{time.strftime('%H:%M:%S')}] Sent chat message")

        # 等1秒后发ping（此时Brain应该还在处理中）
        await asyncio.sleep(1.0)
        await ws.send(json.dumps({"type": "ping"}))
        print(f"[{time.strftime('%H:%M:%S')}] Sent ping during AI processing")

        # 收集所有消息，看ping是否被及时响应
        got_pong = False
        pong_time = None
        got_complete = False
        reply = ""
        ping_sent_at = time.time()

        while time.time() - ping_sent_at < 30:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=15)
                d = json.loads(raw)
                etype = d.get("type", "")

                if etype == "pong":
                    got_pong = True
                    pong_time = time.time() - ping_sent_at
                    print(f"[{time.strftime('%H:%M:%S')}] Got PONG! latency={pong_time:.2f}s brain={d.get('brain')}")
                elif etype in ("response", "response_delta"):
                    reply += str(d.get("data", ""))
                elif etype == "complete":
                    got_complete = True
                    print(f"[{time.strftime('%H:%M:%S')}] Got COMPLETE")
                    break
                elif etype == "thinking":
                    print(f"[{time.strftime('%H:%M:%S')}] Got thinking event")
                elif etype == "error":
                    print(f"[{time.strftime('%H:%M:%S')}] ERROR: {d.get('data')}")
            except asyncio.TimeoutError:
                break

        print(f"\n=== RESULTS ===")
        print(f"Pong received: {got_pong}")
        if pong_time:
            print(f"Pong latency: {pong_time:.2f}s (should be < 1s)")
        print(f"Complete received: {got_complete}")
        print(f"Reply: {reply[:100]}")

        # 关键断言
        assert got_pong, "FAIL: No pong during AI processing - heartbeat blocked!"
        assert pong_time < 2.0, f"FAIL: Pong too slow ({pong_time:.2f}s) - still blocking!"
        assert got_complete, "FAIL: No complete event"
        print("\nPASS: Heartbeat works during AI processing!")


if __name__ == "__main__":
    asyncio.run(main())
