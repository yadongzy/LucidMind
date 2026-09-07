"""S18 浏览器测试：多会话管理。"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8765"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(BASE)
        page.wait_for_selector("#status-indicator.online", timeout=15000)
        time.sleep(1)

        results = []

        # T1: 侧边栏会话列表加载
        sessions = page.query_selector_all("#session-list .session-item")
        t1_ok = len(sessions) >= 1
        t1_default = any(el.get_attribute("data-sid") == "default" for el in sessions)
        results.append(("T1-会话列表加载", t1_ok and t1_default, f"{len(sessions)}个会话, default={'✅' if t1_default else '❌'}"))

        # T2: 新建会话
        new_btn = page.query_selector("#new-session-btn")
        new_btn.click()
        time.sleep(1)
        sessions_after = page.query_selector_all("#session-list .session-item")
        t2_ok = len(sessions_after) > len(sessions)
        new_sid = ""
        for el in sessions_after:
            sid = el.get_attribute("data-sid")
            if sid != "default" and el.evaluate("el => el.classList.contains('active')"):
                new_sid = sid
        results.append(("T2-新建会话", t2_ok and bool(new_sid), f"新会话={new_sid}, 总数={len(sessions_after)}"))

        # T3: 在新会话中发消息
        page.fill("#user-input", "这是新会话的测试消息")
        page.click("#send-btn")
        for _ in range(30):
            time.sleep(0.5)
            msgs = page.query_selector_all("#messages .message.assistant")
            if msgs:
                last = msgs[-1]
                if not last.evaluate("el => el.classList.contains('streaming')"):
                    break
        new_reply = page.query_selector_all("#messages .message.assistant")
        t3_ok = len(new_reply) > 0
        results.append(("T3-新会话发消息", t3_ok, f"回复数={len(new_reply)}"))

        # T4: 切换回 default
        default_item = page.query_selector('#session-list .session-item[data-sid="default"]')
        if default_item:
            default_item.click()
            time.sleep(1)
            # 消息区应该被清空（default 可能有历史也可能没有）
            active_el = page.query_selector("#session-list .session-item.active")
            t4_ok = active_el and active_el.get_attribute("data-sid") == "default"
        else:
            t4_ok = False
        results.append(("T4-切换到default", t4_ok, ""))

        # T5: 删除新会话
        if new_sid:
            # 切换回新会话先
            new_item = page.query_selector(f'#session-list .session-item[data-sid="{new_sid}"]')
            if new_item:
                del_btn = new_item.query_selector(".del-btn")
                if del_btn:
                    page.on("dialog", lambda d: d.accept())
                    del_btn.click()
                    time.sleep(1)
                    remaining = page.query_selector_all("#session-list .session-item")
                    t5_ok = not any(el.get_attribute("data-sid") == new_sid for el in remaining)
                else:
                    t5_ok = False
            else:
                t5_ok = False
        else:
            t5_ok = False
        results.append(("T5-删除会话", t5_ok, f"删除{new_sid}"))

        browser.close()

    # 报告
    print(f"\n{'='*60}")
    print("S18 多会话浏览器测试报告")
    print(f"{'='*60}")
    for name, ok, detail in results:
        print(f"  {name}: {'✅ PASS' if ok else '❌ FAIL'} {detail}")
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n总计: {passed}/{len(results)} 通过")
    print(f"总判定: {'✅ ALL PASS' if passed == len(results) else '❌ HAS FAILURES'}")
    return passed == len(results)

if __name__ == "__main__":
    main()
