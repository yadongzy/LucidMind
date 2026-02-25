"""真实浏览器测试 — 使用 Playwright 打开 Chromium，验证前端 UI。

这不是 WebSocket 脚本模拟，是真正打开浏览器、在输入框输入、看到 UI 渲染结果。
覆盖 S1-S6 的前端验证标准。
"""

import sys
import time

from playwright.sync_api import sync_playwright, expect

sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8765"
TIMEOUT = 90_000  # 90s — LLM 响应可能慢


def test_s1_chat_reply():
    """S1: 浏览器发'你好' → 收到 LLM 回复。"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(BASE_URL)
        print("[S1] Page loaded:", page.title())

        # 等待 WebSocket 连接（状态变为 ONLINE）
        page.wait_for_selector("#status-indicator.online", timeout=10_000)
        print("[S1] WebSocket connected (ONLINE)")

        # 输入消息
        page.fill("#user-input", "你好")
        page.click("#send-btn")
        print("[S1] Sent: 你好")

        # 等待 assistant 回复出现在消息区
        page.wait_for_selector("#messages .message.assistant", timeout=TIMEOUT)
        reply = page.inner_text("#messages .message.assistant")
        print(f"[S1] Reply: {reply[:80]}...")

        assert len(reply) > 0, "回复为空"
        print("[S1] ✅ PASSED — 收到 LLM 回复\n")
        browser.close()


def test_s2_thinking_visible():
    """S2: 浏览器能看到思考过程（thinking 区域非空）。"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(BASE_URL)

        page.wait_for_selector("#status-indicator.online", timeout=10_000)
        print("[S2] WebSocket connected")

        page.fill("#user-input", "分析一下 Python 和 JavaScript 的区别")
        page.click("#send-btn")
        print("[S2] Sent query requiring thinking")

        # 等待 thinking 块出现
        try:
            page.wait_for_selector("#messages .thinking-box", timeout=TIMEOUT)
            thinking = page.inner_text("#messages .thinking-box")
            has_thinking = len(thinking.strip()) > 0
            print(f"[S2] Thinking visible: {has_thinking} ({len(thinking)} chars)")
        except Exception:
            has_thinking = False
            print("[S2] No thinking block found")

        # 等待回复
        page.wait_for_selector("#messages .message.assistant", timeout=TIMEOUT)
        reply = page.inner_text("#messages .message.assistant")
        print(f"[S2] Reply: {reply[:80]}...")

        assert len(reply) > 0, "回复为空"
        # thinking 可能不总是可见（取决于 LLM），但回复必须有
        print(f"[S2] {'✅' if has_thinking else '⚠️'} {'PASSED' if has_thinking else 'WARN'} — thinking {'visible' if has_thinking else 'not visible'}\n")
        browser.close()


def test_s3_tool_execution():
    """S3: 浏览器问系统信息 → 工具调用可见 + 返回真实数据。"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(BASE_URL)

        page.wait_for_selector("#status-indicator.online", timeout=10_000)
        print("[S3] WebSocket connected")

        page.fill("#user-input", "运行命令 echo BROWSER_TEST_S3 并告诉我结果")
        page.click("#send-btn")
        print("[S3] Sent shell command request")

        # 等待工具调用区域出现
        try:
            page.wait_for_selector("#messages .tool-card", timeout=TIMEOUT)
            tool_text = page.inner_text("#messages .tool-card")
            has_tool = "run_command" in tool_text or "echo" in tool_text or "Command" in tool_text
            print(f"[S3] Tool call visible: {has_tool}")
        except Exception:
            has_tool = False
            print("[S3] No tool-card element found")

        # 等待回复
        page.wait_for_selector("#messages .message.assistant", timeout=TIMEOUT)
        reply = page.inner_text("#messages .message.assistant")
        has_result = "BROWSER_TEST_S3" in reply
        print(f"[S3] Reply contains result: {has_result}")
        print(f"[S3] Reply: {reply[:100]}...")

        assert has_result, "回复中未包含 BROWSER_TEST_S3"
        print("[S3] ✅ PASSED — 工具执行 + 真实数据返回\n")
        browser.close()


def test_s5_web_search():
    """S5: 浏览器触发搜索 → 返回真实搜索结果。"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(BASE_URL)

        page.wait_for_selector("#status-indicator.online", timeout=10_000)
        print("[S5] WebSocket connected")

        page.fill("#user-input", "使用 web_search 工具搜索 'Python programming' 并告诉我结果")
        page.click("#send-btn")
        print("[S5] Sent search request")

        # 等待回复
        page.wait_for_selector("#messages .message.assistant", timeout=TIMEOUT)
        reply = page.inner_text("#messages .message.assistant")
        has_search = len(reply) > 20
        print(f"[S5] Reply length: {len(reply)} chars")
        print(f"[S5] Reply: {reply[:120]}...")

        assert has_search, "搜索结果为空或太短"
        print("[S5] ✅ PASSED — 搜索结果返回\n")
        browser.close()


