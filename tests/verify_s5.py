"""S5 真实浏览器测试 -- 网络搜索工具验证。

验证标准（第二条）：问天气 -> 真实搜索结果。
流程：WebSocket -> 让 LLM 搜索 -> 验证返回了真实搜索结果。
"""

import asyncio
import json
import sys

import websockets

sys.stdout.reconfigure(encoding='utf-8')


async def verify_s5():
    uri = "ws://127.0.0.1:8765/ws"
    print(f"Connecting to {uri}...")

    try:
        async with websockets.connect(uri) as ws:
            print("Connected!\n")

            # Send a search request
            query = "Use the web_search tool to search for 'Python 3.13 release date' and tell me what you find."
            print(f"[Step 1] Sending: {query[:60]}...")
            await ws.send(json.dumps({"type": "chat", "message": query}))

            events = {
                "thinking": False,
                "tool_call": False,
                "tool_result": False,
                "response": False,
            }
            tool_result_text = ""

            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=60)
                    data = json.loads(raw)
                    etype = data.get("type")
                    content = data.get("data", "")

                    if etype == "thinking":
                        print(f"  [thinking] {str(content)[:60]}...")
                        events["thinking"] = True
                    elif etype == "tool_call":
                        print(f"  [tool_call] {content}")
                        events["tool_call"] = True
                    elif etype == "tool_result":
                        print(f"  [tool_result] {str(content)[:120]}...")
                        events["tool_result"] = True
                        tool_result_text = str(content)
                    elif etype == "response":
                        print(f"  [response] {str(content)[:100]}...")
                        events["response"] = True
                    elif etype == "info":
                        print(f"  [info] {str(content)[:80]}")
                    elif etype == "complete":
                        break
                    elif etype == "error":
                        print(f"  [ERROR] {content}")
                        break
                except asyncio.TimeoutError:
                    print("  [TIMEOUT]")
                    break

            # Summary
            print("\n=== S5 Verification Summary ===")
            print(f"Thinking:    {'[OK]' if events['thinking'] else '[WARN]'}")
            print(f"Tool Call:   {'[OK]' if events['tool_call'] else '[FAIL]'}")
            print(f"Tool Result: {'[OK]' if events['tool_result'] else '[FAIL]'}")
            print(f"Response:    {'[OK]' if events['response'] else '[FAIL]'}")

            has_real_results = len(tool_result_text) > 20
            print(f"Real Data:   {'[OK]' if has_real_results else '[FAIL]'} ({len(tool_result_text)} chars)")

            if events["tool_call"] and events["tool_result"] and has_real_results:
                print("\n[SUCCESS] S5 WebSearch Tool Verified!")
                sys.exit(0)
            else:
                print("\n[FAIL] S5 Verification Failed")
                sys.exit(1)

    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(verify_s5())
