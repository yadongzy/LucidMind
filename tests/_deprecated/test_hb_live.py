"""Test: heartbeat pong during AI processing."""
import asyncio
import json
import time
import requests
import websockets

BASE = "http://127.0.0.1:8765"

async def main():
    requests.post(f"{BASE}/api/auth/register",
                  json={"user_id": "hb3", "password": "t123"}, timeout=10)
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"user_id": "hb3", "password": "t123"}, timeout=10)
    token = r.json().get("token", "")
    assert token, "Login failed"

    uri = f"ws://127.0.0.1:8765/ws?token={token}"
    async with websockets.connect(uri) as ws:
        # Send chat message (will take 3-5s to process)
        await ws.send(json.dumps({
            "type": "chat", "message": "hi", "session_id": "hb3"
        }))
        print("Sent chat message")

        # Wait 1.5s then send ping while Brain is processing
        await asyncio.sleep(1.5)
        await ws.send(json.dumps({"type": "ping"}))
        ping_time = time.time()
        print("Sent ping during processing")

        got_pong = False
        pong_latency = None
        got_complete = False
        errors = []

        while time.time() - ping_time < 45:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=30)
                d = json.loads(raw)
                etype = d.get("type", "")

                if etype == "pong":
                    got_pong = True
                    pong_latency = time.time() - ping_time
                    print(f"  PONG received! latency={pong_latency:.2f}s")
                elif etype == "complete":
                    got_complete = True
                    print("  COMPLETE received")
                    if got_pong:
                        break
                elif etype == "error":
                    errors.append(str(d.get("data", ""))[:80])
                    print(f"  ERROR: {errors[-1]}")
                elif etype == "thinking":
                    print("  thinking event")
                elif etype in ("response", "response_delta"):
                    pass  # normal
                elif etype == "info":
                    pass
            except asyncio.TimeoutError:
                print("  Timeout waiting")
                break

        print(f"\nResults:")
        print(f"  Pong: {got_pong} (latency: {pong_latency})")
        print(f"  Complete: {got_complete}")
        print(f"  Errors: {errors}")

        if got_pong:
            print("PASS: Heartbeat works during AI processing")
        else:
            print("FAIL: Heartbeat blocked during AI processing")

        return got_pong

if __name__ == "__main__":
    ok = asyncio.run(main())
    exit(0 if ok else 1)
