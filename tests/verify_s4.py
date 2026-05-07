"""S4 真实浏览器测试 — 文件工具验证。

验证标准（第二条）：创建文件 → 磁盘真实存在。
流程：WebSocket → 让 LLM 创建文件 → 检查磁盘 → 让 LLM 读取文件 → 验证内容。
"""

import asyncio
import json
import os
import sys

import websockets

sys.stdout.reconfigure(encoding='utf-8')

# 测试文件路径（相对于工作区）
TEST_FILE = "tests/_s4_test_output.txt"
TEST_CONTENT = "LucidMind S4 File Tool Verified"


async def verify_s4():
    uri = "ws://127.0.0.1:8765/ws"
    print(f"Connecting to {uri}...")

    try:
        async with websockets.connect(uri) as ws:
            print("Connected!\n")

            # === Step 1: 让 LLM 写文件 ===
            write_msg = (
                f"Use the write_file tool to create a file at path '{TEST_FILE}' "
                f"with exactly this content: {TEST_CONTENT}"
            )
            print(f"[Step 1] Sending write request: {write_msg[:80]}...")
            await ws.send(json.dumps({"type": "chat", "message": write_msg}))

            events = {"tool_call": False, "tool_result": False, "response": False}
            write_result_text = ""

            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=45)
                    data = json.loads(raw)
                    etype = data.get("type")
                    content = data.get("data", "")

                    if etype == "thinking":
                        print(f"  [thinking] {str(content)[:60]}...")
                    elif etype == "tool_call":
                        print(f"  [tool_call] {content}")
                        events["tool_call"] = True
                    elif etype == "tool_result":
                        print(f"  [tool_result] {content}")
                        events["tool_result"] = True
                        write_result_text = str(content)
                    elif etype == "response":
                        print(f"  [response] {str(content)[:80]}...")
                        events["response"] = True
                    elif etype == "complete":
                        break
                    elif etype == "error":
                        print(f"  [ERROR] {content}")
                        break
                except asyncio.TimeoutError:
                    print("  [TIMEOUT]")
                    break

            # === Step 2: 检查磁盘文件 ===
            workspace = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            file_path = os.path.join(workspace, TEST_FILE)
            print(f"\n[Step 2] Checking disk: {file_path}")

            if os.path.exists(file_path):
                disk_content = open(file_path, encoding="utf-8").read()
                print("  File exists: YES")
                print(f"  Content: {disk_content!r}")
                disk_ok = TEST_CONTENT in disk_content
                print(f"  Content match: {'[OK]' if disk_ok else '[FAIL]'}")
            else:
                print("  File exists: NO [FAIL]")
                disk_ok = False

            # === Summary ===
            print("\n=== S4 Verification Summary ===")
            print(f"Tool Call:    {'[OK]' if events['tool_call'] else '[FAIL]'}")
            print(f"Tool Result:  {'[OK]' if events['tool_result'] else '[FAIL]'}")
            print(f"Response:     {'[OK]' if events['response'] else '[FAIL]'}")
            print(f"Disk Exists:  {'[OK]' if disk_ok else '[FAIL]'}")

            if events["tool_call"] and events["tool_result"] and disk_ok:
                print("\n[SUCCESS] S4 File Tool Verified!")
                # 清理测试文件
                try:
                    os.remove(file_path)
                    print(f"(Cleaned up {TEST_FILE})")
                except OSError:
                    pass
                sys.exit(0)
            else:
                print("\n[FAIL] S4 Verification Failed")
                sys.exit(1)

    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(verify_s4())
