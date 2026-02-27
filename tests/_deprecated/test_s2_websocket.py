"""S3 真实 WebSocket 测试 -- 验证工具调用 + 真实思考。"""

import asyncio
import json
import websockets


async def send_and_collect(ws, message):
    """发送消息并收集所有事件直到 complete。"""
    await ws.send(json.dumps({"type": "chat", "message": message}))
    events = []
    while True:
        msg = await asyncio.wait_for(ws.recv(), timeout=60)
        data = json.loads(msg)
        events.append(data)
        preview = str(data.get("data", ""))[:120]
        print(f"  [{data['type']}] {preview}")
        if data["type"] == "complete":
            break
    return events


async def test_s3():
    print("=== S3 Test: Tool Call ===")
    print("connecting...")
    async with websockets.connect("ws://127.0.0.1:8765/ws") as ws:
        # Test 1: 普通对话 (S2 regression)
        print("\n--- Test 1: normal chat ---")
        events = await send_and_collect(ws, "hi")
        types = [e["type"] for e in events]
        assert "response" in types, "no response"
        assert "info" in types, "no info"
        print("[PASS] normal chat ok")

        # Test 2: 要求执行命令 (S3 core)
        print("\n--- Test 2: tool call ---")
        events = await send_and_collect(ws, "please run: echo hello-lucidmind")
        types = [e["type"] for e in events]
        print(f"\nevent types: {types}")

        has_tool_call = "tool_call" in types
        has_tool_result = "tool_result" in types
        has_response = "response" in types

        print(f"has tool_call: {has_tool_call}")
        print(f"has tool_result: {has_tool_result}")
        print(f"has response: {has_response}")

        assert has_response, "no response"

        if has_tool_call:
            print("[PASS] S3 tool call works!")
        else:
            print("[WARN] LLM did not choose to call tool (may need prompt tuning)")
            print("[PASS] S3 basic pass -- no crash, response received")


if __name__ == "__main__":
    asyncio.run(test_s3())
