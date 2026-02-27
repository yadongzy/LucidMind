"""B阶段: Playwright 浏览器 E2E 测试 — 真实浏览器验证前端渲染与交互。

覆盖 FRONTEND_AUDIT.md 测试计划:
  A. 页面渲染 (14个Tab)
  B. 按钮功能 (核心交互)
  C. 数据加载 (API数据正确显示)
  D. 异常处理 (控制台无JS错误)

运行: pytest tests/test_e2e_browser.py -v --headed  (有头模式观察)
     pytest tests/test_e2e_browser.py -v            (无头模式CI)

需要: pip install pytest-playwright && playwright install chromium
需要: 服务器运行在 http://127.0.0.1:8000
"""

import os
import pytest
from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("LUCIDMIND_TEST_URL", "http://127.0.0.1:8000")
HEADED = os.environ.get("HEADED", "").lower() in ("1", "true", "yes")

TAB_TITLES = {
    "chat": "对话", "overview": "系统概览", "sessions": "会话管理",
    "tasks": "任务看板", "brain": "大脑状态", "memory": "记忆与经验",
    "learning": "学习中心", "channels": "消息通道", "mcp": "MCP 管理",
    "plugins": "插件管理", "profile": "用户画像", "config": "系统配置",
    "diagnostics": "系统诊断", "logs": "事件日志",
}


@pytest.fixture(scope="module")
def browser_ctx():
    """共享浏览器上下文，整个模块只启动一次。"""
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=not HEADED)
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda err: console_errors.append(str(err)))
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_selector("lucidmind-app", timeout=10000)
    page.wait_for_timeout(1500)
    yield page, console_errors
    context.close()
    browser.close()
    pw.stop()


def _click_tab(page, tab_name: str):
    title = TAB_TITLES.get(tab_name, tab_name)
    page.locator(f".nav-item:has-text('{title}')").click()
    page.wait_for_timeout(600)


def _filter_errors(errors):
    exclude = ["favicon", "Notification", "ResizeObserver", "WebSocket",
               "ERR_CONNECTION", "net::", "Permission", "service-worker"]
    return [e for e in errors if not any(p.lower() in e.lower() for p in exclude)]


# ═══════════════════════ A. 页面渲染测试 ═══════════════════════


class TestTabRendering:
    """A-01~A-14: 每个 Tab 能正常渲染，无 JS 报错。"""

    def test_A01_chat_renders(self, browser_ctx):
        """A-01: 对话界面渲染，输入框可用。"""
        page, _ = browser_ctx
        _click_tab(page, "chat")
        inp = page.locator(".chat-input, textarea, input[type='text']").first
        assert inp.is_visible(), "对话输入框应可见"

    def test_A02_overview_renders(self, browser_ctx):
        """A-02: 概览页渲染，统计卡显示。"""
        page, _ = browser_ctx
        _click_tab(page, "overview")
        page.wait_for_timeout(800)
        assert page.locator(".page-title:has-text('系统概览')").is_visible()
        cards = page.locator(".stat-card, .card, .overview-card, .metric")
        assert cards.count() > 0, "概览页应有统计卡片"

    def test_A03_sessions_renders(self, browser_ctx):
        """A-03: 会话列表渲染。"""
        page, _ = browser_ctx
        _click_tab(page, "sessions")
        page.wait_for_timeout(800)
        assert page.locator(".page-title:has-text('会话管理')").is_visible()

    def test_A04_tasks_renders(self, browser_ctx):
        """A-04: 任务看板渲染。"""
        page, _ = browser_ctx
        _click_tab(page, "tasks")
        page.wait_for_timeout(800)
        assert page.locator(".page-title:has-text('任务看板')").is_visible()

    def test_A05_brain_renders(self, browser_ctx):
        """A-05: 大脑状态页渲染。"""
        page, _ = browser_ctx
        _click_tab(page, "brain")
        page.wait_for_timeout(800)
        assert page.locator(".page-title:has-text('大脑状态')").is_visible()
        assert len(page.locator(".content").inner_text()) > 20

    def test_A06_memory_renders(self, browser_ctx):
        """A-06: 记忆页渲染。"""
        page, _ = browser_ctx
        _click_tab(page, "memory")
        page.wait_for_timeout(800)
        assert page.locator(".page-title:has-text('记忆与经验')").is_visible()

    def test_A07_learning_renders(self, browser_ctx):
        """A-07: 学习中心渲染。"""
        page, _ = browser_ctx
        _click_tab(page, "learning")
        page.wait_for_timeout(800)
        assert page.locator(".page-title:has-text('学习中心')").is_visible()

    def test_A08_channels_renders(self, browser_ctx):
        """A-08: 通道页渲染。"""
        page, _ = browser_ctx
        _click_tab(page, "channels")
        page.wait_for_timeout(800)
        assert page.locator(".page-title:has-text('消息通道')").is_visible()

    def test_A09_mcp_renders(self, browser_ctx):
        """A-09: MCP管理页渲染。"""
        page, _ = browser_ctx
        _click_tab(page, "mcp")
        page.wait_for_timeout(800)
        assert page.locator(".page-title:has-text('MCP')").is_visible()

    def test_A10_plugins_renders(self, browser_ctx):
        """A-10: 插件页渲染。"""
        page, _ = browser_ctx
        _click_tab(page, "plugins")
        page.wait_for_timeout(800)
        assert page.locator(".page-title:has-text('插件管理')").is_visible()

    def test_A11_profile_renders(self, browser_ctx):
        """A-11: 用户画像渲染。"""
        page, _ = browser_ctx
        _click_tab(page, "profile")
        page.wait_for_timeout(800)
        assert page.locator(".page-title:has-text('用户画像')").is_visible()

    def test_A12_config_renders(self, browser_ctx):
        """A-12: 系统配置渲染。"""
        page, _ = browser_ctx
        _click_tab(page, "config")
        page.wait_for_timeout(800)
        assert page.locator(".page-title:has-text('系统配置')").is_visible()

    def test_A13_diagnostics_renders(self, browser_ctx):
        """A-13: 诊断页渲染。"""
        page, _ = browser_ctx
        _click_tab(page, "diagnostics")
        page.wait_for_timeout(800)
        assert page.locator(".page-title:has-text('系统诊断')").is_visible()

    def test_A14_logs_renders(self, browser_ctx):
        """A-14: 日志页渲染。"""
        page, _ = browser_ctx
        _click_tab(page, "logs")
        page.wait_for_timeout(800)
        assert page.locator(".page-title:has-text('事件日志')").is_visible()


