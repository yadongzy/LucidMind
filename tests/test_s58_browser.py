"""S58 真实浏览器测试：UX细节优化验证。

T1: 登录页可访问
T2: textarea替代input
T3: 停止按钮存在
T4: chat_enhance.js 包含所有S58功能
T5: 亮色主题CSS完整
T6: 消息搜索+导出工具栏
T7: 会话搜索框
T8: 移动端适配CSS
T9: 图片粘贴功能代码
T10: 断线重连横幅代码
T11: IME兼容代码
T12: 经验库包含核心智慧
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import requests

BASE = "http://127.0.0.1:8765"


def test_t1_login_page():
    """T1: 登录页可访问。"""
    r = requests.get(f"{BASE}/login", timeout=10)
    assert r.status_code == 200
    assert "password" in r.text.lower()


def test_t2_textarea_input():
    """T2: console.html 使用 textarea 替代 input。"""
    r = requests.get(f"{BASE}/", timeout=10)
    assert r.status_code == 200
    assert "<textarea" in r.text
    assert 'id="user-input"' in r.text
    assert "Shift+Enter" in r.text


def test_t3_stop_button():
    """T3: 停止按钮存在。"""
    r = requests.get(f"{BASE}/", timeout=10)
    assert 'id="stop-btn"' in r.text
    assert "停止生成" in r.text


def test_t4_chat_enhance_features():
    """T4: chat_enhance.js 包含所有S58功能。"""
    r = requests.get(f"{BASE}/static/chat_enhance.js", timeout=10)
    assert r.status_code == 200
    js = r.text
    # S52: 会话搜索
    assert "session-search" in js
    # S53: 消息搜索+导出
    assert "msg-search" in js
    assert "export-btn" in js
    # S54: 移动端
    assert "max-width: 768px" in js
    # S58: textarea
    assert "initTextareaEnhance" in js
    assert "isComposing" in js
    # S58: 停止按钮
    assert "initStopButton" in js
    # S58: 新消息提示
    assert "initNewMessageIndicator" in js
    assert "new-msg-btn" in js
    # S58: 图片粘贴
    assert "initPasteUpload" in js
    # S58: 断线横幅
    assert "initReconnectBanner" in js
    assert "reconnect-banner" in js


def test_t5_light_theme_css():
    """T5: 亮色主题CSS完整覆盖。"""
    r = requests.get(f"{BASE}/static/console.css", timeout=10)
    assert r.status_code == 200
    css = r.text
    assert '--bg-main: #ffffff' in css
    assert '--bg-sidebar: #f3f3f3' in css
    assert '--bg-activity: #e8e8e8' in css
    assert '--bg-header: #f0f0f0' in css
    assert '--bg-input: #ffffff' in css
    assert '--text-primary: #1e1e1e' in css
    assert '--text-secondary: #616161' in css
    assert '--success: #16825d' in css
    assert '--error: #cd3131' in css


def test_t6_msg_search_export():
    """T6: 消息搜索+导出工具栏代码。"""
    r = requests.get(f"{BASE}/static/chat_enhance.js", timeout=10)
    js = r.text
    assert "搜索消息" in js
    assert "导出对话" in js
    assert "text/markdown" in js
    assert "search-highlight" in js


def test_t7_session_search():
    """T7: 会话搜索框代码。"""
    r = requests.get(f"{BASE}/static/chat_enhance.js", timeout=10)
    js = r.text
    assert "搜索会话" in js
    assert "session-search" in js


def test_t8_mobile_css():
    """T8: 移动端适配CSS。"""
    r = requests.get(f"{BASE}/static/chat_enhance.js", timeout=10)
    js = r.text
    assert "@media (max-width: 768px)" in js
    assert "grid-template-columns" in js


def test_t9_paste_upload():
    """T9: 图片粘贴功能代码。"""
    r = requests.get(f"{BASE}/static/chat_enhance.js", timeout=10)
    js = r.text
    assert "clipboardData" in js
    assert "image/" in js
    assert "/api/upload" in js


def test_t10_reconnect_banner():
    """T10: 断线重连横幅代码。"""
    r = requests.get(f"{BASE}/static/chat_enhance.js", timeout=10)
    js = r.text
    assert "reconnect-banner" in js
    assert "连接已断开" in js


def test_t11_ime_compat():
    """T11: IME兼容代码。"""
    r = requests.get(f"{BASE}/static/chat_enhance.js", timeout=10)
    js = r.text
    assert "isComposing" in js
    assert "keyCode === 229" in js
    assert "shiftKey" in js


def test_t12_wisdom_library():
    """T12: 经验库包含核心智慧。"""
    lessons_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                "data", "lessons.json")
    with open(lessons_path, encoding="utf-8") as f:
        lessons = json.load(f)
    assert len(lessons) >= 18
    triggers = [l["trigger"] for l in lessons]
    assert any("永不言败" in t or "困难任务" in t for t in triggers)
    assert any("Cascade" in t or "AI助手" in t for t in triggers)
    assert any("LucidMind" in t for t in triggers)
    assert any("用户体验" in t or "UX" in t for t in triggers)
