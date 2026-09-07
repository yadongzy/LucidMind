"""Tests for brain_fast_path — Fast Path 分类器。"""

import pytest
from brain_fast_path import classify, FastPathResult


class TestFastPathClassify:
    """测试快速路径分类。"""

    # ── 问候 ──
    def test_greeting_hi(self):
        r = classify("你好")
        assert r.category == "greeting"
        assert r.skip_metacog is True
        assert r.skip_lessons is True
        assert r.skip_learn_detect is True

    def test_greeting_hello(self):
        r = classify("hello")
        assert r.category == "greeting"
        assert r.skip_metacog is True

    def test_greeting_good_morning(self):
        r = classify("早上好")
        assert r.category == "greeting"

    # ── 简短确认 ──
    def test_trivial_ok(self):
        r = classify("好的")
        assert r.category == "trivial"
        assert r.skip_metacog is True
        assert r.skip_lessons is True
        assert r.skip_learn_detect is True

    def test_trivial_thanks(self):
        r = classify("谢谢")
        assert r.category == "trivial"

    def test_trivial_emoji(self):
        r = classify("👍")
        assert r.category == "trivial"

    # ── 纠正/教学 ──
    def test_correction(self):
        r = classify("不对，应该是这样的")
        assert r.category == "correction"
        assert r.skip_metacog is True
        assert r.skip_lessons is True
        assert r.skip_learn_detect is False  # 保留学习检测

    def test_teaching(self):
        r = classify("记住，以后回答要用中文")
        assert r.category == "correction"
        assert r.skip_learn_detect is False

    # ── 工具触发 ──
    def test_tool_search(self):
        r = classify("搜索今天的新闻")
        assert r.category == "tool_use"
        assert r.skip_metacog is False
        assert r.skip_lessons is False

    def test_tool_file(self):
        r = classify("读取 /tmp/test.txt 文件")
        assert r.category == "tool_use"

    def test_tool_weather(self):
        r = classify("今天天气怎么样")
        assert r.category == "tool_use"

    # ── 复杂任务 ──
    def test_complex_long(self):
        long_input = "请帮我详细回答" + "这个非常重要的问题，" * 25  # >200 chars
        assert len(long_input) > 200
        r = classify(long_input)
        assert r.category == "complex"
        assert r.skip_metacog is False

    def test_complex_multi_step(self):
        r = classify("首先搜索最新的Python教程，然后总结要点")
        assert r.category in ("complex", "tool_use")  # 有工具关键词也可能是tool_use

    # ── 知识问答 ──
    def test_knowledge_short(self):
        r = classify("Python的GIL是什么？")
        assert r.category == "knowledge"
        assert r.skip_metacog is True
        assert r.skip_learn_detect is True

    def test_knowledge_medium(self):
        r = classify("解释一下深度学习中的反向传播算法的数学原理")
        assert r.category == "knowledge"
        assert r.skip_metacog is True

    # ── repr ──
    def test_repr(self):
        r = classify("你好")
        s = repr(r)
        assert "FastPath" in s
        assert "greeting" in s


class TestFastPathEdgeCases:
    """边界条件测试。"""

    def test_empty_string(self):
        r = classify("")
        assert r.category == "trivial"

    def test_whitespace_only(self):
        r = classify("   ")
        assert r.category == "trivial"

    def test_single_char(self):
        r = classify("?")
        assert r.category == "trivial"

    def test_mixed_greeting_tool(self):
        # "你好，帮我搜索一下" — 工具关键词优先
        r = classify("你好，帮我搜索一下天气")
        assert r.category == "tool_use"
