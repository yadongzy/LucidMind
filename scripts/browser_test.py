"""真实浏览器测试 — 通过WebSocket发送消息到大脑对话框，用户在浏览器监控全流程。"""
import asyncio
import json
import time
import sys
sys.stdout.reconfigure(encoding='utf-8')

import websockets


async def send_and_watch(message: str, session_id: str = "default", timeout: float = 60):
    """发送消息并监听所有WebSocket事件，打印完整流程。"""
    uri = "ws://localhost:8765/ws"
    print(f"\n{'='*60}")
    print(f"发送: {message}")
    print(f"会话: {session_id}")
    print(f"{'='*60}")
    
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({
            "type": "chat",
            "message": message,
            "session_id": session_id,
        }))
        
        results = []
        start = time.time()
        reply_text = ""
        
        while time.time() - start < timeout:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
                d = json.loads(raw)
                msg_type = d.get("type", "?")
                data = d.get("data", "")
                elapsed = round(time.time() - start, 1)
                
                if msg_type == "thinking":
                    print(f"  [{elapsed}s] 🧠 思考: {str(data)[:200]}")
                elif msg_type == "tool_call":
                    print(f"  [{elapsed}s] ⚙️  工具调用: {str(data)[:200]}")
                elif msg_type == "tool_result":
                    print(f"  [{elapsed}s] ✅ 工具结果: {str(data)[:200]}")
                elif msg_type == "response_start":
                    print(f"  [{elapsed}s] 📝 开始回复...")
                elif msg_type == "response_delta":
                    reply_text += str(data)
                elif msg_type == "response_end":
                    print(f"  [{elapsed}s] 📝 回复完成: {reply_text[:300]}")
                elif msg_type == "response":
                    reply_text = str(data)
                    print(f"  [{elapsed}s] 💬 回复: {reply_text[:300]}")
                elif msg_type == "complete":
                    print(f"  [{elapsed}s] ✅ 处理完成")
                    results.append(d)
                    break
                elif msg_type == "pong":
                    pass  # 心跳，忽略
                else:
                    print(f"  [{elapsed}s] [{msg_type}] {str(data)[:100]}")
                
                results.append(d)
            except asyncio.TimeoutError:
                continue
        
        total_time = round(time.time() - start, 1)
        types = [r.get("type") for r in results if r.get("type") != "pong"]
        print(f"\n  总耗时: {total_time}s")
        print(f"  事件流: {' → '.join(types)}")
        print(f"  回复: {reply_text[:200] if reply_text else '(无)'}")
        
        return {
            "reply": reply_text,
            "types": types,
            "time": total_time,
            "success": "complete" in types,
        }


async def run_all_tests():
    print("\n" + "="*60)
    print("LucidMind 真实浏览器测试（WebSocket全流程）")
    print("用户请在浏览器中监控大脑对话框")
    print("="*60)
    
    results = {}
    
    # 测试1: 基本对话
    print("\n\n### 测试1: 基本对话")
    r1 = await send_and_watch("你好，请用一句话介绍你自己")
    results["基本对话"] = "✅ 通过" if r1["success"] and r1["reply"] else "❌ 失败"
    
    await asyncio.sleep(2)
    
    # 测试2: 工具调用
    print("\n\n### 测试2: 工具调用（系统时间）")
    r2 = await send_and_watch("请查看当前系统时间")
    has_tool = "tool_call" in r2["types"] or "tool_result" in r2["types"]
    results["工具调用"] = "✅ 通过" if r2["success"] and r2["reply"] else "❌ 失败"
    results["工具调用"] += f" (工具事件: {'有' if has_tool else '无'})"
    
    await asyncio.sleep(2)
    
    # 测试3: 记忆写入
    print("\n\n### 测试3: 记忆写入")
    r3 = await send_and_watch("记住：我最喜欢的编程语言是Python")
    results["记忆写入"] = "✅ 通过" if r3["success"] and r3["reply"] else "❌ 失败"
    
    await asyncio.sleep(2)
    
    # 测试4: 记忆读取
    print("\n\n### 测试4: 记忆读取")
    r4 = await send_and_watch("我最喜欢的编程语言是什么？")
    has_python = "python" in r4["reply"].lower() if r4["reply"] else False
    results["记忆读取"] = f"✅ 通过 (回复含Python)" if has_python else f"⚠️ 回复: {r4['reply'][:100]}"
    
    # 汇总
    print("\n\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    for name, result in results.items():
        print(f"  {name}: {result}")
    
    all_pass = all("✅" in v for v in results.values())
    print(f"\n  总结: {'全部通过 ✅' if all_pass else '有失败项 ⚠️'}")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
