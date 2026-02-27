"""S39-S41 全真实浏览器测试。
T1: 向量检索(S39) — 记忆检索API正常+降级不崩溃
T2: 多用户隔离(S40) — UserIsolator模块可导入+功能正确
T3: 部署方案(S41) — Dockerfile存在+API健康检查
T4: 综合 — 浏览器对话+大脑面板+工具列表
"""
import sys, time, requests, importlib
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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

    # ===== T1: 向量检索模块 =====
    t0 = time.time()
    try:
        from adapters.memory.vector_store import VectorStore, get_vector_store
        vs = get_vector_store()
        # 测试基本功能（即使没有模型也不应崩溃）
        available = vs.is_available()
        # 测试语义搜索降级
        items = [{"id": "1", "text": "天空是蓝色的"}, {"id": "2", "text": "太阳是红色的"}]
        search_result = vs.semantic_search("蓝天", items, ["text"], limit=2)
        # 无论模型是否可用，都不应崩溃
        t1_ok = True
        model_status = "可用" if available else "降级(BM25)"
    except Exception as e:
        t1_ok = False
        model_status = f"错误: {e}"
    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"T1: 向量检索模块 (S39)")
    print(f"{'='*60}")
    print(f"  向量模型: {model_status}")
    print(f"  模块导入: {'✅' if t1_ok else '❌'}")
    print(f"  耗时: {elapsed:.1f}s")
    print(f"  判定: {'✅ PASS' if t1_ok else '❌ FAIL'}")
    results.append(("T1-向量检索(S39)", t1_ok))

    # ===== T2: 多用户隔离 =====
    t0 = time.time()
    try:
        from adapters.auth.user_isolator import UserIsolator, get_isolator
        iso = get_isolator()
        # 注册两个用户
        u1 = iso.register_or_get("alice")
        u2 = iso.register_or_get("bob")
        # 生成隔离session
        s1 = iso.get_isolated_session_id("alice", "chat1")
        s2 = iso.get_isolated_session_id("bob", "chat1")
        # 验证隔离
        isolated = s1 != s2 and "alice" not in s2 and "bob" not in s1
        stats = iso.get_stats()
        t2_ok = isolated and stats["total_users"] >= 2
    except Exception as e:
        t2_ok = False
        isolated = False
        stats = {"error": str(e)}
    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"T2: 多用户隔离 (S40)")
    print(f"{'='*60}")
    print(f"  Alice session: {s1 if t2_ok else 'N/A'}")
    print(f"  Bob session: {s2 if t2_ok else 'N/A'}")
    print(f"  隔离验证: {'✅' if isolated else '❌'}")
    print(f"  用户数: {stats.get('total_users', 0)}")
    print(f"  耗时: {elapsed:.1f}s")
    print(f"  判定: {'✅ PASS' if t2_ok else '❌ FAIL'}")
    results.append(("T2-多用户隔离(S40)", t2_ok))

    # ===== T3: 部署方案 =====
    t0 = time.time()
    dockerfile_exists = (ROOT / "Dockerfile").exists()
    compose_exists = (ROOT / "docker-compose.yml").exists()
    # 验证 Dockerfile 内容
    if dockerfile_exists:
        content = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        has_healthcheck = "HEALTHCHECK" in content
        has_port = "8765" in content
    else:
        has_healthcheck = False
        has_port = False
    # 验证 API 健康检查
    try:
        res = requests.get(f"{BASE}/api/health", timeout=5)
        health_ok = res.json().get("status") == "ok"
    except Exception:
        health_ok = False
    elapsed = time.time() - t0
    t3_ok = dockerfile_exists and compose_exists and has_healthcheck and health_ok
    print(f"\n{'='*60}")
    print(f"T3: 部署方案 (S41)")
    print(f"{'='*60}")
    print(f"  Dockerfile: {'✅' if dockerfile_exists else '❌'}")
    print(f"  docker-compose.yml: {'✅' if compose_exists else '❌'}")
    print(f"  HEALTHCHECK: {'✅' if has_healthcheck else '❌'}")
    print(f"  API /health: {'✅' if health_ok else '❌'}")
    print(f"  耗时: {elapsed:.1f}s")
    print(f"  判定: {'✅ PASS' if t3_ok else '❌ FAIL'}")
    results.append(("T3-部署方案(S41)", t3_ok))

    # ===== T4: 综合浏览器验证 =====
    t0 = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(BASE)
        page.wait_for_selector("#status-indicator.online", timeout=15000)
        time.sleep(2)

        # 发消息验证完整流程
        page.fill("#user-input", "你好")
        page.click("#send-btn")
        reply = wait_reply(page, 30)
        has_reply = len(reply) > 5

        # 验证工具列表包含新工具
        for _ in range(10):
            tool_list = page.query_selector("#dev-tool-list")
            tool_names = tool_list.inner_text() if tool_list else ""
            if "speech_to_text" in tool_names: break
            time.sleep(0.5)
        has_stt = "speech_to_text" in tool_names

        # 验证大脑面板
        brain_btn = page.query_selector('.activity-item[title="大脑状态 (Brain)"]')
        has_brain_btn = brain_btn is not None

        browser.close()

    elapsed = time.time() - t0
    t4_ok = has_reply and has_stt and has_brain_btn
    print(f"\n{'='*60}")
    print(f"T4: 综合浏览器验证 (S39-S41)")
    print(f"{'='*60}")
    print(f"  对话回复: {'✅' if has_reply else '❌'} ({reply[:50]})")
    print(f"  STT工具: {'✅' if has_stt else '❌'}")
    print(f"  大脑面板: {'✅' if has_brain_btn else '❌'}")
    print(f"  耗时: {elapsed:.1f}s")
    print(f"  判定: {'✅ PASS' if t4_ok else '❌ FAIL'}")
    results.append(("T4-综合(S39-S41)", t4_ok))

    # 汇总
    print(f"\n{'='*60}")
    print("S39-S41 全真实浏览器测试汇总")
    print(f"{'='*60}")
    for name, ok in results:
        print(f"  {name}: {'✅ PASS' if ok else '❌ FAIL'}")
    passed = sum(1 for _, ok in results if ok)
    print(f"\n总计: {passed}/{len(results)} 通过")
    print(f"总判定: {'✅ ALL PASS' if passed == len(results) else '❌ HAS FAILURES'}")
    return passed == len(results)

if __name__ == "__main__":
    main()