# ═══════════════════════ B. 核心按钮交互 ═══════════════════════


class TestCoreInteractions:
    """B: 核心按钮和交互功能验证。"""

    def test_B01_chat_input_and_send(self, browser_ctx):
        """B-01: 对话输入框可输入文字。"""
        page, _ = browser_ctx
        _click_tab(page, "chat")
        inp = page.locator(".chat-input, textarea").first
        inp.fill("测试消息")
        assert inp.input_value() == "测试消息"
        inp.fill("")

    def test_B02_sidebar_collapse(self, browser_ctx):
        """B-32: 侧边栏折叠/展开。"""
        page, _ = browser_ctx
        toggle = page.locator(".nav-toggle").first
        toggle.click()
        page.wait_for_timeout(400)
        assert page.locator(".shell--nav-collapsed").count() > 0
        toggle.click()
        page.wait_for_timeout(400)
        assert page.locator(".shell--nav-collapsed").count() == 0

    def test_B03_theme_toggle(self, browser_ctx):
        """B-32: 主题切换按钮有效。"""
        page, _ = browser_ctx
        btn = page.locator(".theme-toggle").first
        # 获取当前主题
        before = page.evaluate("document.documentElement.getAttribute('data-theme')")
        btn.click()
        page.wait_for_timeout(300)
        after = page.evaluate("document.documentElement.getAttribute('data-theme')")
        assert before != after, f"主题应切换: {before} → {after}"
        # 切回原主题
        btn.click()
        page.wait_for_timeout(300)

    def test_B04_status_pill_visible(self, browser_ctx):
        """顶栏状态药丸可见，显示连接状态。"""
        page, _ = browser_ctx
        pill = page.locator(".pill").first
        assert pill.is_visible()
        text = pill.inner_text()
        assert "状态" in text

    def test_B05_model_selector_exists(self, browser_ctx):
        """顶栏模型选择器存在。"""
        page, _ = browser_ctx
        select = page.locator(".model-select, select").first
        assert select.is_visible()

    def test_B06_sessions_page_has_default(self, browser_ctx):
        """B-09: 会话页包含 default 会话。"""
        page, _ = browser_ctx
        _click_tab(page, "sessions")
        page.wait_for_timeout(800)
        text = page.locator(".content").inner_text()
        assert "default" in text.lower() or "默认" in text

    def test_B07_brain_page_has_controls(self, browser_ctx):
        """B-29: 大脑页有控制按钮。"""
        page, _ = browser_ctx
        _click_tab(page, "brain")
        page.wait_for_timeout(800)
        buttons = page.locator(".content button, .content .btn")
        assert buttons.count() > 0, "大脑页应有控制按钮"

    def test_B08_plugins_page_has_reload(self, browser_ctx):
        """B-22: 插件页有热加载按钮。"""
        page, _ = browser_ctx
        _click_tab(page, "plugins")
        page.wait_for_timeout(800)
        text = page.locator(".content").inner_text()
        assert "热加载" in text or "reload" in text.lower() or "刷新" in text

    def test_B09_profile_page_has_content(self, browser_ctx):
        """B-25: 画像页显示用户画像内容。"""
        page, _ = browser_ctx
        _click_tab(page, "profile")
        page.wait_for_timeout(1000)
        text = page.locator(".content").inner_text()
        assert len(text) > 30, "画像页应显示画像内容"

    def test_B10_config_page_has_form(self, browser_ctx):
        """B-28: 配置页有表单元素。"""
        page, _ = browser_ctx
        _click_tab(page, "config")
        page.wait_for_timeout(800)
        forms = page.locator(".content select, .content input, .content button")
        assert forms.count() > 0, "配置页应有表单元素"


