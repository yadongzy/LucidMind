"""工具 + 记忆 单元测试（S3-S6）。

从 test_brain.py 拆分，符合第三条代码边界（≤300行）。
"""

import pytest
import asyncio


# ========== S3: 工具调用测试 ==========


def test_shell_adapter_importable():
    """Shell 适配器可导入且实现 ToolPort。"""
    from adapters.tools.shell import ShellAdapter
    from ports.tool_port import ToolPort

    adapter = ShellAdapter()
    assert isinstance(adapter, ToolPort)
    tools = adapter.list_tools()
    assert len(tools) > 0
    assert tools[0]["function"]["name"] == "run_command"


def test_brain_tool_call():
    """Brain 收到 LLM 的 tool_calls 时，执行工具并回传结果。"""
    from brain import Brain
    from ports.llm_port import LLMPort
    from ports.stream_port import StreamPort
    from ports.tool_port import ToolPort

    call_count = 0

    class MockLLMWithTools(LLMPort):
        async def chat(self, messages, tools=None, stream=False):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # 第一轮：LLM 决定调工具
                return {
                    "content": "",
                    "tool_calls": [{
                        "id": "call_1",
                        "function": {
                            "name": "run_command",
                            "arguments": '{"command": "echo hello"}',
                        },
                    }],
                }
            else:
                # 第二轮：LLM 看到工具结果后给出最终回复
                return {"content": "命令输出是 hello"}

        async def is_available(self):
            return True

    class MockStream(StreamPort):
        def __init__(self):
            self.events = []
        async def emit(self, event_type, data):
            self.events.append((event_type, data))

    class MockTool(ToolPort):
        async def execute(self, tool_name, params):
            return {"success": True, "result": "hello", "error": None}
        def list_tools(self):
            return [{"type": "function", "function": {"name": "run_command", "parameters": {}}}]

    mock_stream = MockStream()
    brain = Brain(
        llm=MockLLMWithTools(),
        stream=mock_stream,
        tools=MockTool(),
    )

    asyncio.get_event_loop().run_until_complete(
        brain.process("test-session", "run echo hello")
    )

    types = [e[0] for e in mock_stream.events]
    assert "tool_call" in types, f"缺少 tool_call 事件: {types}"
    assert "tool_result" in types, f"缺少 tool_result 事件: {types}"
    assert "response" in types
    assert "complete" in types
    assert call_count == 2, f"LLM 应被调用 2 次，实际 {call_count}"


def test_shell_blocked_command():
    """危险命令应被拦截。"""
    from adapters.tools.shell import ShellAdapter

    adapter = ShellAdapter()
    result = asyncio.get_event_loop().run_until_complete(
        adapter.execute("run_command", {"command": "rm -rf /"})
    )
    assert result["success"] is False
    assert "安全策略" in result["error"]


# === S4: 文件工具测试 ===

def test_file_adapter_importable():
    """FileAdapter 和 CompositeToolAdapter 可导入。"""
    from adapters.tools.file import FileAdapter
    from adapters.tools.composite import CompositeToolAdapter
    assert FileAdapter is not None
    assert CompositeToolAdapter is not None


def test_file_write_and_read(tmp_path):
    """正向：写入文件后能读回相同内容。"""
    from adapters.tools.file import FileAdapter

    adapter = FileAdapter(workspace=str(tmp_path))
    loop = asyncio.get_event_loop()

    # 写入
    w = loop.run_until_complete(
        adapter.execute("write_file", {"path": "hello.txt", "content": "S4 Test OK"})
    )
    assert w["success"] is True, f"写入失败: {w['error']}"
    assert (tmp_path / "hello.txt").exists(), "文件未创建"

    # 读取
    r = loop.run_until_complete(
        adapter.execute("read_file", {"path": "hello.txt"})
    )
    assert r["success"] is True, f"读取失败: {r['error']}"
    assert r["result"] == "S4 Test OK"


def test_file_list_directory(tmp_path):
    """正向：列出目录内容。"""
    from adapters.tools.file import FileAdapter

    (tmp_path / "a.txt").write_text("aaa")
    (tmp_path / "b.txt").write_text("bbb")
    (tmp_path / "subdir").mkdir()

    adapter = FileAdapter(workspace=str(tmp_path))
    r = asyncio.get_event_loop().run_until_complete(
        adapter.execute("list_directory", {"path": "."})
    )
    assert r["success"] is True
    assert "a.txt" in r["result"]
    assert "b.txt" in r["result"]
    assert "subdir" in r["result"]


def test_file_path_traversal_blocked(tmp_path):
    """异常：路径遍历攻击应被拦截。"""
    from adapters.tools.file import FileAdapter

    adapter = FileAdapter(workspace=str(tmp_path))
    loop = asyncio.get_event_loop()

    r = loop.run_until_complete(
        adapter.execute("read_file", {"path": "../../etc/passwd"})
    )
    assert r["success"] is False
    assert "不安全" in r["error"]


