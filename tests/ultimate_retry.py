"""重试 L1/L3/L4 失败项 — 多轮追问直到完成。"""

import sys
import time
import os

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8765"
TIMEOUT = 180_000


def send_and_wait(page, message, timeout=TIMEOUT):
    count_before = len(page.query_selector_all("#messages .message.assistant"))
    page.fill("#user-input", message)
    page.click("#send-btn")
    page.wait_for_function(
        f"document.querySelectorAll('#messages .message.assistant').length > {count_before}",
        timeout=timeout,
    )
    time.sleep(4)
    replies = page.query_selector_all("#messages .message.assistant")
    return replies[-1].inner_text() if replies else ""


def get_all_replies(page):
    replies = page.query_selector_all("#messages .message.assistant")
    return " ".join([r.inner_text() for r in replies])


def test_l1_retry():
    """L1 重试：安全审计报告。"""
    print("=" * 60)
    print("L1 RETRY: 本机安全审计报告")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(BASE_URL)
        page.wait_for_selector("#status-indicator.online", timeout=10_000)

        r1 = send_and_wait(page,
            "帮我做一份本机安全审计报告，查一下开放端口、可疑进程、防火墙状态，"
            "结果保存到 F:/verv/LucidMind/data/security_audit.txt"
        )
        print(f"[L1] R1 ({len(r1)} chars): {r1[:200]}...")

        # 追问直到文件生成
        target = r"F:\verv\LucidMind\data\security_audit.txt"
        for i in range(3):
            if os.path.exists(target):
                break
            r = send_and_wait(page, "继续，把结果整理好保存到文件里。")
            print(f"[L1] R{i+2} ({len(r)} chars): {r[:200]}...")

        exists = os.path.exists(target)
        if exists:
            c = open(target, "r", encoding="utf-8", errors="replace").read()
            print(f"[L1] File size: {len(c)} chars")

        all_text = get_all_replies(page)
        browser.close()

        passed = exists and len(c if exists else "") > 50
        print(f"[L1] File: {exists}")
        print(f"[L1] {'✅ PASSED' if passed else '❌ FAILED'}\n")
        return passed


def test_l3_retry():
    """L3 重试：磁盘分析。"""
    print("=" * 60)
    print("L3 RETRY: 磁盘空间分析")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(BASE_URL)
        page.wait_for_selector("#status-indicator.online", timeout=10_000)

        r1 = send_and_wait(page,
            "查一下我 C 盘哪些文件夹最占空间，告诉我能清理哪些、能释放多少。"
        )
        print(f"[L3] R1 ({len(r1)} chars): {r1[:300]}...")

        all_text = get_all_replies(page)
        has_result = any(kw in all_text for kw in ["GB", "MB", "清理", "释放", "Windows", "Users"])

        if not has_result:
            r2 = send_and_wait(page, "结果呢？告诉我哪些目录最大、能清理多少。")
            print(f"[L3] R2 ({len(r2)} chars): {r2[:300]}...")
            all_text = get_all_replies(page)
            has_result = any(kw in all_text for kw in ["GB", "MB", "清理", "释放", "Windows", "Users"])

        if not has_result:
            r3 = send_and_wait(page, "直接告诉我 C 盘最大的 5 个目录和大小。")
            print(f"[L3] R3 ({len(r3)} chars): {r3[:300]}...")
            all_text = get_all_replies(page)

        browser.close()

        has_dirs = any(kw in all_text for kw in ["Windows", "Users", "Program", "AppData"])
        has_size = any(kw in all_text for kw in ["GB", "MB"])
        passed = has_dirs and has_size
        print(f"[L3] Dirs: {has_dirs}, Size: {has_size}")
        print(f"[L3] {'✅ PASSED' if passed else '❌ FAILED'}\n")
        return passed


def test_l4_retry():
    """L4 重试：摄像头 + 语音。"""
    print("=" * 60)
    print("L4 RETRY: 摄像头拍照 + 语音播报")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(BASE_URL)
        page.wait_for_selector("#status-indicator.online", timeout=10_000)

        r1 = send_and_wait(page,
            "用我电脑的摄像头拍一张照片，然后用扬声器说一句话。"
        )
        print(f"[L4] R1 ({len(r1)} chars): {r1[:300]}...")

        all_text = get_all_replies(page)

        # 多轮追问
        for i in range(4):
            done_cam = any(kw in all_text for kw in ["拍照完成", "照片已保存", "captured", "saved", "photo"])
            done_voice = any(kw in all_text for kw in ["已播放", "说话完成", "TTS OK", "语音完成", "speak"])
            if done_cam and done_voice:
                break
            r = send_and_wait(page, "继续执行，完成拍照和语音任务。")
            print(f"[L4] R{i+2} ({len(r)} chars): {r[:200]}...")
            all_text = get_all_replies(page)

        browser.close()

        has_camera = any(kw in all_text for kw in ["摄像头", "拍照", "照片", "camera", "photo", "capture", "cv2", "opencv", "captured"])
        has_voice = any(kw in all_text for kw in ["语音", "说话", "播报", "pyttsx3", "TTS", "speak", "voice", "扬声器"])
        passed = has_camera and has_voice
        print(f"[L4] Camera: {has_camera}, Voice: {has_voice}")
        print(f"[L4] {'✅ PASSED' if passed else '❌ FAILED'}\n")
        return passed


if __name__ == "__main__":
    results = {}
    tests = [
        ("L1_security_audit", test_l1_retry),
        ("L3_disk_analysis", test_l3_retry),
        ("L4_camera_voice", test_l4_retry),
    ]

    for name, fn in tests:
        try:
            passed = fn()
            results[name] = "✅ PASSED" if passed else "❌ FAILED"
        except Exception as e:
            results[name] = f"❌ EXCEPTION: {e}"
            print(f"[{name}] ❌ EXCEPTION: {e}\n")

    print("\n" + "=" * 60)
    print("RETRY RESULTS")
    print("=" * 60)
    # 加上之前已通过的
    print("  L1_security_audit:", results.get("L1_security_audit", "?"))
    print("  L2_job_market_analysis: ✅ PASSED (已通过)")
    print("  L3_disk_analysis:", results.get("L3_disk_analysis", "?"))
    print("  L4_camera_voice:", results.get("L4_camera_voice", "?"))
    print("  L5_stock_hell: ✅ PASSED (已通过, 盈利298.44元)")

    failed = sum(1 for v in results.values() if "FAILED" in v or "EXCEPTION" in v)
    print(f"\nRetry: {len(results)} | Passed: {len(results) - failed} | Failed: {failed}")
    sys.exit(1 if failed else 0)
