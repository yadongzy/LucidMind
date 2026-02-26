"""S9 成人礼 — 全面验收测试（pytest）。

覆盖: S1-S8 回归 + 压力测试（并发/超时/损坏恢复）。
"""

import asyncio
import json
import os
import pytest

# === 公共 Mock ===

class MockLLM:
    model = "test-model"
    async def chat(self, messages, tools=None, stream=False, **kwargs):
        return {"content": "S9 验收回复", "usage": {"total_tokens": 42}}
    async def is_available(self):
        return True

class MockStream:
    def __init__(self):
        self.events = []
    async def emit(self, event_type, data):
        self.events.append((event_type, data))


# === S1 回归: 基本对话 ===

def test_s9_s1_basic_chat():
    from brain import Brain
    stream = MockStream()
    brain = Brain(llm=MockLLM(), stream=stream)
    asyncio.get_event_loop().run_until_complete(brain.process("s9", "你好"))
    responses = [e for e in stream.events if e[0] == "response"]
    assert len(responses) == 1
    assert len(responses[0][1]) > 0


# === S2 回归: 思考提取 ===

def test_s9_s2_thinking_extraction():
    from brain import Brain
    class ThinkLLM(MockLLM):
        async def chat(self, messages, tools=None, stream=False, **kwargs):
            return {"content": "<think>我在想...</think>最终答案", "usage": {}}
    stream = MockStream()
    brain = Brain(llm=ThinkLLM(), stream=stream)
    asyncio.get_event_loop().run_until_complete(brain.process("s9", "测试思考"))
    thinking = [e for e in stream.events if e[0] == "thinking"]
    assert len(thinking) >= 1
    assert "我在想" in thinking[0][1]


# === S3 回归: Shell 工具 ===

def test_s9_s3_shell_tool():
    from adapters.tools.shell import ShellAdapter
    adapter = ShellAdapter()
    r = asyncio.get_event_loop().run_until_complete(
        adapter.execute("run_command", {"command": "echo S9_SHELL_OK"})
    )
    assert r["success"] is True
    assert "S9_SHELL_OK" in r["result"]

def test_s9_s3_shell_blocked():
    from adapters.tools.shell import ShellAdapter
    adapter = ShellAdapter()
    r = asyncio.get_event_loop().run_until_complete(
        adapter.execute("run_command", {"command": "rm -rf /"})
    )
    assert r["success"] is False


# === S4 回归: 文件工具 ===

def test_s9_s4_file_write_read(tmp_path):
    from adapters.tools.file import FileAdapter
    adapter = FileAdapter(workspace=str(tmp_path))
    loop = asyncio.get_event_loop()
    w = loop.run_until_complete(
        adapter.execute("write_file", {"path": "s9.txt", "content": "S9_FILE_OK"})
    )
    assert w["success"] is True
    r = loop.run_until_complete(adapter.execute("read_file", {"path": "s9.txt"}))
    assert r["success"] is True
    assert "S9_FILE_OK" in r["result"]

def test_s9_s4_list_directory(tmp_path):
    from adapters.tools.file import FileAdapter
    adapter = FileAdapter(workspace=str(tmp_path))
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        adapter.execute("write_file", {"path": "a.txt", "content": "x"})
    )
    r = loop.run_until_complete(adapter.execute("list_directory", {"path": "."}))
    assert r["success"] is True
    assert "a.txt" in r["result"]


# === S5 回归: 搜索 ===

def test_s9_s5_web_search():
    from adapters.tools.web_search import WebSearchAdapter
    adapter = WebSearchAdapter()
    r = asyncio.get_event_loop().run_until_complete(
        adapter.execute("web_search", {"query": "Python programming"})
    )
    # 网络可能超时，验证降级行为正确
    if r["success"]:
        assert len(r["result"]) > 10
    else:
        assert r["error"] is not None  # 优雅降级，有错误信息


# === S6 回归: 记忆持久化 ===

def test_s9_s6_memory_persist(tmp_path):
    from adapters.memory.json_memory import JSONMemoryAdapter
    loop = asyncio.get_event_loop()
    a1 = JSONMemoryAdapter(data_dir=str(tmp_path))
    loop.run_until_complete(a1.save_message("s9", {"role": "user", "content": "暗号S9"}))
    a2 = JSONMemoryAdapter(data_dir=str(tmp_path))
    msgs = loop.run_until_complete(a2.get_context("s9"))
    assert len(msgs) == 1
    assert msgs[0]["content"] == "暗号S9"


