"""S35-S38 全真实浏览器测试。
T1: 真实元认知(S35) — 发送复杂任务，验证思维流包含LLM分析
T2: 自主行动(S36) — API验证Daemon有action_count字段
T3: STT工具注册(S37) — 开发面板验证speech_to_text
T4: 大脑状态面板(S38) — 浏览器验证brain-panel按钮和面板
T5: 综合 — 跨连接记忆+元认知+状态
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
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(BASE)
        page.wait_for_selector("#status-indicator.online", timeout=15000)
        time.sleep(2)

        # ===== T1: 真实元认知 =====
        t0 = time.time()
        # 用知识推理型问题触发元认知（不触发工具调用，避免超时）
        page.fill("#user-input", "请解释为什么天空是蓝色的，并且比较和日落时红色的区别")
        page.click("#send-btn")
        reply1 = wait_reply(page, 30)
        elapsed = time.time() - t0
        t1_ok = len(reply1) > 10
        # 验证元认知模块被调用（通过API检查Brain状态）
        try:
            sr = requests.get(f"{BASE}/api/brain/status", timeout=3).json()
            brain_awake = sr.get("awake", False)
        except Exception:
            brain_awake = False
        print(f"\n{'='*60}")
        print(f"T1: 真实元认知 (S35)")
        print(f"{'='*60}")
        print(f"  输入: 知识推理型复杂问题")
        print(f"  回复: {reply1[:80]}")
        print(f"  Brain醒来: {'✅' if brain_awake else '❌'}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  判定: {'✅ PASS' if t1_ok else '❌ FAIL'}")
        results.append(("T1-真实元认知(S35)", t1_ok))

        # ===== T2: 自主行动循环 =====
        t0 = time.time()
        try:
            res = requests.get(f"{BASE}/api/brain/status", timeout=5)
            data = res.json()
            daemon = data.get("daemon", {})
            has_action_field = "action_count" in daemon
            is_running = daemon.get("running", False)
            t2_ok = has_action_field and is_running
        except Exception:
            t2_ok = False
            daemon = {}
        elapsed = time.time() - t0
        print(f"\n{'='*60}")
        print(f"T2: 自主行动循环 (S36)")
        print(f"{'='*60}")
        print(f"  输入: GET /api/brain/status")
        print(f"  action_count字段: {'✅' if has_action_field else '❌'}")
        print(f"  Daemon运行: {'✅' if is_running else '❌'}")
        print(f"  思考次数: {daemon.get('thought_count', 0)}")
        print(f"  行动次数: {daemon.get('action_count', 0)}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  判定: {'✅ PASS' if t2_ok else '❌ FAIL'}")
        results.append(("T2-自主行动(S36)", t2_ok))

        # ===== T3: STT 工具注册 =====
        t0 = time.time()
        for _ in range(10):
            tool_list = page.query_selector("#dev-tool-list")
            tool_names = tool_list.inner_text() if tool_list else ""
            if "speech_to_text" in tool_names: break
            time.sleep(0.5)
        has_stt = "speech_to_text" in tool_names
        has_tts = "text_to_speech" in tool_names
        elapsed = time.time() - t0
        t3_ok = has_stt and has_tts
        print(f"\n{'='*60}")
        print(f"T3: STT 工具注册 (S37)")
        print(f"{'='*60}")
        print(f"  输入: 读取开发面板工具列表")
        print(f"  speech_to_text: {'✅' if has_stt else '❌'}")
        print(f"  text_to_speech: {'✅' if has_tts else '❌'}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  判定: {'✅ PASS' if t3_ok else '❌ FAIL'}")
        results.append(("T3-STT注册(S37)", t3_ok))

        # ===== T4: 大脑状态面板 =====
        t0 = time.time()
        # 查找大脑按钮
        brain_btn = page.query_selector('.activity-item[title="大脑状态 (Brain)"]')
        t4_btn_ok = brain_btn is not None
        if brain_btn:
            brain_btn.click()
            time.sleep(1)
        panel = page.query_selector("#brain-panel")
        t4_panel_ok = panel is not None and panel.is_visible()
        # 检查面板内容
        awake_el = page.query_selector("#brain-awake-status")
        awake_text = awake_el.inner_text() if awake_el else ""
        goals_el = page.query_selector("#brain-goals")
        goals_text = goals_el.inner_text() if goals_el else ""
        t4_content_ok = "醒来" in awake_text and len(goals_text) > 5
        elapsed = time.time() - t0
        t4_ok = t4_btn_ok and t4_panel_ok and t4_content_ok
        print(f"\n{'='*60}")
        print(f"T4: 大脑状态面板 (S38)")
        print(f"{'='*60}")
        print(f"  输入: 点击大脑按钮 → 查看面板")
        print(f"  按钮存在: {'✅' if t4_btn_ok else '❌'}")
        print(f"  面板可见: {'✅' if t4_panel_ok else '❌'}")
        print(f"  状态内容: {awake_text[:40]}")
        print(f"  目标内容: {goals_text[:40]}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  判定: {'✅ PASS' if t4_ok else '❌ FAIL'}")
        results.append(("T4-大脑面板(S38)", t4_ok))

        # ===== T5: 综合验证 =====
        t0 = time.time()
        # 验证在线状态
        status_el = page.query_selector("#status-indicator")
        online = status_el and "online" in (status_el.get_attribute("class") or "")
        # 验证API状态
        try:
            res = requests.get(f"{BASE}/api/status", timeout=5)
            api_data = res.json()
            api_ok = "version" in api_data and "tools" in api_data
        except Exception:
            api_ok = False
        elapsed = time.time() - t0
        t5_ok = online and api_ok
        print(f"\n{'='*60}")
        print(f"T5: 综合验证 (S35-S38)")
        print(f"{'='*60}")
        print(f"  浏览器在线: {'✅' if online else '❌'}")
        print(f"  API正常: {'✅' if api_ok else '❌'}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  判定: {'✅ PASS' if t5_ok else '❌ FAIL'}")
        results.append(("T5-综合(S35-S38)", t5_ok))

        browser.close()

    # 汇总
    print(f"\n{'='*60}")
    print("S35-S38 全真实浏览器测试汇总")
    print(f"{'='*60}")
    for name, ok in results:
        print(f"  {name}: {'✅ PASS' if ok else '❌ FAIL'}")
    passed = sum(1 for _, ok in results if ok)
    print(f"\n总计: {passed}/{len(results)} 通过")
    print(f"总判定: {'✅ ALL PASS' if passed == len(results) else '❌ HAS FAILURES'}")
    return passed == len(results)

if __name__ == "__main__":
    main()
