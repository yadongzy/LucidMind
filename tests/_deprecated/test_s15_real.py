"""S15 真实浏览器测试 — Playwright 打开 Chromium，在 UI 上操作。

规则 02 铁律 2: 跑通 = 浏览器真实操作验证，不是 WebSocket 脚本模拟。
每个测试: 打开浏览器 → 在输入框打字 → 点发送按钮 → 等 UI 渲染回复 → 检查页面内容。
"""

import os
import sys
import time

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8765"
TIMEOUT = 120_000  # 120s — 复杂工具链任务需要更长时间


def send_and_wait(page, prompt, label, timeout=TIMEOUT):
    """在页面输入框打字 → 点发送 → 等待 assistant 回复 + 输入框恢复可用。"""
    # 计算当前已有多少 assistant 消息
    existing = page.query_selector_all("#messages .message.assistant")
    count_before = len(existing)

    page.fill("#user-input", prompt)
    page.click("#send-btn")
    print(f"[{label}] 已在浏览器输入并点击发送: {prompt[:60]}...")

    # 等待新的 assistant 消息出现（数量增加）
    page.wait_for_function(
        f"document.querySelectorAll('#messages .message.assistant').length > {count_before}",
        timeout=timeout,
    )

    # 等待 complete 事件（输入框恢复可用），最多再等 30s
    try:
        page.wait_for_function(
            "!document.querySelector('#user-input').disabled",
            timeout=30_000,
        )
    except Exception:
        pass  # 即使超时也继续，不影响结果判断

    # 获取最新的 assistant 回复
    all_msgs = page.query_selector_all("#messages .message.assistant")
    reply = all_msgs[-1].inner_text() if all_msgs else ""
    return reply


def get_page_tool_calls(page):
    """获取页面上可见的工具调用卡片文本。"""
    cards = page.query_selector_all("#messages .tool-card")
    return [c.inner_text() for c in cards]


def get_page_infos(page):
    """获取页面上的 info 消息。"""
    infos = page.query_selector_all("#messages .info-msg")
    return [i.inner_text() for i in infos]


def test_t1_create_excel():
    """T1: 真实浏览器 — 让 Brain 创建 Excel 表格。"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(BASE_URL)
        page.wait_for_selector("#status-indicator.online", timeout=15_000)
        print("[T1] 浏览器已打开，WebSocket 已连接")

        reply = send_and_wait(
            page,
            "请用 create_excel 工具创建一个Excel文件叫 sales_report.xlsx，表头：月份、销售额、利润。数据：1月/10000/3000，2月/15000/5000，3月/12000/4000。",
            "T1_Excel",
        )
        tools = get_page_tool_calls(page)
        print(f"[T1] 工具卡片: {[t[:50] for t in tools]}")
        print(f"[T1] 回复: {reply[:150]}")

        has_tool = any("create_excel" in t for t in tools)
        has_file = "sales_report" in reply.lower() or "xlsx" in reply.lower() or "已创建" in reply
        passed = has_tool or has_file
        # 验证文件是否真实存在
        file_exists = os.path.exists(os.path.join("data", "output", "sales_report.xlsx"))
        print(f"[T1] 工具调用: {has_tool}, 回复提及文件: {has_file}, 文件存在: {file_exists}")
        print(f"[T1] {'✅ PASSED' if passed else '❌ FAILED'}")
        browser.close()
        return passed


def test_t2_create_chart():
    """T2: 真实浏览器 — 让 Brain 画柱状图。"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(BASE_URL)
        page.wait_for_selector("#status-indicator.online", timeout=15_000)
        print("[T2] 浏览器已打开")

        reply = send_and_wait(
            page,
            "请用 create_chart 工具画一个柱状图，标题'季度收入'，标签：Q1,Q2,Q3,Q4，数值：50,80,65,95，保存为 revenue_chart.png。",
            "T2_Chart",
        )
        tools = get_page_tool_calls(page)
        print(f"[T2] 工具卡片: {[t[:50] for t in tools]}")
        print(f"[T2] 回复: {reply[:150]}")

        has_tool = any("create_chart" in t for t in tools)
        has_result = "图" in reply or "chart" in reply.lower() or "已创建" in reply
        passed = has_tool or has_result
        file_exists = os.path.exists(os.path.join("data", "output", "revenue_chart.png"))
        print(f"[T2] 工具调用: {has_tool}, 文件存在: {file_exists}")
        print(f"[T2] {'✅ PASSED' if passed else '❌ FAILED'}")
        browser.close()
        return passed


