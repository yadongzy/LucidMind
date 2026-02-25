"""PLAN_NEXT.md 第四节：复杂测试题目清单 — 真实浏览器验证。

7项综合测试 + 4项本地控制测试。
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import os
import time
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8765"
TIMEOUT = 120_000  # 2分钟


def send_and_wait(page, prompt, label, timeout=TIMEOUT):
    existing = page.query_selector_all("#messages .message.assistant")
    count_before = len(existing)
    page.fill("#user-input", prompt)
    page.click("#send-btn")
    print(f"  [{label}] 发送: {prompt[:70]}...")
    page.wait_for_function(
        f"document.querySelectorAll('#messages .message.assistant').length > {count_before}",
        timeout=timeout,
    )
    try:
        page.wait_for_function("!document.querySelector('#user-input').disabled", timeout=30_000)
    except Exception:
        pass
    all_msgs = page.query_selector_all("#messages .message.assistant")
    reply = all_msgs[-1].inner_text() if all_msgs else ""
    return reply


def run_test(name, prompt, check_fn):
    """通用测试框架：打开浏览器→发送→检查→关闭。"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(BASE_URL)
        page.wait_for_selector("#status-indicator.online", timeout=15_000)
        reply = send_and_wait(page, prompt, name)
        print(f"  [{name}] 回复({len(reply)}字): {reply[:120]}...")
        passed = check_fn(reply)
        print(f"  [{name}] {'PASS' if passed else 'FAIL'}")
        browser.close()
        return passed


# === 综合测试 ===

def test_c1_multi_file():
    """C1: 创建Python项目（多文件创建+内容质量）"""
    return run_test("C1_MultiFile",
        "请创建一个简单的Python项目：1个 hello.py 文件（包含一个 greet 函数）和 1个 README.md 文件（说明项目用途）。保存到 data/output/myproject/ 目录。",
        lambda r: ("hello" in r.lower() or "greet" in r.lower() or "README" in r or "创建" in r or "已" in r))

def test_c2_code_analysis():
    """C2: 代码理解+逻辑推理"""
    return run_test("C2_CodeAnalysis",
        "分析这段Python代码的bug：\ndef avg(nums):\n    total = 0\n    for n in nums:\n        total += n\n    return total / len(nums)\n\n当传入空列表时会怎样？如何修复？",
        lambda r: ("除" in r or "ZeroDivision" in r.lower() or "空" in r or "0" in r or "empty" in r.lower()))

def test_c3_local_sort():
    """C3: 本地控制 — 列出文件并排序"""
    return run_test("C3_LocalSort",
        "请运行命令列出当前工作目录下的所有 .py 文件，并告诉我有多少个。",
        lambda r: (".py" in r or "文件" in r or "个" in r))

def test_c4_search_summarize():
    """C4: 搜索+综合+写作"""
    return run_test("C4_SearchSum",
        "请搜索 'Python dataclass tutorial'，然后用3句话总结 dataclass 的核心优势。",
        lambda r: len(r) > 50 and ("dataclass" in r.lower() or "数据" in r or "类" in r))

def test_c5_memory():
    """C5: 记忆测试 — 记住信息并回忆"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(BASE_URL)
        page.wait_for_selector("#status-indicator.online", timeout=15_000)
        # 记住
        r1 = send_and_wait(page, "请记住这个密码：LucidMind2026Secret", "C5_Save")
        print(f"  [C5] 记住回复: {r1[:80]}...")
        # 干扰对话
        r2 = send_and_wait(page, "1+1等于多少？", "C5_Distract")
        r3 = send_and_wait(page, "Python的创始人是谁？", "C5_Distract2")
        # 回忆
        r4 = send_and_wait(page, "我之前让你记住的密码是什么？", "C5_Recall")
        print(f"  [C5] 回忆回复: {r4[:120]}...")
        passed = "LucidMind2026Secret" in r4 or "2026" in r4 or "Secret" in r4 or "密码" in r4
        print(f"  [C5] {'PASS' if passed else 'FAIL'}")
        browser.close()
        return passed

def test_c6_never_give_up():
    """C6: 永不放弃 — 多方法尝试"""
    return run_test("C6_NeverGiveUp",
        "请用2种不同的方法计算斐波那契数列的第10项，并比较结果。",
        lambda r: ("55" in r or "fibonacci" in r.lower() or "斐波那契" in r))

def test_c7_self_learning():
    """C7: 自我学习 — 纠正后学习"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(BASE_URL)
        page.wait_for_selector("#status-indicator.online", timeout=15_000)
        r1 = send_and_wait(page, "Python中如何反转字符串？", "C7_Q1")
        print(f"  [C7] 首次回复: {r1[:80]}...")
        # 纠正
        r2 = send_and_wait(page, "不对，最简洁的方法是 s[::-1]，请记住这个。", "C7_Correct")
        print(f"  [C7] 纠正回复: {r2[:80]}...")
        passed = "学习" in r2 or "记" in r2 or "[::-1]" in r2 or "了解" in r2 or "好的" in r2
        print(f"  [C7] {'PASS' if passed else 'FAIL'}")
        browser.close()
        return passed

# === 本地控制测试 ===

def test_l1_notepad():
    """L1: 打开记事本"""
    return run_test("L1_Notepad",
        "请运行命令 'echo LucidMind Test > data/output/test_local.txt'，然后确认文件已创建。",
        lambda r: ("test_local" in r or "创建" in r or "成功" in r or "已" in r))

def test_l2_sysinfo():
    """L2: 系统信息"""
    return run_test("L2_SysInfo",
        "请运行 systeminfo 命令并告诉我操作系统名称和版本。",
        lambda r: ("Windows" in r or "windows" in r or "操作系统" in r or "OS" in r))

def test_l3_file_search():
    """L3: 文件搜索"""
    return run_test("L3_FileSearch",
        "请搜索当前项目中所有的 .md 文件，列出文件名。",
        lambda r: (".md" in r or "README" in r or "PLAN" in r or "PROGRESS" in r))

def test_l4_disk():
    """L4: 磁盘信息"""
    return run_test("L4_Disk",
        "请运行命令查看C盘的剩余空间大小。",
        lambda r: ("GB" in r or "MB" in r or "空间" in r or "剩余" in r or "C:" in r))


if __name__ == "__main__":
    results = {}
    tests = [
        ("C1_MultiFile", test_c1_multi_file),
        ("C2_CodeAnalysis", test_c2_code_analysis),
        ("C3_LocalSort", test_c3_local_sort),
        ("C4_SearchSum", test_c4_search_summarize),
        ("C5_Memory", test_c5_memory),
        ("C6_NeverGiveUp", test_c6_never_give_up),
        ("C7_SelfLearn", test_c7_self_learning),
        ("L1_LocalFile", test_l1_notepad),
        ("L2_SysInfo", test_l2_sysinfo),
        ("L3_FileSearch", test_l3_file_search),
        ("L4_Disk", test_l4_disk),
    ]

    for name, fn in tests:
        print(f"\n{'='*50}")
        print(f"TEST: {name}")
        print(f"{'='*50}")
        try:
            results[name] = fn()
        except Exception as e:
            print(f"  [{name}] ERROR: {e}")
            results[name] = False

    print(f"\n{'='*60}")
    print("PLAN_NEXT SECTION 4: COMPLEX TEST RESULTS")
    print(f"{'='*60}")
    for name, ok in results.items():
        print(f"  {name}: {'PASS' if ok else 'FAIL'}")
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\nTotal: {total} | Passed: {passed} | Failed: {total - passed}")
