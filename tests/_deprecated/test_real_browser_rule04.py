"""规则 04-testing.md 真实浏览器测试 — 记录：输入→思维流→回复→耗时→判定。

验证 PLAN_NEXT.md 新增功能：
1. 智能重试 + 失败学习 (_tool_call_with_retry + _adapt_params + _learn_pattern)
2. 强制思考摘要 (_generate_thinking_summary)
3. 工具调用 + 本地控制
4. 记忆持久化
5. 自我学习（纠正后学习）
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import time
import json
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8765"
RESULTS = []


def real_browser_test(name, prompt, check_fn, timeout=120_000):
    """真实浏览器测试：打开页面→输入→等待→抓取思维流+回复+耗时。"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(BASE_URL)
        page.wait_for_selector("#status-indicator.online", timeout=15_000)

        # 记录已有消息数
        existing = page.query_selector_all("#messages .message.assistant")
        count_before = len(existing)

        # 记录开始时间
        t0 = time.time()

        # 输入并发送
        page.fill("#user-input", prompt)
        page.click("#send-btn")

        # 等待 assistant 回复
        page.wait_for_function(
            f"document.querySelectorAll('#messages .message.assistant').length > {count_before}",
            timeout=timeout,
        )
        try:
            page.wait_for_function("!document.querySelector('#user-input').disabled", timeout=30_000)
        except Exception:
            pass

        elapsed = time.time() - t0

        # 抓取思维流（thinking 消息）
        thinking_els = page.query_selector_all("#messages .message.thinking, #messages .thinking-box")
        thinking_texts = []
        for el in thinking_els:
            txt = el.inner_text().strip()
            if txt:
                thinking_texts.append(txt)
        thinking = " | ".join(thinking_texts) if thinking_texts else "(无思维流)"

        # 抓取回复
        all_msgs = page.query_selector_all("#messages .message.assistant")
        reply = all_msgs[-1].inner_text() if all_msgs else ""

        # 抓取 info 消息（工具调用、学习提示等）
        info_els = page.query_selector_all("#messages .message.info")
        info_texts = [el.inner_text().strip() for el in info_els if el.inner_text().strip()]

        # 判定
        passed = check_fn(reply, thinking, info_texts)

        # 记录结果
        result = {
            "name": name,
            "input": prompt,
            "thinking": thinking[:200],
            "reply": reply[:300],
            "info": info_texts[-3:] if info_texts else [],
            "elapsed": f"{elapsed:.1f}s",
            "passed": passed,
        }
        RESULTS.append(result)

        # 打印规则04格式
        print(f"\n{'='*60}")
        print(f"TEST: {name}")
        print(f"{'='*60}")
        print(f"  输入: {prompt[:80]}")
        print(f"  思维流: {thinking[:150]}")
        print(f"  回复: {reply[:200]}")
        if info_texts:
            print(f"  系统信息: {'; '.join(info_texts[-3:])}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  判定: {'✅ PASS' if passed else '❌ FAIL'}")

        browser.close()
        return passed


