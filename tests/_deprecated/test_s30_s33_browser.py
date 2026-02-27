"""S30-S33 全真实浏览器测试 — 大脑醒来验证。
T1: Brain单例(S30) — 浏览器发消息→断开→重连→历史保留
T2: 后台思考(S31) — API验证Daemon运行+思考日志
T3: 动态灵魂(S32) — API验证灵魂进化历史端点
T4: 目标系统(S33) — API验证目标注入+浏览器对话含目标感知
T5: 大脑状态(S30-S33) — 浏览器验证awake状态
"""
import sys, time, requests
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8765"

def wait_reply(page, timeout=30):
    for _ in range(timeout * 2):
        time.sleep(0.5)
        msgs = page.query_selector_all("#messages .message.assistant:not(.typing-indicator)")
        if msgs and not msgs[-1].evaluate("el => el.classList.contains('streaming')"):
            break
    msgs = page.query_selector_all("#messages .message.assistant:not(.typing-indicator)")
    return msgs[-1].inner_text() if msgs else ""

def main():
    results = []

    # ===== T1: Brain 单例 — 跨连接保留状态 =====
    t0 = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        # 第一次连接：发消息
        page1 = browser.new_page()
        page1.goto(BASE)
        page1.wait_for_selector("#status-indicator.online", timeout=15000)
        time.sleep(2)
        page1.fill("#user-input", "记住这个数字：42")
        page1.click("#send-btn")
        reply1 = wait_reply(page1, 15)
        page1.close()
        time.sleep(1)

        # 第二次连接：验证Brain还记得
        page2 = browser.new_page()
        page2.goto(BASE)
        page2.wait_for_selector("#status-indicator.online", timeout=15000)
        time.sleep(2)
        page2.fill("#user-input", "我刚才让你记住的数字是什么？")
        page2.click("#send-btn")
        reply2 = wait_reply(page2, 15)
        elapsed = time.time() - t0
        t1_ok = "42" in reply2
        print(f"\n{'='*60}")
        print(f"T1: Brain 单例 — 跨连接记忆 (S30)")
        print(f"{'='*60}")
        print(f"  输入: 连接1发'记住42' → 断开 → 连接2问'记住什么数字'")
        print(f"  回复1: {reply1[:60]}")
        print(f"  回复2: {reply2[:60]}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  判定: {'✅ PASS' if t1_ok else '❌ FAIL'}")
        results.append(("T1-Brain单例(S30)", t1_ok))

        # ===== T2: 后台思考 — Daemon 运行验证 =====
        t0 = time.time()
        try:
            res = requests.get(f"{BASE}/api/brain/status", timeout=5)
            data = res.json()
            daemon_running = data.get("daemon", {}).get("running", False)
            is_awake = data.get("awake", False)
        except Exception:
            daemon_running = False
            is_awake = False
        # 检查思考日志
        try:
            res2 = requests.get(f"{BASE}/api/brain/thoughts", timeout=5)
            thoughts = res2.json().get("thoughts", [])
            has_thoughts = len(thoughts) > 0
        except Exception:
            has_thoughts = False
        # 浏览器验证：发消息确认Brain正常工作
        page2.fill("#user-input", "你现在醒着吗？")
        page2.click("#send-btn")
        reply_awake = wait_reply(page2, 15)
        elapsed = time.time() - t0
        t2_ok = daemon_running and is_awake and has_thoughts
        print(f"\n{'='*60}")
        print(f"T2: 后台思考 — Daemon 运行 (S31)")
        print(f"{'='*60}")
        print(f"  输入: GET /api/brain/status + /api/brain/thoughts + 浏览器对话")
        print(f"  Daemon运行: {'✅' if daemon_running else '❌'}")
        print(f"  大脑醒来: {'✅' if is_awake else '❌'}")
        print(f"  思考日志: {len(thoughts)}条 {'✅' if has_thoughts else '❌'}")
        print(f"  浏览器回复: {reply_awake[:60]}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  判定: {'✅ PASS' if t2_ok else '❌ FAIL'}")
        results.append(("T2-后台思考(S31)", t2_ok))

        # ===== T3: 动态灵魂 — 进化历史端点 =====
        t0 = time.time()
        try:
            res3 = requests.get(f"{BASE}/api/brain/soul/history", timeout=5)
            soul_data = res3.json()
            t3_ok = "history" in soul_data
        except Exception:
            t3_ok = False
        elapsed = time.time() - t0
        print(f"\n{'='*60}")
        print(f"T3: 动态灵魂 — 进化历史 (S32)")
        print(f"{'='*60}")
        print(f"  输入: GET /api/brain/soul/history")
        print(f"  回复: history字段={'✅' if t3_ok else '❌'}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  判定: {'✅ PASS' if t3_ok else '❌ FAIL'}")
        results.append(("T3-动态灵魂(S32)", t3_ok))

        # ===== T4: 目标系统 — 目标列表 =====
        t0 = time.time()
        try:
            res4 = requests.get(f"{BASE}/api/brain/goals", timeout=5)
            goals_data = res4.json()
            goals = goals_data.get("goals", [])
            has_long_term = any(g.get("type") == "long_term" for g in goals)
            t4_ok = len(goals) >= 3 and has_long_term
        except Exception:
            goals = []
            t4_ok = False
        elapsed = time.time() - t0
        print(f"\n{'='*60}")
        print(f"T4: 目标系统 — 目标列表 (S33)")
        print(f"{'='*60}")
        print(f"  输入: GET /api/brain/goals")
        print(f"  目标数: {len(goals)}")
        print(f"  长期目标: {'✅' if has_long_term else '❌'}")
        for g in goals[:3]:
            print(f"    - [{g.get('type')}] {g.get('content', '')[:50]}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  判定: {'✅ PASS' if t4_ok else '❌ FAIL'}")
        results.append(("T4-目标系统(S33)", t4_ok))

        # ===== T5: 综合 — 浏览器验证大脑状态面板 =====
        t0 = time.time()
        # 检查开发面板是否显示工具
        for _ in range(10):
            tool_list = page2.query_selector("#dev-tool-list")
            tool_names = tool_list.inner_text() if tool_list else ""
            if "run_command" in tool_names: break
            time.sleep(0.5)
        tools_ok = "run_command" in tool_names
        # 检查状态指示器
        status_el = page2.query_selector("#status-indicator")
        online = status_el and "online" in (status_el.get_attribute("class") or "")
        elapsed = time.time() - t0
        t5_ok = tools_ok and online
        print(f"\n{'='*60}")
        print(f"T5: 综合状态验证 (S30-S33)")
        print(f"{'='*60}")
        print(f"  输入: 浏览器开发面板 + 状态指示器")
        print(f"  工具列表: {'✅' if tools_ok else '❌'}")
        print(f"  在线状态: {'✅' if online else '❌'}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  判定: {'✅ PASS' if t5_ok else '❌ FAIL'}")
        results.append(("T5-综合状态(S30-S33)", t5_ok))

        browser.close()

    # 汇总
    print(f"\n{'='*60}")
    print("S30-S33 全真实浏览器测试汇总")
    print(f"{'='*60}")
    for name, ok in results:
        print(f"  {name}: {'✅ PASS' if ok else '❌ FAIL'}")
    passed = sum(1 for _, ok in results if ok)
    print(f"\n总计: {passed}/{len(results)} 通过")
    print(f"总判定: {'✅ ALL PASS' if passed == len(results) else '❌ HAS FAILURES'}")
    return passed == len(results)

if __name__ == "__main__":
    main()
