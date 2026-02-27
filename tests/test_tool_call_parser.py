"""测试 tool_call_parser — XML tool call 解析器。"""

import json
import pytest
from tool_call_parser import parse_xml_tool_calls, strip_xml_tool_calls, has_xml_tool_calls


class TestHasXmlToolCalls:
    """快速检测是否包含 XML tool call。"""

    def test_empty(self):
        assert has_xml_tool_calls("") is False
        assert has_xml_tool_calls(None) is False

    def test_normal_text(self):
        assert has_xml_tool_calls("Hello, how are you?") is False

    def test_with_invoke(self):
        assert has_xml_tool_calls('<invoke name="web_search">') is True

    def test_case_insensitive(self):
        assert has_xml_tool_calls('<INVOKE NAME="test">') is True


class TestParseXmlToolCalls:
    """解析 XML 格式 tool call。"""

    def test_empty_returns_empty(self):
        assert parse_xml_tool_calls("") == []
        assert parse_xml_tool_calls(None) == []
        assert parse_xml_tool_calls("normal text") == []

    def test_single_tool_call(self):
        text = '''[tool_call]
<invoke name="web_search">
<parameter name="query">今天的科技新闻</parameter>
</invoke>'''
        result = parse_xml_tool_calls(text)
        assert len(result) == 1
        assert result[0]["function"]["name"] == "web_search"
        args = json.loads(result[0]["function"]["arguments"])
        assert args["query"] == "今天的科技新闻"
        assert result[0]["type"] == "function"
        assert result[0]["id"].startswith("xmltc_web_search_")

    def test_multiple_parameters(self):
        text = '''<invoke name="web_search">
<parameter name="query">科技新闻</parameter>
<parameter name="max_results">8</parameter>
</invoke>'''
        result = parse_xml_tool_calls(text)
        assert len(result) == 1
        args = json.loads(result[0]["function"]["arguments"])
        assert args["query"] == "科技新闻"
        assert args["max_results"] == "8"

    def test_multiple_tool_calls(self):
        text = '''先检查一下。
<invoke name="run_command">
<parameter name="command">ls -la</parameter>
</invoke>
然后搜索。
<invoke name="web_search">
<parameter name="query">test</parameter>
</invoke>'''
        result = parse_xml_tool_calls(text)
        assert len(result) == 2
        assert result[0]["function"]["name"] == "run_command"
        assert result[1]["function"]["name"] == "web_search"

    def test_with_minimax_tag(self):
        text = '''<invoke name="run_command">
<parameter name="command">which say</parameter>
</invoke>
</minimax:tool_call>'''
        result = parse_xml_tool_calls(text)
        assert len(result) == 1
        assert result[0]["function"]["name"] == "run_command"

    def test_with_tool_call_marker(self):
        text = '''让我先搜索...
[tool_call]
<invoke name="web_search">
<parameter name="query">量子计算</parameter>
</invoke>'''
        result = parse_xml_tool_calls(text)
        assert len(result) == 1
        assert result[0]["function"]["name"] == "web_search"

    def test_mcp_tool(self):
        text = '''<invoke name="mcp_filesystem_list_directory">
<parameter name="path">/Users/yadong/Desktop</parameter>
</invoke>'''
        result = parse_xml_tool_calls(text)
        assert len(result) == 1
        assert result[0]["function"]["name"] == "mcp_filesystem_list_directory"
        args = json.loads(result[0]["function"]["arguments"])
        assert args["path"] == "/Users/yadong/Desktop"

    def test_single_quotes(self):
        text = "<invoke name='web_search'>\n<parameter name='query'>test</parameter>\n</invoke>"
        result = parse_xml_tool_calls(text)
        assert len(result) == 1
        assert result[0]["function"]["name"] == "web_search"

    def test_no_parameters(self):
        text = '<invoke name="get_time"></invoke>'
        result = parse_xml_tool_calls(text)
        assert len(result) == 1
        assert result[0]["function"]["name"] == "get_time"
        args = json.loads(result[0]["function"]["arguments"])
        assert args == {}

    def test_multiline_parameter_value(self):
        text = '''<invoke name="run_command">
<parameter name="command">echo "hello
world"</parameter>
</invoke>'''
        result = parse_xml_tool_calls(text)
        assert len(result) == 1
        args = json.loads(result[0]["function"]["arguments"])
        assert "hello\nworld" in args["command"]

    def test_unique_ids(self):
        text = '''<invoke name="web_search">
<parameter name="query">a</parameter>
</invoke>
<invoke name="web_search">
<parameter name="query">b</parameter>
</invoke>'''
        result = parse_xml_tool_calls(text)
        assert len(result) == 2
        assert result[0]["id"] != result[1]["id"]