# ═══════════════════════ C. 数据加载验证 ═══════════════════════


class TestDataLoading:
    """C: 验证各页面 API 数据正确加载显示。"""

    def test_C01_overview_loads_data(self, browser_ctx):
        """概览页数据加载完成，无 undefined。"""
        page, _ = browser_ctx
        _click_tab(page, "overview")
        page.wait_for_timeout(1200)
        text = page.locator(".content").inner_text()
        assert "undefined" not in text, "概览页不应包含 undefined"

    def test_C02_brain_loads_status(self, browser_ctx):
        """大脑页加载状态数据。"""
        page, _ = browser_ctx
        _click_tab(page, "brain")
        page.wait_for_timeout(1200)
        text = page.locator(".content").inner_text()
        assert "undefined" not in text, "大脑页不应包含 undefined"

    def test_C03_channels_loads_data(self, browser_ctx):
        """通道页加载通道数据。"""
        page, _ = browser_ctx
        _click_tab(page, "channels")
        page.wait_for_timeout(1200)
        text = page.locator(".content").inner_text()
        # 应至少有一个通道名称
        has_channel = any(k in text for k in ["Telegram", "飞书", "企微", "微信"])
        assert has_channel, "通道页应显示通道信息"

    def test_C04_mcp_loads_servers(self, browser_ctx):
        """MCP页加载服务器数据。"""
        page, _ = browser_ctx
        _click_tab(page, "mcp")
        page.wait_for_timeout(1200)
        text = page.locator(".content").inner_text()
        assert len(text) > 20, "MCP页应显示内容"

    def test_C05_plugins_loads_list(self, browser_ctx):
        """插件页加载插件列表。"""
        page, _ = browser_ctx
        _click_tab(page, "plugins")
        page.wait_for_timeout(1200)
        text = page.locator(".content").inner_text()
        assert len(text) > 30, "插件页应显示插件列表"

    def test_C06_diagnostics_loads(self, browser_ctx):
        """诊断页加载诊断数据。"""
        page, _ = browser_ctx
        _click_tab(page, "diagnostics")
        page.wait_for_timeout(1200)
        text = page.locator(".content").inner_text()
        assert len(text) > 20, "诊断页应显示内容"

    def test_C07_logs_has_entries(self, browser_ctx):
        """日志页有事件条目（至少有系统启动事件）。"""
        page, _ = browser_ctx
        _click_tab(page, "logs")
        page.wait_for_timeout(800)
        text = page.locator(".content").inner_text()
        assert len(text) > 20, "日志页应有事件"


# ═══════════════════════ D. JS 错误检查 ═══════════════════════


class TestNoJSErrors:
    """D: 遍历所有Tab后无严重JS错误。"""

    def test_D01_no_critical_js_errors(self, browser_ctx):
        """遍历所有Tab后，控制台无严重JS错误。"""
        page, console_errors = browser_ctx
        # 先遍历所有Tab
        for tab in TAB_TITLES:
            _click_tab(page, tab)
            page.wait_for_timeout(400)

        critical = _filter_errors(console_errors)
        if critical:
            msg = f"发现 {len(critical)} 个JS错误:\n" + "\n".join(critical[:5])
            pytest.fail(msg)


# ═══════════════════════ E. WebSocket 连接 ═══════════════════════


class TestWebSocket:
    """验证 WebSocket 连接状态。"""

    def test_E01_websocket_connected(self, browser_ctx):
        """页面加载后 WebSocket 应已连接。"""
        page, _ = browser_ctx
        _click_tab(page, "chat")
        page.wait_for_timeout(500)
        # 检查状态指示器
        dot = page.locator(".statusDot.ok")
        assert dot.count() > 0, "WebSocket 应已连接 (状态点应为ok)"

    def test_E02_connection_status_shows_normal(self, browser_ctx):
        """连接状态显示"正常"。"""
        page, _ = browser_ctx
        pill = page.locator(".pill").first
        text = pill.inner_text()
        assert "正常" in text, f"连接状态应为正常，实际: {text}"


# ═══════════════════════ F. 导航完整性 ═══════════════════════


class TestNavigation:
    """验证导航栏完整性。"""

    def test_F01_all_nav_items_exist(self, browser_ctx):
        """导航栏包含所有14个Tab。"""
        page, _ = browser_ctx
        for tab, title in TAB_TITLES.items():
            btn = page.locator(f".nav-item:has-text('{title}')")
            assert btn.count() > 0, f"缺少导航项: {title} ({tab})"

    def test_F02_nav_groups_exist(self, browser_ctx):
        """导航分组标题存在。"""
        page, _ = browser_ctx
        groups = ["对话", "控制台", "大脑", "连接", "设置"]
        for g in groups:
            label = page.locator(f".nav-label:has-text('{g}')")
            assert label.count() > 0, f"缺少导航分组: {g}"

    def test_F03_brand_visible(self, browser_ctx):
        """品牌标识可见。"""
        page, _ = browser_ctx
        brand = page.locator(".brand-title")
        assert brand.is_visible()
        assert "LUCIDMIND" in brand.inner_text()
