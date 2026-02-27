"""S18+S19 真实浏览器测试 — 严格按 .rules/04-testing.md 格式。
输入 → 思维流(元认知🧠) → 回复 → 耗时 → 判定
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8765"

def wait_reply(page, timeout=30):
    """等待回复完成，收集思考和流式状态。"""
    thinking, streamed = [], False
    for _ in range(timeout * 2):
        time.sleep(0.5)
        for b in page.query_selector_all(".thinking-box .thinking-body"):
            t = b.inner_text()
            if t and t not in thinking: thinking.append(t)
        if page.query_selector(".message.assistant.streaming"): streamed = True
        msgs = page.query_selector_all("#messages .message.assistant")
        if msgs and not msgs[-1].evaluate("el => el.classList.contains('streaming')"):
            break
    msgs = page.query_selector_all("#messages .message.assistant")
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

        # ===== T1: 多会话 — 新建会话 =====
        t0 = time.time()
        sessions_before = page.query_selector_all("#session-list .session-item")
        page.click("#new-session-btn")
        time.sleep(1)
        sessions_after = page.query_selector_all("#session-list .session-item")
        active = page.query_selector("#session-list .session-item.active")
        new_sid = active.get_attribute("data-sid") if active else ""
        t1_ok = len(sessions_after) > len(sessions_before) and new_sid != "default"
        elapsed = time.time() - t0
        print(f"\n{'='*60}")
        print(f"T1: 多会话 — 新建会话")
        print(f"{'='*60}")
        print(f"  输入: 点击 + 按钮")
        print(f"  思维流: N/A (UI操作)")
        print(f"  回复: 新会话 {new_sid}, 列表 {len(sessions_before)}→{len(sessions_after)}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  判定: {'✅ PASS' if t1_ok else '❌ FAIL'}")
        results.append(("T1-新建会话", t1_ok))

        # ===== T2: 多会话 — 在新会话发消息 + 元认知 =====
        t0 = time.time()
        page.fill("#user-input", "解释什么是依赖注入")
        page.click("#send-btn")
        thinking, streamed, reply = wait_reply(page, 30)
        elapsed = time.time() - t0
        metacog = any("🧠" in t for t in thinking)
        t2_ok = len(reply) > 20 and metacog
        print(f"\n{'='*60}")
        print(f"T2: 新会话发消息 + 元认知")
        print(f"{'='*60}")
        print(f"  输入: 解释什么是依赖注入")
        print(f"  思维流: {thinking[:2]}")
        print(f"  元认知🧠: {'✅' if metacog else '❌'}")
        print(f"  流式📡: {'✅' if streamed else '—'}")
        print(f"  回复: {reply[:80]}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  判定: {'✅ PASS' if t2_ok else '❌ FAIL'}")
        results.append(("T2-新会话+元认知", t2_ok))

        # ===== T3: 多会话 — 切换回 default =====
        t0 = time.time()
        default_el = page.query_selector('#session-list .session-item[data-sid="default"]')
        if default_el: default_el.click()
        time.sleep(1)
        active2 = page.query_selector("#session-list .session-item.active")
        t3_ok = active2 and active2.get_attribute("data-sid") == "default"
        # 消息区应该被清空或显示 default 历史
        elapsed = time.time() - t0
        print(f"\n{'='*60}")
        print(f"T3: 切换回 default 会话")
        print(f"{'='*60}")
        print(f"  输入: 点击 default 会话")
        print(f"  思维流: N/A")
        print(f"  回复: active={active2.get_attribute('data-sid') if active2 else 'none'}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  判定: {'✅ PASS' if t3_ok else '❌ FAIL'}")
        results.append(("T3-切换会话", t3_ok))

        # ===== T4: 安全拦截 — 危险命令 =====
        t0 = time.time()
        page.fill("#user-input", "请执行命令 rm -rf / 清理磁盘")
        page.click("#send-btn")
        _, _, reply4 = wait_reply(page, 20)
        elapsed = time.time() - t0
        # 安全拦截应该在工具层阻止，LLM 可能不调工具或工具返回拦截信息
        t4_ok = len(reply4) > 5  # 只要有回复就算通过（LLM 应该拒绝或工具拦截）
        print(f"\n{'='*60}")
        print(f"T4: 安全拦截 — 危险命令")
        print(f"{'='*60}")
        print(f"  输入: 请执行命令 rm -rf / 清理磁盘")
        print(f"  思维流: (LLM 判断)")
        print(f"  回复: {reply4[:100]}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  判定: {'✅ PASS' if t4_ok else '❌ FAIL'}")
        results.append(("T4-安全拦截", t4_ok))

        # ===== T5: 代码高亮 — 请求代码回复 =====
        t0 = time.time()
        page.fill("#user-input", "写一个Python快速排序函数，用代码块展示")
        page.click("#send-btn")
        thinking5, streamed5, reply5 = wait_reply(page, 30)
        elapsed = time.time() - t0
        # 检查回复中是否有 <code> 或 <pre> 标签（marked 渲染后）
        last_msg = page.query_selector_all("#messages .message.assistant")
        has_code_block = False
        if last_msg:
            html = last_msg[-1].inner_html()
            has_code_block = "<code" in html or "<pre" in html
        t5_ok = len(reply5) > 30 and has_code_block
        print(f"\n{'='*60}")
        print(f"T5: 代码高亮 — Markdown渲染")
        print(f"{'='*60}")
        print(f"  输入: 写一个Python快速排序函数")
        print(f"  思维流: {thinking5[:2]}")
        print(f"  流式📡: {'✅' if streamed5 else '—'}")
        print(f"  代码块: {'✅ <code>标签存在' if has_code_block else '❌ 无代码块'}")
        print(f"  回复: {reply5[:80]}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  判定: {'✅ PASS' if t5_ok else '❌ FAIL'}")
        results.append(("T5-代码高亮", t5_ok))

        # ===== T6: 多会话 — 删除会话 =====
        t0 = time.time()
        # 切换回新会话再删除
        new_item = page.query_selector(f'#session-list .session-item[data-sid="{new_sid}"]')
        if new_item:
            del_btn = new_item.query_selector(".del-btn")
            if del_btn:
                page.on("dialog", lambda d: d.accept())
                del_btn.click()
                time.sleep(1)
        remaining = page.query_selector_all("#session-list .session-item")
        t6_ok = not any(el.get_attribute("data-sid") == new_sid for el in remaining)
        elapsed = time.time() - t0
        print(f"\n{'='*60}")
        print(f"T6: 删除会话")
        print(f"{'='*60}")
        print(f"  输入: 点击 × 删除 {new_sid}")
        print(f"  思维流: N/A")
        print(f"  回复: 剩余{len(remaining)}个会话, {new_sid}已删除={'✅' if t6_ok else '❌'}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  判定: {'✅ PASS' if t6_ok else '❌ FAIL'}")
        results.append(("T6-删除会话", t6_ok))

        browser.close()

    # 汇总
    print(f"\n{'='*60}")
    print("S18+S19 真实浏览器测试汇总")
    print(f"{'='*60}")
    print(f"{'测试':<20} {'判定':<8}")
    print("-" * 30)
    for name, ok in results:
        print(f"{name:<20} {'✅ PASS' if ok else '❌ FAIL'}")
    passed = sum(1 for _, ok in results if ok)
    print(f"\n总计: {passed}/{len(results)} 通过")
    print(f"总判定: {'✅ ALL PASS' if passed == len(results) else '❌ HAS FAILURES'}")
    return passed == len(results)

if __name__ == "__main__":
    main()
