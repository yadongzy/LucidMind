"""S17 最终综合浏览器测试：流式输出 + 元认知 + 资源监控。"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8765"

def send_and_wait(page, prompt, timeout=30):
    """发送消息并等待回复完成，返回 (thinking_texts, streaming_seen, reply, elapsed)。"""
    count_before = len(page.query_selector_all("#messages .message.assistant"))
    t0 = time.time()
    page.fill("#user-input", prompt)
    page.click("#send-btn")

    thinking = []
    streamed = False
    for _ in range(timeout * 2):
        time.sleep(0.5)
        for b in page.query_selector_all(".thinking-box .thinking-body"):
            t = b.inner_text()
            if t and t not in thinking:
                thinking.append(t)
        if page.query_selector(".message.assistant.streaming"):
            streamed = True
        msgs = page.query_selector_all("#messages .message.assistant")
        if len(msgs) > count_before:
            last = msgs[-1]
            if not last.evaluate("el => el.classList.contains('streaming')"):
                break

    elapsed = time.time() - t0
    msgs = page.query_selector_all("#messages .message.assistant")
    reply = msgs[-1].inner_text() if len(msgs) > count_before else ""
    return thinking, streamed, reply, elapsed

def main():
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(BASE)
        page.wait_for_selector("#status-indicator.online", timeout=15000)
        time.sleep(1)

        # T1: 元认知 — 知识推理
        think, stream, reply, t = send_and_wait(page, "解释为什么Python用缩进而不是大括号")
        metacog = any("🧠" in x for x in think)
        ok = metacog and len(reply) > 20
        results.append(("T1-元认知(推理)", ok, metacog, stream, len(reply), t))

        # T2: 元认知 — 记忆请求
        think, stream, reply, t = send_and_wait(page, "记住我最喜欢的颜色是蓝色")
        metacog = any("🧠" in x for x in think)
        ok = metacog and len(reply) > 5
        results.append(("T2-元认知(记忆)", ok, metacog, stream, len(reply), t))

        # T3: 流式输出 — 长回复
        think, stream, reply, t = send_and_wait(page, "用3段话介绍Python的GIL机制，每段至少40字", timeout=40)
        ok = len(reply) > 100
        results.append(("T3-流式长回复", ok, any("🧠" in x for x in think), stream, len(reply), t))

        # T4: 追问上下文
        think, stream, reply, t = send_and_wait(page, "我刚才说我喜欢什么颜色？")
        ok = "蓝" in reply
        results.append(("T4-记忆追问", ok, any("🧠" in x for x in think), stream, len(reply), t))

        # T5: 简单问题（短回复走非流式）
        think, stream, reply, t = send_and_wait(page, "2+3等于多少")
        ok = "5" in reply
        results.append(("T5-简单计算", ok, any("🧠" in x for x in think), stream, len(reply), t))

        browser.close()

    # 输出报告
    print(f"\n{'='*70}")
    print("S17 最终综合浏览器测试报告")
    print(f"{'='*70}")
    print(f"{'测试':<20} {'判定':<6} {'元认知':<6} {'流式':<6} {'回复字数':<8} {'耗时':<6}")
    print("-" * 70)
    for name, ok, mc, st, rlen, elapsed in results:
        print(f"{name:<20} {'✅' if ok else '❌':<6} {'🧠' if mc else '—':<6} {'📡' if st else '—':<6} {rlen:<8} {elapsed:.1f}s")
    
    passed = sum(1 for r in results if r[1])
    total = len(results)
    print(f"\n总计: {passed}/{total} 通过")
    print(f"总判定: {'✅ ALL PASS' if passed == total else '❌ HAS FAILURES'}")
    return passed == total

if __name__ == "__main__":
    main()