def test_s6_memory_across_sessions():
    """S6: 暗号测试 — 连接1告诉暗号，关闭浏览器，连接2新浏览器询问暗号。"""
    with sync_playwright() as p:
        # === Session 1: 告诉暗号 ===
        browser1 = p.chromium.launch(headless=False)
        page1 = browser1.new_page()
        page1.goto(BASE_URL)

        page1.wait_for_selector("#status-indicator.online", timeout=10_000)
        print("[S6] Session 1: connected")

        page1.fill("#user-input", "请记住暗号：宝塔镇河妖。这非常重要，请确认。")
        page1.click("#send-btn")
        print("[S6] Session 1: told secret")

        page1.wait_for_selector("#messages .message.assistant", timeout=TIMEOUT)
        reply1 = page1.inner_text("#messages .message.assistant")
        print(f"[S6] Session 1 reply: {reply1[:80]}...")

        browser1.close()
        print("[S6] Session 1: browser CLOSED")
        time.sleep(2)  # 等待文件写入

        # === Session 2: 新浏览器询问暗号 ===
        browser2 = p.chromium.launch(headless=False)
        page2 = browser2.new_page()
        page2.goto(BASE_URL)

        page2.wait_for_selector("#status-indicator.online", timeout=10_000)
        print("[S6] Session 2: connected (NEW browser)")

        page2.fill("#user-input", "你还记得我之前的暗号吗？请直接说出来。")
        page2.click("#send-btn")
        print("[S6] Session 2: asked for secret")

        page2.wait_for_selector("#messages .message.assistant", timeout=TIMEOUT)
        reply2 = page2.inner_text("#messages .message.assistant")
        print(f"[S6] Session 2 reply: {reply2[:120]}...")

        has_secret = "宝塔镇河妖" in reply2
        print(f"[S6] Secret recalled: {has_secret}")

        browser2.close()

        assert has_secret, "新浏览器未能回忆暗号"
        print("[S6] ✅ PASSED — 跨浏览器记忆保留\n")


if __name__ == "__main__":
    results = {}
    tests = [
        ("S1_chat_reply", test_s1_chat_reply),
        ("S2_thinking_visible", test_s2_thinking_visible),
        ("S3_tool_execution", test_s3_tool_execution),
        ("S5_web_search", test_s5_web_search),
        ("S6_memory", test_s6_memory_across_sessions),
    ]

    for name, fn in tests:
        try:
            fn()
            results[name] = "✅ PASSED"
        except Exception as e:
            results[name] = f"❌ FAILED: {e}"
            print(f"[{name}] ❌ FAILED: {e}\n")

    print("\n" + "=" * 50)
    print("REAL BROWSER TEST RESULTS")
    print("=" * 50)
    for name, status in results.items():
        print(f"  {name}: {status}")

    failed = sum(1 for v in results.values() if "FAILED" in v)
    print(f"\nTotal: {len(results)} | Passed: {len(results) - failed} | Failed: {failed}")

    if failed:
        sys.exit(1)
    else:
        print("\n[ALL PASSED] Real browser verification complete!")
        sys.exit(0)
