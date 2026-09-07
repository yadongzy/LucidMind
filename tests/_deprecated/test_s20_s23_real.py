"""S20-S23 真实浏览器+API测试。
T1: 子代理（浏览器）
T2: 插件系统（浏览器）
T3: HTTP API 通道（requests）
T4: typing 指示（浏览器）
"""
import sys, time, requests
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8765"

def wait_reply(page, timeout=40):
    thinking, streamed = [], False
    for _ in range(timeout * 2):
        time.sleep(0.5)
        for b in page.query_selector_all(".thinking-box .thinking-body"):
            t = b.inner_text()
            if t and t not in thinking: thinking.append(t)
        if page.query_selector(".message.assistant.streaming"): streamed = True
        msgs = page.query_selector_all("#messages .message.assistant:not(.typing-indicator)")
        if msgs and not msgs[-1].evaluate("el => el.classList.contains('streaming')"):
            break
    msgs = page.query_selector_all("#messages .message.assistant:not(.typing-indicator)")
    reply = msgs[-1].inner_text() if msgs else ""
    return thinking, streamed, reply

def main():
    results = []

    # ===== T1: 子代理 — 通过浏览器触发 =====
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(BASE)
        page.wait_for_selector("#status-indicator.online", timeout=15000)
        time.sleep(1)

        t0 = time.time()
        page.fill("#user-input", "请从3个角度分析Python的优缺点：性能、生态、学习曲线")
        page.click("#send-btn")
        thinking, streamed, reply = wait_reply(page, 40)
        elapsed = time.time() - t0
        t1_ok = len(reply) > 30
        print(f"\n{'='*60}")
        print(f"T1: 子代理 — 多角度分析")
        print(f"{'='*60}")
        print(f"  输入: 3个角度分析Python优缺点")
        print(f"  思维流: {thinking[:2]}")
        print(f"  回复: {reply[:100]}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  判定: {'✅ PASS' if t1_ok else '❌ FAIL'}")
        results.append(("T1-子代理/多角度", t1_ok))

        # ===== T4: typing 指示 — 验证机制存在 + 回复后清理 =====
        t0 = time.time()
        # 用 evaluate 注入检测：submit 后立即检查 DOM 中是否曾出现 typing-indicator
        page.evaluate("""() => { window._typingSeen = false;
            const obs = new MutationObserver(muts => { for (const m of muts) for (const n of m.addedNodes) if (n.classList && n.classList.contains('typing-indicator')) window._typingSeen = true; });
            obs.observe(document.getElementById('messages'), {childList: true}); }""")
        page.fill("#user-input", "1+1等于多少")
        page.click("#send-btn")
        wait_reply(page, 15)
        typing_seen = page.evaluate("() => window._typingSeen")
        typing_after = page.query_selector(".typing-indicator")
        t4_removed = typing_after is None
        elapsed = time.time() - t0
        print(f"\n{'='*60}")
        print(f"T4: typing 指示")
        print(f"{'='*60}")
        print(f"  输入: 1+1等于多少")
        print(f"  曾出现typing: {'✅' if typing_seen else '❌'}")
        print(f"  回复后消失: {'✅' if t4_removed else '❌'}")
        print(f"  耗时: {elapsed:.1f}s")
        t4_pass = typing_seen and t4_removed
        print(f"  判定: {'✅ PASS' if t4_pass else '❌ FAIL'}")
        results.append(("T4-typing指示", t4_pass))

        browser.close()

    # ===== T2: 插件系统 — 验证工具注册 =====
    t0 = time.time()
    try:
        res = requests.get(f"{BASE}/api/status", timeout=5)
        data = res.json()
        tools = data.get("tools", [])
        has_plugin = "hello_plugin" in tools
        has_decompose = "decompose_task" in tools
        t2_ok = has_plugin and has_decompose
        print(f"\n{'='*60}")
        print(f"T2: 插件系统 — 工具注册验证")
        print(f"{'='*60}")
        print(f"  hello_plugin: {'✅ 已注册' if has_plugin else '❌ 未注册'}")
        print(f"  decompose_task: {'✅ 已注册' if has_decompose else '❌ 未注册'}")
        print(f"  总工具数: {len(tools)}")
        print(f"  耗时: {time.time()-t0:.1f}s")
        print(f"  判定: {'✅ PASS' if t2_ok else '❌ FAIL'}")
    except Exception as e:
        t2_ok = False
        print(f"  T2 失败: {e}")
    results.append(("T2-插件系统", t2_ok))

    # ===== T3: HTTP API 通道 =====
    t0 = time.time()
    try:
        res = requests.post(f"{BASE}/api/chat", json={"message": "你好，这是HTTP通道测试", "session_id": "http_test"}, timeout=30)
        data = res.json()
        reply = data.get("reply", "")
        sid = data.get("session_id", "")
        t3_ok = len(reply) > 3 and sid == "http_test"
        print(f"\n{'='*60}")
        print(f"T3: HTTP API 通道")
        print(f"{'='*60}")
        print(f"  输入: 你好，这是HTTP通道测试")
        print(f"  session_id: {sid}")
        print(f"  回复: {reply[:80]}")
        print(f"  thinking: {data.get('thinking', [])[:2]}")
        print(f"  耗时: {time.time()-t0:.1f}s")
        print(f"  判定: {'✅ PASS' if t3_ok else '❌ FAIL'}")
    except Exception as e:
        t3_ok = False
        print(f"  T3 失败: {e}")
    results.append(("T3-HTTP通道", t3_ok))

    # 汇总
    print(f"\n{'='*60}")
    print("S20-S23 综合测试汇总")
    print(f"{'='*60}")
    for name, ok in results:
        print(f"  {name}: {'✅ PASS' if ok else '❌ FAIL'}")
    passed = sum(1 for _, ok in results if ok)
    print(f"\n总计: {passed}/{len(results)} 通过")
    print(f"总判定: {'✅ ALL PASS' if passed == len(results) else '❌ HAS FAILURES'}")
    return passed == len(results)

if __name__ == "__main__":
    main()