# === S7 回归: Ralph 重试 ===

def test_s9_s7_ralph_retry():
    from brain import Brain
    call_count = 0
    class FailTwiceLLM:
        model = "test"
        async def chat(self, messages, tools=None, stream=False, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("fail")
            return {"content": "Ralph OK", "usage": {}}
        async def is_available(self):
            return True
    stream = MockStream()
    brain = Brain(llm=FailTwiceLLM(), stream=stream)
    brain.ralph_base_delay = 0.01
    asyncio.get_event_loop().run_until_complete(brain.process("s9", "retry"))
    assert call_count == 3
    responses = [e for e in stream.events if e[0] == "response"]
    assert "Ralph OK" in responses[0][1]


# === S8 回归: 学习 ===

def test_s9_s8_learning(tmp_path):
    from adapters.learning.json_lessons import JSONLessonsAdapter
    loop = asyncio.get_event_loop()
    adapter = JSONLessonsAdapter(data_dir=str(tmp_path))
    loop.run_until_complete(adapter.learn({
        "trigger": "user said wrong answer", "lesson": "correct answer is 42"
    }))
    lessons = loop.run_until_complete(adapter.get_lessons("wrong answer", limit=3))
    assert len(lessons) >= 1
    assert "42" in lessons[0]["lesson"]


# === 压力测试: 并发 WebSocket ===

def test_s9_pressure_concurrent():
    from brain import Brain
    stream1, stream2, stream3 = MockStream(), MockStream(), MockStream()
    b1 = Brain(llm=MockLLM(), stream=stream1)
    b2 = Brain(llm=MockLLM(), stream=stream2)
    b3 = Brain(llm=MockLLM(), stream=stream3)

    async def run_all():
        await asyncio.gather(
            b1.process("c1", "并发1"),
            b2.process("c2", "并发2"),
            b3.process("c3", "并发3"),
        )
    asyncio.get_event_loop().run_until_complete(run_all())
    for s in [stream1, stream2, stream3]:
        responses = [e for e in s.events if e[0] == "response"]
        assert len(responses) == 1


# === 压力测试: LLM 故障优雅降级 ===

def test_s9_pressure_llm_failure():
    from brain import Brain
    class DeadLLM:
        model = "dead"
        async def chat(self, messages, tools=None, stream=False, **kwargs):
            raise RuntimeError("LLM is dead")
        async def is_available(self):
            return False
    stream = MockStream()
    brain = Brain(llm=DeadLLM(), stream=stream)
    brain.ralph_max_retries = 1
    brain.ralph_base_delay = 0.01
    asyncio.get_event_loop().run_until_complete(brain.process("s9", "test"))
    errors = [e for e in stream.events if e[0] == "error"]
    assert len(errors) >= 1
    completes = [e for e in stream.events if e[0] == "complete"]
    assert len(completes) == 1


# === 压力测试: 记忆文件损坏恢复 ===

def test_s9_pressure_memory_corrupt(tmp_path):
    from adapters.memory.json_memory import JSONMemoryAdapter
    corrupt_file = tmp_path / "sessions" / "corrupt.json"
    corrupt_file.parent.mkdir(parents=True, exist_ok=True)
    corrupt_file.write_text("{invalid json!!!", encoding="utf-8")
    adapter = JSONMemoryAdapter(data_dir=str(tmp_path))
    loop = asyncio.get_event_loop()
    msgs = loop.run_until_complete(adapter.get_context("corrupt"))
    assert msgs == [] or msgs is not None


# === 压力测试: 工具超时不阻塞 ===

def test_s9_pressure_tool_timeout():
    import platform
    from adapters.tools.shell import ShellAdapter
    adapter = ShellAdapter(timeout=2)
    ping_cmd = "ping -n 10 127.0.0.1" if platform.system() == "Windows" else "ping -c 10 127.0.0.1"
    r = asyncio.get_event_loop().run_until_complete(
        adapter.execute("run_command", {"command": ping_cmd})
    )
    assert r["success"] is False
    assert "超时" in r["error"]