def test_file_blocked_path(tmp_path):
    """异常：禁止路径（.env, .git 等）应被拦截。"""
    from adapters.tools.file import FileAdapter

    adapter = FileAdapter(workspace=str(tmp_path))
    loop = asyncio.get_event_loop()

    r = loop.run_until_complete(
        adapter.execute("write_file", {"path": ".env", "content": "SECRET=abc"})
    )
    assert r["success"] is False
    assert "禁止" in r["error"]


def test_composite_routes_correctly():
    """CompositeToolAdapter 正确路由到对应适配器。"""
    from adapters.tools.shell import ShellAdapter
    from adapters.tools.file import FileAdapter
    from adapters.tools.composite import CompositeToolAdapter

    shell = ShellAdapter()
    file_adapter = FileAdapter()
    composite = CompositeToolAdapter([shell, file_adapter])

    tools = composite.list_tools()
    names = [t["function"]["name"] for t in tools]
    assert "run_command" in names
    assert "read_file" in names
    assert "write_file" in names
    assert "list_directory" in names

    # 未知工具应返回错误
    r = asyncio.get_event_loop().run_until_complete(
        composite.execute("nonexistent_tool", {})
    )
    assert r["success"] is False
    assert "未知工具" in r["error"]


# === S5: 网络搜索工具测试 ===

def test_web_search_adapter_importable():
    """WebSearchAdapter 可导入。"""
    from adapters.tools.web_search import WebSearchAdapter
    assert WebSearchAdapter is not None


def test_web_search_real_query():
    """正向：真实搜索返回结果（需要网络）。"""
    from adapters.tools.web_search import WebSearchAdapter

    adapter = WebSearchAdapter()
    r = asyncio.get_event_loop().run_until_complete(
        adapter.execute("web_search", {"query": "Python programming language", "max_results": 2})
    )
    if not r["success"] and ("SearchException" in str(r.get("error", "")) or "DDGSException" in str(r.get("error", "")) or "TimeoutException" in str(r.get("error", ""))):
        pytest.skip(f"网络不可用，跳过真实搜索测试: {r['error'][:80]}")
    assert r["success"] is True, f"搜索失败: {r['error']}"
    assert r["result"] is not None
    assert len(r["result"]) > 0


def test_web_search_empty_query():
    """异常：空搜索词应返回错误。"""
    from adapters.tools.web_search import WebSearchAdapter

    adapter = WebSearchAdapter()
    r = asyncio.get_event_loop().run_until_complete(
        adapter.execute("web_search", {"query": ""})
    )
    assert r["success"] is False
    assert "空" in r["error"]


def test_composite_with_all_adapters():
    """CompositeToolAdapter 包含所有 S5 工具。"""
    from adapters.tools.shell import ShellAdapter
    from adapters.tools.file import FileAdapter
    from adapters.tools.web_search import WebSearchAdapter
    from adapters.tools.composite import CompositeToolAdapter

    composite = CompositeToolAdapter([ShellAdapter(), FileAdapter(), WebSearchAdapter()])
    names = [t["function"]["name"] for t in composite.list_tools()]
    assert "run_command" in names
    assert "read_file" in names
    assert "write_file" in names
    assert "list_directory" in names
    assert "web_search" in names


# === S6: 记忆系统测试 ===

def test_json_memory_adapter_importable():
    """JSONMemoryAdapter 可导入。"""
    from adapters.memory.json_memory import JSONMemoryAdapter
    assert JSONMemoryAdapter is not None


def test_memory_save_and_recall(tmp_path):
    """正向：保存记忆后能检索回来。"""
    from adapters.memory.json_memory import JSONMemoryAdapter

    adapter = JSONMemoryAdapter(data_dir=str(tmp_path))
    loop = asyncio.get_event_loop()

    loop.run_until_complete(adapter.save("暗号", "天王盖地虎", "secret"))
    loop.run_until_complete(adapter.save("偏好", "喜欢Python", "preference"))

    results = loop.run_until_complete(adapter.recall("暗号"))
    assert len(results) >= 1
    assert results[0]["value"] == "天王盖地虎"


def test_memory_session_persistence(tmp_path):
    """正向：会话消息跨实例持久化。"""
    from adapters.memory.json_memory import JSONMemoryAdapter

    sid = "test_session_001"
    loop = asyncio.get_event_loop()

    # 实例 1：写入消息
    adapter1 = JSONMemoryAdapter(data_dir=str(tmp_path))
    loop.run_until_complete(adapter1.save_message(sid, {"role": "user", "content": "暗号是 LucidMind"}))
    loop.run_until_complete(adapter1.save_message(sid, {"role": "assistant", "content": "我记住了"}))

    # 实例 2：新实例加载消息
    adapter2 = JSONMemoryAdapter(data_dir=str(tmp_path))
    messages = loop.run_until_complete(adapter2.get_context(sid))
    assert len(messages) == 2
    assert messages[0]["content"] == "暗号是 LucidMind"
    assert messages[1]["content"] == "我记住了"


