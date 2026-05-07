"""S6 真实浏览器测试 — 记忆持久化验证。

验证标准（第二条）：暗号测试 → 新对话仍记得。
流程：
  连接1: 告诉 LLM 暗号 → 断开
  连接2: 问 LLM 暗号 → 验证它还记得
"""

import asyncio
import json
import sys

import websockets

sys.stdout.reconfigure(encoding='utf-8')

SECRET = "天王盖地虎"
SESSION_ID = "s6_memory_test"


async def send_and_collect(uri: str, message: str, session_id: str) -> dict:
    """发送消息并收集所有事件。"""
    events = {"thinking": [], "response": "", "tool_calls": [], "tool_results": []}

    async with websockets.connect(uri) as ws:
        payload = json.dumps({"type": "chat", "message": message, "session_id": session_id})
        await ws.send(payload)

        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=60)
                data = json.loads(raw)
                etype = data.get("type")
                content = data.get("data", "")

                if etype == "thinking":
                    events["thinking"].append(str(content)[:100])
                elif etype == "tool_call":
                    events["tool_calls"].append(content)
                elif etype == "tool_result":
                    events["tool_results"].append(content)
                elif etype == "response":
                    events["response"] = str(content)
                elif etype == "complete":
                    break
                elif etype == "error":
                    events["response"] = f"[ERROR] {content}"
                    break
            except asyncio.TimeoutError:
                events["response"] = "[TIMEOUT]"
                break

    return events


async def verify_s6():
    uri = "ws://127.0.0.1:8765/ws"

    # === Step 1: 告诉 LLM 暗号 ===
    print(f"[Step 1] 连接1: 告诉暗号 '{SECRET}'")
    msg1 = f"请记住这个暗号：{SECRET}。暗号非常重要，请确认你记住了。"
    r1 = await send_and_collect(uri, msg1, SESSION_ID)
    print(f"  Response: {r1['response'][:100]}...")
    print("  (连接1 断开)")

    step1_ok = SECRET in r1["response"] or "记住" in r1["response"] or "天王" in r1["response"]
    print(f"  Step 1: {'[OK]' if step1_ok else '[WARN]'}")

    # 等待确保文件写入完成
    await asyncio.sleep(1)

    # === Step 2: 新连接，问暗号 ===
    print("\n[Step 2] 连接2: 询问暗号（新 WebSocket 连接）")
    msg2 = "你还记得我之前告诉你的暗号是什么吗？请直接说出暗号内容。"
    r2 = await send_and_collect(uri, msg2, SESSION_ID)
    print(f"  Response: {r2['response'][:200]}...")

    step2_ok = SECRET in r2["response"]
    print(f"  Step 2: {'[OK]' if step2_ok else '[FAIL]'}")

    # === Summary ===
    print("\n=== S6 Verification Summary ===")
    print(f"Step 1 (tell secret):   {'[OK]' if step1_ok else '[WARN]'}")
    print(f"Step 2 (recall secret): {'[OK]' if step2_ok else '[FAIL]'}")
    print(f"Secret '{SECRET}' in response: {'YES' if step2_ok else 'NO'}")

    if step2_ok:
        print("\n[SUCCESS] S6 Memory Persistence Verified!")
        # 清理测试会话文件
        import os
        session_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                     "data", "sessions", f"{SESSION_ID}.json")
        if os.path.exists(session_file):
            os.remove(session_file)
            print(f"(Cleaned up {SESSION_ID}.json)")
        sys.exit(0)
    else:
        print("\n[FAIL] S6 Verification Failed — LLM did not recall the secret")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(verify_s6())