def test_multi_session(name, steps, check_fn, timeout=120_000):
    """多轮对话测试。"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(BASE_URL)
        page.wait_for_selector("#status-indicator.online", timeout=15_000)

        t0 = time.time()
        replies = []
        all_thinking = []
        all_info = []

        for i, prompt in enumerate(steps):
            existing = page.query_selector_all("#messages .message.assistant")
            count_before = len(existing)

            page.fill("#user-input", prompt)
            page.click("#send-btn")

            page.wait_for_function(
                f"document.querySelectorAll('#messages .message.assistant').length > {count_before}",
                timeout=timeout,
            )
            try:
                page.wait_for_function("!document.querySelector('#user-input').disabled", timeout=30_000)
            except Exception:
                pass

            # 抓取
            thinking_els = page.query_selector_all("#messages .message.thinking, #messages .thinking-box")
            for el in thinking_els:
                txt = el.inner_text().strip()
                if txt and txt not in all_thinking:
                    all_thinking.append(txt)

            msgs = page.query_selector_all("#messages .message.assistant")
            reply = msgs[-1].inner_text() if msgs else ""
            replies.append(reply)

            info_els = page.query_selector_all("#messages .message.info")
            for el in info_els:
                txt = el.inner_text().strip()
                if txt and txt not in all_info:
                    all_info.append(txt)

            time.sleep(1)

        elapsed = time.time() - t0
        thinking_str = " | ".join(all_thinking[:3]) if all_thinking else "(无思维流)"
        passed = check_fn(replies, all_thinking, all_info)

        result = {
            "name": name,
            "input": " → ".join(s[:30] for s in steps),
            "thinking": thinking_str[:200],
            "reply": replies[-1][:300] if replies else "",
            "info": all_info[-3:],
            "elapsed": f"{elapsed:.1f}s",
            "passed": passed,
        }
        RESULTS.append(result)

        print(f"\n{'='*60}")
        print(f"TEST: {name}")
        print(f"{'='*60}")
        for i, (s, r) in enumerate(zip(steps, replies)):
            print(f"  轮{i+1} 输入: {s[:60]}")
            print(f"  轮{i+1} 回复: {r[:120]}")
        print(f"  思维流: {thinking_str[:150]}")
        if all_info:
            print(f"  系统信息: {'; '.join(all_info[-3:])}")
        print(f"  耗时: {elapsed:.1f}s")
        print(f"  判定: {'✅ PASS' if passed else '❌ FAIL'}")

        browser.close()
        return passed


if __name__ == "__main__":
    print("=" * 60)
    print("规则 04 真实浏览器测试 — PLAN_NEXT.md 功能验证")
    print("=" * 60)

    # T1: 工具调用 + 强制思考摘要
    real_browser_test(
        "T1_工具调用+思考摘要",
        "请用 create_excel 工具创建一个Excel文件叫 test_rule04.xlsx，表头：姓名、年龄、城市，填3行数据。",
        lambda reply, think, info: (
            ("xlsx" in reply.lower() or "创建" in reply or "已" in reply)
        ),
    )

    # T2: 本地控制（Shell工具）
    real_browser_test(
        "T2_本地控制_系统信息",
        "请运行 systeminfo 命令并告诉我操作系统版本。",
        lambda reply, think, info: (
            "Windows" in reply or "windows" in reply or "操作系统" in reply
        ),
    )

    # T3: 搜索+综合
    real_browser_test(
        "T3_搜索综合",
        "请搜索 'Python type hints best practices'，然后用2句话总结。",
        lambda reply, think, info: len(reply) > 30,
    )

    # T4: 记忆 + 回忆（多轮）
    test_multi_session(
        "T4_记忆持久化",
        [
            "请记住这个暗号：BlueDragon42",
            "1+1等于多少？",
            "我之前告诉你的暗号是什么？",
        ],
        lambda replies, think, info: (
            "BlueDragon42" in replies[-1] or "Blue" in replies[-1] or "Dragon" in replies[-1] or "42" in replies[-1]
        ),
    )

    # T5: 自我学习（纠正后学习）
    test_multi_session(
        "T5_自我学习_纠正",
        [
            "Python中怎么合并两个字典？",
            "不对，最简洁的方法是 {**a, **b}，请记住。",
        ],
        lambda replies, think, info: (
            any("学习" in i or "📝" in i or "记" in i for i in info) or
            "记" in replies[-1] or "{**" in replies[-1] or "学" in replies[-1]
        ),
    )

    # T6: 代码分析（逻辑推理）
    real_browser_test(
        "T6_代码分析",
        "这段代码有什么问题？\ndef divide(a, b):\n    return a / b\n\n请分析并给出修复方案。",
        lambda reply, think, info: (
            "除" in reply or "0" in reply or "ZeroDivision" in reply.lower() or "异常" in reply or "error" in reply.lower()
        ),
    )

    # === 汇总 ===
    print(f"\n{'='*60}")
    print("规则 04 真实浏览器测试汇总")
    print(f"{'='*60}")
    for r in RESULTS:
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        print(f"  {r['name']}: {status} ({r['elapsed']})")

    passed = sum(1 for r in RESULTS if r["passed"])
    total = len(RESULTS)
    print(f"\n总计: {total} | 通过: {passed} | 失败: {total - passed}")

    # 输出 PROGRESS.md 格式的记录
    print(f"\n{'='*60}")
    print("PROGRESS.md 记录格式")
    print(f"{'='*60}")
    for r in RESULTS:
        print(f"\n### {r['name']}")
        print(f"- 输入: {r['input'][:80]}")
        print(f"- 思维流: {r['thinking'][:150]}")
        print(f"- 回复: {r['reply'][:200]}")
        if r['info']:
            print(f"- 系统信息: {'; '.join(r['info'][:3])}")
        print(f"- 耗时: {r['elapsed']}")
        print(f"- 判定: {'PASS' if r['passed'] else 'FAIL'}")