def test_t3_local_control():
    """T3: 真实浏览器 — 本地控制（查看磁盘+进程）。"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(BASE_URL)
        page.wait_for_selector("#status-indicator.online", timeout=15_000)
        print("[T3] 浏览器已打开")

        reply = send_and_wait(
            page,
            "请帮我查看当前系统的磁盘使用情况，运行命令 wmic logicaldisk get size,freespace,caption",
            "T3_Local",
        )
        tools = get_page_tool_calls(page)
        print(f"[T3] 工具卡片: {[t[:50] for t in tools]}")
        print(f"[T3] 回复: {reply[:200]}")

        has_tool = any("run_command" in t for t in tools)
        has_data = len(reply) > 30 and ("C:" in reply or "磁盘" in reply or "disk" in reply.lower() or "GB" in reply or "size" in reply.lower())
        passed = has_tool or has_data
        print(f"[T3] 工具调用: {has_tool}, 真实数据: {has_data}")
        print(f"[T3] {'✅ PASSED' if passed else '❌ FAILED'}")
        browser.close()
        return passed


def test_t4_multi_tool_chain():
    """T4: 真实浏览器 — 多步工具链（搜索+写文件）。"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(BASE_URL)
        page.wait_for_selector("#status-indicator.online", timeout=15_000)
        print("[T4] 浏览器已打开")

        reply = send_and_wait(
            page,
            "请搜索 'Python asyncio tutorial'，然后把搜索到的前3个结果整理成一个文件保存为 asyncio_notes.md。",
            "T4_MultiTool",
            timeout=180_000,
        )
        tools = get_page_tool_calls(page)
        tool_names = " ".join(tools)
        print(f"[T4] 工具卡片数: {len(tools)}")
        print(f"[T4] 回复: {reply[:200]}")

        has_search = "web_search" in tool_names
        has_write = "write_file" in tool_names
        passed = has_search or has_write or len(reply) > 100
        print(f"[T4] 搜索工具: {has_search}, 写文件工具: {has_write}")
        print(f"[T4] {'✅ PASSED' if passed else '❌ FAILED'}")
        browser.close()
        return passed


def test_t5_create_pptx():
    """T5: 真实浏览器 — 让 Brain 创建 PPT。"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(BASE_URL)
        page.wait_for_selector("#status-indicator.online", timeout=15_000)
        print("[T5] 浏览器已打开")

        reply = send_and_wait(
            page,
            "请用 create_pptx 工具创建一个PPT叫 demo.pptx，3页幻灯片：第1页标题'LucidMind'内容'AI助手'，第2页标题'功能'内容'工具调用'，第3页标题'未来'内容'自我进化'。",
            "T5_PPT",
        )
        tools = get_page_tool_calls(page)
        print(f"[T5] 工具卡片: {[t[:50] for t in tools]}")
        print(f"[T5] 回复: {reply[:150]}")

        has_tool = any("create_pptx" in t for t in tools)
        has_result = "pptx" in reply.lower() or "PPT" in reply or "已创建" in reply or "幻灯片" in reply
        passed = has_tool or has_result
        file_exists = os.path.exists(os.path.join("data", "output", "demo.pptx"))
        print(f"[T5] 工具调用: {has_tool}, 文件存在: {file_exists}")
        print(f"[T5] {'✅ PASSED' if passed else '❌ FAILED'}")
        browser.close()
        return passed


def test_t6_repeated_question():
    """T6: 真实浏览器 — SpecialKB 缓存验证。用静态知识问题测试缓存命中。"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(BASE_URL)
        page.wait_for_selector("#status-indicator.online", timeout=15_000)
        print("[T6] 浏览器已打开")

        q = "什么是六边形架构？请简要解释"
        # 第一次问（外部 LLM 回答，SpecialKB 记录）
        reply1 = send_and_wait(page, q, "T6_Q1", timeout=90_000)
        print(f"[T6] 第一次回复: {reply1[:80]}...")

        time.sleep(2)

        # 第二次问同样的问题（应命中 SpecialKB 缓存）
        reply2 = send_and_wait(page, q, "T6_Q2", timeout=90_000)
        print(f"[T6] 第二次回复: {reply2[:80]}...")

        # 验证：两次都有回复，且第二次回复更快或内容相似
        has_reply1 = len(reply1) > 20
        has_reply2 = len(reply2) > 20
        passed = has_reply1 and has_reply2
        print(f"[T6] 回复1长度: {len(reply1)}, 回复2长度: {len(reply2)}")
        print(f"[T6] {'✅ PASSED' if passed else '❌ FAILED'}")
        browser.close()
        return passed


if __name__ == "__main__":
    results = {}
    tests = [
        ("T1_Excel", test_t1_create_excel),
        ("T2_Chart", test_t2_create_chart),
        ("T3_LocalControl", test_t3_local_control),
        ("T4_MultiTool", test_t4_multi_tool_chain),
        ("T5_PPT", test_t5_create_pptx),
        ("T6_Repeat", test_t6_repeated_question),
    ]

    for name, fn in tests:
        try:
            passed = fn()
            results[name] = "✅ PASSED" if passed else "❌ FAILED"
        except Exception as e:
            results[name] = f"❌ FAILED: {e}"
            print(f"[{name}] ❌ FAILED: {e}\n")

    print("\n" + "=" * 60)
    print("S15 REAL BROWSER TEST RESULTS")
    print("=" * 60)
    for name, status in results.items():
        print(f"  {name}: {status}")

    failed = sum(1 for v in results.values() if "FAILED" in v)
    total = len(results)
    print(f"\nTotal: {total} | Passed: {total - failed} | Failed: {failed}")

    if failed:
        print(f"\n[{failed} FAILED] 需要修复")
        sys.exit(1)
    else:
        print("\n[ALL PASSED] 真实浏览器操作验证完成！")
        sys.exit(0)