class TestStripXmlToolCalls:
    """从文本中剥离 XML tool call。"""

    def test_empty(self):
        assert strip_xml_tool_calls("") == ""
        assert strip_xml_tool_calls(None) is None

    def test_no_tool_calls(self):
        text = "Hello, how are you?"
        assert strip_xml_tool_calls(text) == text

    def test_strip_with_marker(self):
        text = '''让我搜索一下。
[tool_call]
<invoke name="web_search">
<parameter name="query">test</parameter>
</invoke>'''
        result = strip_xml_tool_calls(text)
        assert "<invoke" not in result
        assert "[tool_call]" not in result
        assert "让我搜索一下" in result

    def test_strip_with_minimax_tag(self):
        text = '''Hello<invoke name="Bash">
<parameter name="command">ls</parameter>
</invoke>
</minimax:tool_call>World'''
        result = strip_xml_tool_calls(text)
        assert "<invoke" not in result
        assert "minimax" not in result
        assert "Hello" in result
        assert "World" in result

    def test_strip_multiple(self):
        text = '''First.
<invoke name="a">
<parameter name="x">1</parameter>
</invoke>
Second.
<invoke name="b">
<parameter name="y">2</parameter>
</invoke>
Third.'''
        result = strip_xml_tool_calls(text)
        assert "First" in result
        assert "Second" in result
        assert "Third" in result
        assert "<invoke" not in result

    def test_strip_preserves_clean_text(self):
        text = "这是一段没有工具调用的普通文本。"
        assert strip_xml_tool_calls(text) == text

    def test_tool_call_only(self):
        text = '''[tool_call]
<invoke name="run_command">
<parameter name="command">ls</parameter>
</invoke>'''
        result = strip_xml_tool_calls(text)
        assert result == ""


class TestRealWorldExamples:
    """来自 brain.log 的真实案例。"""

    def test_minimax_web_search(self):
        """MiniMax-M1 搜索新闻的实际输出。"""
        text = '''让我先搜索今天的科技新闻...
[tool_call]
<invoke name="web_search">
<parameter name="query">2026年2月27日 科技新闻</parameter>
<parameter name="max_results">8</parameter>
</invoke>'''
        tcs = parse_xml_tool_calls(text)
        assert len(tcs) == 1
        assert tcs[0]["function"]["name"] == "web_search"
        args = json.loads(tcs[0]["function"]["arguments"])
        assert args["query"] == "2026年2月27日 科技新闻"
        assert args["max_results"] == "8"

        clean = strip_xml_tool_calls(text)
        assert "让我先搜索今天的科技新闻" in clean
        assert "<invoke" not in clean

    def test_minimax_run_command(self):
        """MiniMax-M1 执行命令的实际输出。"""
        text = '''[tool_call]
<invoke name="run_command">
<parameter name="command">ls -la /Users/yadong/Desktop</parameter>
</invoke>'''
        tcs = parse_xml_tool_calls(text)
        assert len(tcs) == 1
        assert tcs[0]["function"]["name"] == "run_command"
        args = json.loads(tcs[0]["function"]["arguments"])
        assert args["command"] == "ls -la /Users/yadong/Desktop"

    def test_minimax_mcp_filesystem(self):
        """MiniMax-M1 调用 MCP 工具的实际输出。"""
        text = '''好的，我先查看你桌面的文件...
[tool_call]
<invoke name="mcp_filesystem_list_directory">
<parameter name="path">/Users/yadong/Desktop</parameter>
</invoke>'''
        tcs = parse_xml_tool_calls(text)
        assert len(tcs) == 1
        assert tcs[0]["function"]["name"] == "mcp_filesystem_list_directory"

    def test_minimax_with_say_command(self):
        """MiniMax-M1 用语音和说话的实际输出。"""
        text = '''[tool_call]
<invoke name="run_command">
<parameter name="command">which say && say --help 2>&1 | head -20</parameter>
</invoke>
</minimax:tool_call>'''
        tcs = parse_xml_tool_calls(text)
        assert len(tcs) == 1
        assert tcs[0]["function"]["name"] == "run_command"
        args = json.loads(tcs[0]["function"]["arguments"])
        assert "which say" in args["command"]
