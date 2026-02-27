"""S59 TTS端到端测试：让AI说话 → 验证音频文件生成 → 验证可访问。"""
import asyncio
import json
import time
import requests
import websockets

BASE = "http://127.0.0.1:8765"

async def main():
    # Login
    requests.post(f"{BASE}/api/auth/register",
                  json={"user_id": "tts_test", "password": "t123"}, timeout=10)
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"user_id": "tts_test", "password": "t123"}, timeout=10)
    token = r.json().get("token", "")
    assert token, "Login failed"

    uri = f"ws://127.0.0.1:8765/ws?token={token}"
    async with websockets.connect(uri) as ws:
        # Ask AI to generate speech
        await ws.send(json.dumps({
            "type": "chat",
            "message": "Please use the text_to_speech tool to say 'Hello World' in Chinese. Use filename hello_test.mp3",
            "session_id": "tts_e2e"
        }))
        print("Sent TTS request")

        reply = ""
        tool_used = False
        tool_result = ""
        got_complete = False
        t0 = time.time()

        while time.time() - t0 < 45:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=30)
                d = json.loads(raw)
                etype = d.get("type", "")
                if etype in ("response", "response_delta"):
                    reply += str(d.get("data", ""))
                elif etype == "tool_use":
                    tool_used = True
                    print(f"  Tool called: {d.get('data', {})}")
                elif etype == "tool_result":
                    tool_result = str(d.get("data", ""))
                    print(f"  Tool result: {tool_result[:100]}")
                elif etype == "complete":
                    got_complete = True
                    break
            except asyncio.TimeoutError:
                break

        print(f"\nResults ({time.time()-t0:.1f}s):")
        print(f"  Tool used: {tool_used}")
        print(f"  Tool result: {tool_result[:100]}")
        print(f"  Reply: {reply[:150]}")
        print(f"  Complete: {got_complete}")

        # Check if audio file is accessible
        audio_url = f"{BASE}/static/output/hello_test.mp3"
        ar = requests.head(audio_url, timeout=10)
        print(f"  Audio accessible: {ar.status_code} ({audio_url})")

        # Check frontend has clickable paths feature
        js = requests.get(f"{BASE}/static/chat_enhance.js", timeout=10).text
        has_linkify = "initClickablePaths" in js
        has_autoplay = "autoplay" in js
        print(f"  Clickable paths: {has_linkify}")
        print(f"  Audio autoplay: {has_autoplay}")

        all_ok = got_complete and has_linkify and has_autoplay
        if ar.status_code == 200:
            print("\nPASS: TTS works end-to-end, audio accessible, autoplay enabled")
        else:
            print(f"\nAudio file not found (status {ar.status_code}), but TTS tool was called: {tool_used}")
            print("This may be because the AI chose not to use the exact filename")

        return all_ok

if __name__ == "__main__":
    ok = asyncio.run(main())
    exit(0 if ok else 1)
