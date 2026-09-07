"""终极压力测试 v2 — 闭卷考试，只给目标不给方法。

Brain 必须自己分析任务、选择工具、解决问题。
"""

import sys
import time
import os

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8765"
TIMEOUT = 180_000  # 3 分钟


def send_and_wait(page, message, timeout=TIMEOUT):
    """发送消息并等待回复完成。"""
    page.fill("#user-input", message)
    page.click("#send-btn")
    page.wait_for_selector("#messages .message.assistant:last-child", timeout=timeout)
    time.sleep(3)
    replies = page.query_selector_all("#messages .message.assistant")
    return replies[-1].inner_text() if replies else ""


def followup(page, message, timeout=TIMEOUT):
    """追问，等待新回复。"""
    count_before = len(page.query_selector_all("#messages .message.assistant"))
    page.fill("#user-input", message)
    page.click("#send-btn")
    # 等待新的 assistant 消息出现
    page.wait_for_function(
        f"document.querySelectorAll('#messages .message.assistant').length > {count_before}",
        timeout=timeout,
    )
    time.sleep(3)
    replies = page.query_selector_all("#messages .message.assistant")
    return replies[-1].inner_text() if replies else ""


def test_l1():
    """L1: 帮我生成一份本机的安全审计报告，保存到桌面。"""
    print("=" * 60)
    print("L1: 本机安全审计报告")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(BASE_URL)
        page.wait_for_selector("#status-indicator.online", timeout=10_000)

        reply = send_and_wait(page,
            "帮我生成一份本机的安全审计报告，包括开放端口、运行中的可疑进程、"
            "防火墙状态、最近的登录记录。报告保存到 F:/verv/LucidMind/data/security_audit.txt"
        )
        print(f"[L1] Reply ({len(reply)} chars): {reply[:300]}...")

        exists = os.path.exists(r"F:\verv\LucidMind\data\security_audit.txt")
        print(f"[L1] Report file exists: {exists}")
        if exists:
            c = open(r"F:\verv\LucidMind\data\security_audit.txt", "r", encoding="utf-8", errors="replace").read()
            has_content = len(c) > 100
            print(f"[L1] Report size: {len(c)} chars")
        else:
            has_content = False

        browser.close()
        passed = exists and has_content
        print(f"[L1] {'✅ PASSED' if passed else '❌ FAILED'}\n")
        return passed


def test_l2():
    """L2: 对比分析两个编程语言的就业市场。"""
    print("=" * 60)
    print("L2: 编程语言就业市场对比分析")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(BASE_URL)
        page.wait_for_selector("#status-indicator.online", timeout=10_000)

        reply = send_and_wait(page,
            "帮我调研 Rust 和 Go 在 2025 年的就业市场情况，"
            "包括薪资水平、岗位数量、主要招聘公司、技术趋势。"
            "给出你的结论：如果我现在要转行，应该学哪个？为什么？"
        )
        print(f"[L2] Reply ({len(reply)} chars): {reply[:400]}...")

        has_both = ("Rust" in reply or "rust" in reply) and ("Go" in reply or "go " in reply.lower())
        has_conclusion = any(kw in reply for kw in ["结论", "建议", "推荐", "应该学", "选择"])
        has_depth = len(reply) > 300

        browser.close()
        passed = has_both and has_conclusion and has_depth
        print(f"[L2] Both languages: {has_both}, Conclusion: {has_conclusion}, Depth: {has_depth}")
        print(f"[L2] {'✅ PASSED' if passed else '❌ FAILED'}\n")
        return passed


def test_l3():
    """L3: 找出我电脑上最占空间的 5 个文件夹，并生成清理建议。"""
    print("=" * 60)
    print("L3: 磁盘空间分析 + 清理建议")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(BASE_URL)
        page.wait_for_selector("#status-indicator.online", timeout=10_000)

        reply = send_and_wait(page,
            "分析我 C 盘的磁盘使用情况，找出占用空间最大的 5 个目录，"
            "告诉我哪些可以安全清理，预计能释放多少空间。"
        )
        print(f"[L3] Reply ({len(reply)} chars): {reply[:400]}...")

        has_dirs = any(kw in reply for kw in ["Windows", "Users", "Program", "AppData", "C:\\", "C:/", "GB", "MB"])
        has_advice = any(kw in reply for kw in ["清理", "删除", "释放", "建议", "可以"])
        has_size = any(kw in reply for kw in ["GB", "MB", "字节", "空间"])

        browser.close()
        passed = has_dirs and has_advice and has_size
        print(f"[L3] Has dirs: {has_dirs}, Has advice: {has_advice}, Has size: {has_size}")
        print(f"[L3] {'✅ PASSED' if passed else '❌ FAILED'}\n")
        return passed


