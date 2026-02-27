"""真实浏览器测试：验证元认知 + 流式输出。"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import time
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8765"

def run_test(label, prompt, expect_metacog=True):
    """发送 prompt，检查元认知思考和流式输出。"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(BASE_URL)
        page.wait_for_selector("#status-indicator.online", timeout=15000)
        time.sleep(1)

        t0 = time.time()
        page.fill("#user-input", prompt)
        page.click("#send-btn")

        thinking_texts = []
        streaming_seen = False
        for _ in range(60):
            time.sleep(0.5)
            # 收集 thinking-box 内容（正确选择器: .thinking-body）
            for b in page.query_selector_all(".thinking-box .thinking-body"):
                txt = b.inner_text()
                if txt and txt not in thinking_texts:
                    thinking_texts.append(txt)
            if page.query_selector(".message.assistant.streaming"):
                streaming_seen = True
            # 检查回复完成
            msgs = page.query_selector_all("#messages .message.assistant")
            if msgs:
                last = msgs[-1]
                if not last.evaluate("el => el.classList.contains('streaming')"):
                    break

        elapsed = time.time() - t0
        msgs = page.query_selector_all("#messages .message.assistant")
        reply = msgs[-1].inner_text() if msgs else ""

        metacog_found = any("🧠" in t for t in thinking_texts)
        has_reply = len(reply) > 3
        passed = has_reply and (metacog_found if expect_metacog else True)

        print(f"\n{'='*60}")
        print(f"测试: {label}")
        print(f"{'='*60}")
        print(f"  输入: {prompt[:60]}")
        print(f"  思考: {thinking_texts[:3]}")
        print(f"  元认知🧠: {'✅' if metacog_found else '❌'}")
        print(f"  流式: {'✅' if streaming_seen else '⚠️ 非流式'}")
        print(f"  回复: {reply[:80]}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  判定: {'✅ PASS' if passed else '❌ FAIL'}")

        browser.close()
        return passed

if __name__ == "__main__":
    results = []
    # T1: 知识推理 → 元认知应识别推理型
    results.append(("T1-知识推理", run_test("T1: 知识推理", "解释为什么六边形架构比MVC更好", True)))
    # T2: 记忆意图 → 元认知应识别记忆请求
    results.append(("T2-记忆意图", run_test("T2: 记忆意图", "记住我的名字叫TestUser123", True)))
    # T3: 简单问题 → 元认知可能不触发（也OK）
    results.append(("T3-简单问题", run_test("T3: 简单问题", "1+1等于多少", False)))

    print(f"\n{'='*60}")
    print("总结")
    print(f"{'='*60}")
    for name, passed in results:
        print(f"  {name}: {'✅ PASS' if passed else '❌ FAIL'}")
    all_pass = all(p for _, p in results)
    print(f"\n总判定: {'✅ ALL PASS' if all_pass else '❌ HAS FAILURES'}")
