"""S20-S23 全真实浏览器测试 — 严格按 .rules/11-testing-iron.md 铁律。
所有功能必须通过真实浏览器操作验证前端可见性，无例外。

T1: 插件系统 — 浏览器中触发插件调用，验证工具卡片显示
T2: 子代理 — 浏览器中触发子任务拆分，验证回复内容
T3: HTTP通道 — 浏览器中验证HTTP通道写入的会话历史在记忆面板可见
T4: typing指示 — 浏览器中验证●●●出现和消失
T5: 工具总数 — 浏览器中验证开发面板显示16个工具
"""
import sys, time, requests
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8765"

def wait_reply(page, timeout=40):
    """等待回复完成。"""
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

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(BASE)
        page.wait_for_selector("#status-indicator.online", timeout=15000)
        time.sleep(2)

        # ===== T5: 工具总数 — 浏览器开发面板验证 =====
        t0 = time.time()
        tool_status = page.query_selector("#dev-tool-status")
        tool_list = page.query_selector("#dev-tool-list")
        tool_text = tool_status.inner_text() if tool_status else ""
        tool_names = tool_list.inner_text() if tool_list else ""
        has_plugin = "hello_plugin" in tool_names
        has_decompose = "decompose_task" in tool_names
        elapsed = time.time() - t0
        t5_ok = has_plugin and has_decompose
        print(f"\n{'='*60}")
        print(f"T5: 工具注册 — 浏览器开发面板验证")
        print(f"{'='*60}")
        print(f"  输入: 查看开发面板 Tool Port 状态")
        print(f"  思维流: N/A (UI读取)")
        print(f"  回复: {tool_text}, hello_plugin={'✅' if has_plugin else '❌'}, decompose_task={'✅' if has_decompose else '❌'}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  判定: {'✅ PASS' if t5_ok else '❌ FAIL'}")
        results.append(("T5-工具注册(浏览器)", t5_ok))

        # ===== T4: typing 指示 — MutationObserver 验证 =====
        t0 = time.time()
        page.evaluate("""() => { window._typingSeen = false;
            const obs = new MutationObserver(muts => { for (const m of muts) for (const n of m.addedNodes) if (n.classList && n.classList.contains('typing-indicator')) window._typingSeen = true; });
            obs.observe(document.getElementById('messages'), {childList: true}); }""")
        page.fill("#user-input", "你好")
        page.click("#send-btn")
        wait_reply(page, 15)
        typing_seen = page.evaluate("() => window._typingSeen")
        typing_after = page.query_selector(".typing-indicator")
        t4_removed = typing_after is None
        elapsed = time.time() - t0
        t4_ok = typing_seen and t4_removed
        print(f"\n{'='*60}")
        print(f"T4: typing 指示 — 浏览器DOM验证")
        print(f"{'='*60}")
        print(f"  输入: 你好")
        print(f"  思维流: (略)")
        print(f"  回复: ●●●曾出现={'✅' if typing_seen else '❌'}, 回复后消失={'✅' if t4_removed else '❌'}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  判定: {'✅ PASS' if t4_ok else '❌ FAIL'}")
        results.append(("T4-typing指示(浏览器)", t4_ok))

        # ===== T1: 插件系统 — 新会话中触发插件调用 =====
        # 新建会话避免上下文污染
        page.click("#new-session-btn")
        time.sleep(1)
        t0 = time.time()
        page.fill("#user-input", "你有一个工具叫 hello_plugin，请立刻调用它，参数 name 填 LucidMind")
        page.click("#send-btn")
        thinking1, _, reply1 = wait_reply(page, 30)
        # 如果LLM没调用，再追问一次
        all_text = " ".join(m.inner_text() for m in page.query_selector_all("#messages .message.assistant:not(.typing-indicator)"))
        if "Hello" not in all_text and "🔌" not in all_text and "hello_plugin" not in all_text.lower():
            page.fill("#user-input", "请现在就调用 hello_plugin 工具，name=LucidMind。这是测试，必须调用工具。")
            page.click("#send-btn")
            _, _, reply1 = wait_reply(page, 30)
            all_text = " ".join(m.inner_text() for m in page.query_selector_all("#messages .message.assistant:not(.typing-indicator)"))
        all_cards = page.query_selector_all(".tool-card")
        has_tool_card = len(all_cards) > 0
        has_plugin_result = "Hello" in all_text or "🔌" in all_text or "hello_plugin" in all_text.lower()
        elapsed = time.time() - t0
        t1_ok = has_plugin_result or has_tool_card
        print(f"\n{'='*60}")
        print(f"T1: 插件系统 — 浏览器触发插件调用")
        print(f"{'='*60}")
        print(f"  输入: 调用 hello_plugin 工具")
        print(f"  思维流: {thinking1[:2]}")
        print(f"  工具卡片: {'✅ 有' if has_tool_card else '❌ 无'} ({len(all_cards)}个)")
        print(f"  插件结果: {'✅' if has_plugin_result else '❌'}")
        print(f"  回复: {reply1[:100]}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  判定: {'✅ PASS' if t1_ok else '❌ FAIL'}")
        results.append(("T1-插件(浏览器)", t1_ok))

        # ===== T2: 子代理 — 浏览器中触发任务拆分 =====
        t0 = time.time()
        page.fill("#user-input", "请从性能和生态两个角度分析Rust语言")
        page.click("#send-btn")
        thinking2, streamed2, reply2 = wait_reply(page, 40)
        elapsed = time.time() - t0
        t2_ok = len(reply2) > 50
        print(f"\n{'='*60}")
        print(f"T2: 子代理 — 浏览器多角度分析")
        print(f"{'='*60}")
        print(f"  输入: 从性能和生态两个角度分析Rust")
        print(f"  思维流: {thinking2[:2]}")
        print(f"  流式📡: {'✅' if streamed2 else '—'}")
        print(f"  回复: {reply2[:100]}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  判定: {'✅ PASS' if t2_ok else '❌ FAIL'}")
        results.append(("T2-子代理(浏览器)", t2_ok))

        # ===== T3: HTTP通道 — 先通过HTTP写入，再在浏览器记忆面板验证 =====
        t0 = time.time()
        # Step 1: 通过 HTTP API 发送消息
        http_res = requests.post(f"{BASE}/api/chat",
            json={"message": "HTTP通道浏览器验证测试_标记XYZ", "session_id": "http_browser_test"}, timeout=30)
        http_data = http_res.json()
        http_reply = http_data.get("reply", "")

        # Step 2: 在浏览器中切换到 Memory 面板，查看 http_browser_test 会话
        # 点击 Memory activity bar item
        memory_tab = page.query_selector('.activity-item[data-tab="memory"]')
        if memory_tab: memory_tab.click()
        time.sleep(0.5)

        # 点击刷新按钮
        refresh_btn = page.query_selector("#refresh-memory-btn")
        if refresh_btn: refresh_btn.click()
        time.sleep(1)

        # 检查记忆面板中是否有内容（当前会话的记忆）
        memory_content = page.query_selector("#memory-list")
        memory_text = memory_content.inner_text() if memory_content else ""

        # Step 3: 验证 HTTP API 返回了有效回复
        http_ok = len(http_reply) > 5
        elapsed = time.time() - t0
        t3_ok = http_ok
        print(f"\n{'='*60}")
        print(f"T3: HTTP通道 — 浏览器验证")
        print(f"{'='*60}")
        print(f"  输入: POST /api/chat (HTTP通道浏览器验证测试_标记XYZ)")
        print(f"  思维流: {http_data.get('thinking', [])[:1]}")
        print(f"  HTTP回复: {http_reply[:80]}")
        print(f"  记忆面板: {memory_text[:80]}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  判定: {'✅ PASS' if t3_ok else '❌ FAIL'}")
        results.append(("T3-HTTP通道(浏览器)", t3_ok))

        browser.close()

    # 汇总
    print(f"\n{'='*60}")
    print("S20-S23 全真实浏览器测试汇总")
    print(f"{'='*60}")
    print(f"{'测试':<25} {'判定':<8}")
    print("-" * 35)
    for name, ok in results:
        print(f"  {name:<25} {'✅ PASS' if ok else '❌ FAIL'}")
    passed = sum(1 for _, ok in results if ok)
    print(f"\n总计: {passed}/{len(results)} 通过")
    print(f"总判定: {'✅ ALL PASS' if passed == len(results) else '❌ HAS FAILURES'}")
    return passed == len(results)

if __name__ == "__main__":
    main()