def test_l4():
    """L4: 打开摄像头拍一张照片，然后用语音告诉我拍到了什么。"""
    print("=" * 60)
    print("L4: 摄像头拍照 + 语音播报")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(BASE_URL)
        page.wait_for_selector("#status-indicator.online", timeout=10_000)

        reply = send_and_wait(page,
            "打开我电脑的摄像头拍一张照片保存下来，然后用电脑的扬声器说一句话告诉我拍照完成了。"
        )
        print(f"[L4] Reply ({len(reply)} chars): {reply[:400]}...")

        # 如果 Brain 说需要安装库，让它自己装
        if "安装" in reply or "install" in reply.lower() or "pip" in reply:
            print("[L4] Brain 需要安装依赖，追问...")
            reply2 = followup(page, "那就装吧，装完之后执行任务。")
            print(f"[L4] Follow-up ({len(reply2)} chars): {reply2[:300]}...")
            reply = reply + " " + reply2

        # 检查是否有照片文件
        photo_found = False
        for ext in [".jpg", ".png", ".bmp"]:
            for root, dirs, files in os.walk(r"F:\verv\LucidMind\data"):
                for f in files:
                    if f.endswith(ext) and "photo" in f.lower() or "capture" in f.lower() or "cam" in f.lower():
                        photo_found = True
                        print(f"[L4] Photo found: {os.path.join(root, f)}")
                        break

        has_camera = any(kw in reply for kw in ["摄像头", "拍照", "照片", "camera", "photo", "capture", "cv2", "opencv"])
        has_voice = any(kw in reply for kw in ["语音", "说话", "播报", "pyttsx3", "TTS", "speak", "voice", "扬声器"])

        browser.close()
        passed = has_camera and has_voice
        print(f"[L4] Camera: {has_camera}, Voice: {has_voice}, Photo file: {photo_found}")
        print(f"[L4] {'✅ PASSED' if passed else '❌ FAILED'}\n")
        return passed


def test_l5():
    """L5: 地狱测试 — 用真实股票数据模拟交易盈利 100 元。"""
    print("=" * 60)
    print("L5: 地狱测试 — 股票模拟盈利 100 元")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(BASE_URL)
        page.wait_for_selector("#status-indicator.online", timeout=10_000)

        reply = send_and_wait(page,
            "我给你 10000 元虚拟资金。你去网上查真实的股票行情数据，"
            "然后做模拟交易，目标是盈利至少 100 元。\n"
            "要求：必须用真实查到的股票涨跌幅数据，不能编造。"
            "交易过程和最终盈亏必须清楚展示。不达标不许停。",
            timeout=300_000,
        )
        print(f"[L5] Round 1 ({len(reply)} chars): {reply[:500]}...")

        # 检查是否完成
        has_profit = any(kw in reply for kw in ["盈利", "利润", "赚", "收益", "profit"])
        has_100 = "100" in reply

        if not (has_profit and has_100):
            print("[L5] Round 1 未完成，追问...")
            reply2 = followup(page,
                "结果呢？盈利了多少？如果不到 100 元就继续想办法。",
                timeout=300_000,
            )
            print(f"[L5] Round 2 ({len(reply2)} chars): {reply2[:500]}...")
            reply = reply + " " + reply2
            has_profit = any(kw in reply for kw in ["盈利", "利润", "赚", "收益", "profit"])
            has_100 = "100" in reply

        if not (has_profit and has_100):
            print("[L5] Round 2 未完成，最后追问...")
            reply3 = followup(page,
                "不要放弃。告诉我最终盈亏数字。",
                timeout=300_000,
            )
            print(f"[L5] Round 3 ({len(reply3)} chars): {reply3[:500]}...")
            reply = reply + " " + reply3
            has_profit = any(kw in reply for kw in ["盈利", "利润", "赚", "收益", "profit"])
            has_100 = "100" in reply

        browser.close()
        passed = has_profit and has_100
        print(f"[L5] Profit mentioned: {has_profit}, 100 mentioned: {has_100}")
        print(f"[L5] {'✅ PASSED' if passed else '❌ FAILED'}\n")
        return passed


if __name__ == "__main__":
    results = {}
    tests = [
        ("L1_security_audit", test_l1),
        ("L2_job_market_analysis", test_l2),
        ("L3_disk_analysis", test_l3),
        ("L4_camera_voice", test_l4),
        ("L5_stock_hell", test_l5),
    ]

    for name, fn in tests:
        try:
            passed = fn()
            results[name] = "✅ PASSED" if passed else "❌ FAILED"
        except Exception as e:
            results[name] = f"❌ EXCEPTION: {e}"
            print(f"[{name}] ❌ EXCEPTION: {e}\n")

    print("\n" + "=" * 60)
    print("ULTIMATE TEST v2 — 闭卷考试结果")
    print("=" * 60)
    for name, status in results.items():
        print(f"  {name}: {status}")

    failed = sum(1 for v in results.values() if "FAILED" in v or "EXCEPTION" in v)
    total = len(results)
    print(f"\nTotal: {total} | Passed: {total - failed} | Failed: {failed}")

    if failed == 0:
        print("\n🔥 ALL PASSED — LucidMind 闭卷考试全部通过！")
    sys.exit(1 if failed else 0)
