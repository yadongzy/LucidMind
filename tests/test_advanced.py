"""高级功能单元测试（S6记忆异常 + S7 Ralph + S8 自我感知/学习）。"""

import pytest
import asyncio


class DummyLLM:
    model = "test"
    async def chat(self, messages, tools=None, **kwargs):
        return {"content": "ok", "usage": {}}
    async def is_available(self):
        return True

class DummyStream:
    async def emit(self, t, d):
        pass


# === S6: 记忆异常测试（从 test_tools.py 移入） ===

def test_memory_empty_recall(tmp_path):
    """异常：查询不存在的记忆返回空列表。"""
    from adapters.memory.json_memory import JSONMemoryAdapter

    adapter = JSONMemoryAdapter(data_dir=str(tmp_path))
    results = asyncio.get_event_loop().run_until_complete(adapter.recall("不存在的内容"))
    assert results == []


def test_memory_nonexistent_session(tmp_path):
    """异常：加载不存在的会话返回空列表。"""
    from adapters.memory.json_memory import JSONMemoryAdapter

    adapter = JSONMemoryAdapter(data_dir=str(tmp_path))
    messages = asyncio.get_event_loop().run_until_complete(adapter.get_context("nonexistent"))
    assert messages == []


# === S7: Ralph 循环测试 ===

def test_ralph_retry_then_success():
    """正向：LLM 前两次失败，第三次成功 → Ralph 自动重试并最终成功。"""
    from brain import Brain

    call_count = 0

    class FailThenSuccessLLM:
        model = "test"
        async def chat(self, messages, tools=None, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError(f"Simulated failure #{call_count}")
            return {"content": "Ralph 重试成功！", "usage": {}}
        async def is_available(self):
            return True

    class CollectorStream:
        def __init__(self):
            self.events = []
        async def emit(self, event_type, data):
            self.events.append((event_type, data))

    stream = CollectorStream()
    brain = Brain(llm=FailThenSuccessLLM(), stream=stream)
    brain.ralph_max_retries = 3
    brain.ralph_base_delay = 0.01  # 快速测试

    asyncio.get_event_loop().run_until_complete(brain.process("test", "测试 Ralph"))

    assert call_count == 3, f"Expected 3 calls, got {call_count}"
    # 应有 info 事件告知重试
    info_events = [e for e in stream.events if e[0] == "info" and "Ralph" in str(e[1])]
    assert len(info_events) >= 1, "应有 Ralph 重试通知"
    # 最终应有成功回复
    responses = [e for e in stream.events if e[0] == "response"]
    assert len(responses) == 1
    assert "重试成功" in responses[0][1]


def test_ralph_all_retries_exhausted():
    """异常：所有重试均失败 → 诚实报告错误。"""
    from brain import Brain

    class AlwaysFailLLM:
        model = "test"
        async def chat(self, messages, tools=None, **kwargs):
            raise ConnectionError("Permanent failure")
        async def is_available(self):
            return True

    class CollectorStream:
        def __init__(self):
            self.events = []
        async def emit(self, event_type, data):
            self.events.append((event_type, data))

    stream = CollectorStream()
    brain = Brain(llm=AlwaysFailLLM(), stream=stream)
    brain.ralph_max_retries = 2
    brain.ralph_base_delay = 0.01

    asyncio.get_event_loop().run_until_complete(brain.process("test", "必定失败"))

    # 应有 error 事件（诚实报告）
    errors = [e for e in stream.events if e[0] == "error"]
    assert len(errors) >= 1, "应有错误事件"
    assert "Ralph" in str(errors[0][1]) or "失败" in str(errors[0][1])
    # 应有 complete 事件（不管成败都要 complete）
    completes = [e for e in stream.events if e[0] == "complete"]
    assert len(completes) == 1


def test_ralph_config_defaults():
    """Brain 默认 Ralph 配置正确。"""
    from brain import Brain
    brain = Brain(llm=DummyLLM(), stream=DummyStream())
    assert brain.ralph_max_retries == 3
    assert brain.ralph_base_delay == 2.0


# === S8: 自我感知 + 质量守卫测试 ===

def test_self_awareness_in_system_prompt():
    """正向：system prompt 包含动态自我感知信息（工具、模型、环境）。"""
    from brain import Brain
    from ports.tool_port import ToolPort

    class MockLLM:
        model = "deepseek-test"
        async def chat(self, messages, tools=None, **kwargs):
            return {"content": "ok", "usage": {}}
        async def is_available(self):
            return True

    class MockStream:
        async def emit(self, t, d):
            pass

    class MockTool(ToolPort):
        def list_tools(self):
            return [
                {"type": "function", "function": {"name": "run_command", "parameters": {}}},
                {"type": "function", "function": {"name": "web_search", "parameters": {}}},
            ]
        async def execute(self, tool_name, params):
            return {"success": True, "result": "ok", "error": None}

    brain = Brain(llm=MockLLM(), stream=MockStream(), tools=MockTool())
    import asyncio
    messages = asyncio.get_event_loop().run_until_complete(brain._build_messages())

    assert len(messages) >= 1, "应有 system prompt"
    system = messages[0]["content"]
    # 自我感知内容
    assert "run_command" in system, "system prompt 应包含工具名"
    assert "web_search" in system, "system prompt 应包含工具名"
    assert "deepseek-test" in system, "system prompt 应包含模型名"
    assert "历史" in system, "system prompt 应包含会话状态"
    assert "记忆" in system or "记忆系统" in system, "system prompt 应包含记忆状态"
    # 身份内容（来自 CORE.md / SOUL.md）
    assert "不可变内核" in system or "诚实" in system, "system prompt 应包含核心身份"


def test_soul_hot_reload(tmp_path):
    """正向：SOUL.md 修改后 Brain 自动重载。"""
    import brain as brain_module
    original_path = brain_module._SOUL_PATH
    fake_soul = tmp_path / "SOUL.md"
    fake_soul.write_text("# Version 1", encoding="utf-8")
    brain_module._SOUL_PATH = fake_soul

    try:
        import asyncio
        b = brain_module.Brain(llm=DummyLLM(), stream=DummyStream())
        msgs1 = asyncio.get_event_loop().run_until_complete(b._build_messages())
        assert "Version 1" in msgs1[0]["content"]

        # 修改 SOUL.md
        import time
        time.sleep(0.05)  # 确保 mtime 变化
        fake_soul.write_text("# Version 2 Updated", encoding="utf-8")

        msgs2 = asyncio.get_event_loop().run_until_complete(b._build_messages())
        assert "Version 2" in msgs2[0]["content"], "SOUL.md 修改后应自动重载"
        assert "Version 1" not in msgs2[0]["content"]
    finally:
        brain_module._SOUL_PATH = original_path


def test_self_awareness_no_tools():
    """异常：无工具时自我感知应显示"无"。"""
    from brain import Brain
    brain = Brain(llm=DummyLLM(), stream=DummyStream())
    awareness = brain._build_self_awareness()
    assert "可用工具" not in awareness, "无工具时不应包含工具列表"
    assert "test" in awareness, "应包含模型名"


# === S8: 经验学习测试 ===

def test_json_lessons_learn_and_recall(tmp_path):
    """正向：学习经验后能检索回来。"""
    from adapters.learning.json_lessons import JSONLessonsAdapter

    adapter = JSONLessonsAdapter(data_dir=str(tmp_path))
    loop = asyncio.get_event_loop()

    loop.run_until_complete(adapter.learn({
        "trigger": "用户纠正: Python 是编译型语言",
        "lesson": "Python 是解释型语言，不是编译型",
        "source_session": "test",
    }))

    results = loop.run_until_complete(adapter.get_lessons("Python 语言类型", limit=3))
    assert len(results) >= 1, "应检索到相关经验"
    assert "解释型" in results[0]["lesson"]


def test_json_lessons_dedup(tmp_path):
    """正向：相同 trigger 的经验应合并而非重复。"""
    from adapters.learning.json_lessons import JSONLessonsAdapter

    adapter = JSONLessonsAdapter(data_dir=str(tmp_path))
    loop = asyncio.get_event_loop()

    loop.run_until_complete(adapter.learn({
        "trigger": "关于 X 的错误",
        "lesson": "第一次纠正",
    }))
    loop.run_until_complete(adapter.learn({
        "trigger": "关于 X 的错误",
        "lesson": "第二次纠正（更准确）",
    }))

    assert len(adapter._lessons) == 1, f"相同 trigger 应合并，实际 {len(adapter._lessons)} 条"
    assert "第二次" in adapter._lessons[0]["lesson"]


def test_json_lessons_empty_context(tmp_path):
    """异常：空上下文应返回空列表。"""
    from adapters.learning.json_lessons import JSONLessonsAdapter

    adapter = JSONLessonsAdapter(data_dir=str(tmp_path))
    results = asyncio.get_event_loop().run_until_complete(adapter.get_lessons(""))
    assert results == []


def test_brain_detect_correction():
    """正向：用户说"不对"时 Brain 触发学习。"""
    from brain import Brain
    from ports.learning_port import LearningPort

    learned = []

    class MockLLM:
        model = "test"
        call_count = 0
        async def chat(self, messages, tools=None, **kwargs):
            self.call_count += 1
            if self.call_count == 1:
                return {"content": "Python 是编译型语言", "usage": {}}
            # 第3+次调用是 _detect_learning_signal，返回 "correction" 触发学习
            last_content = messages[-1].get("content", "") if messages else ""
            if "纠正" in last_content or "correction" in last_content or "teaching" in last_content:
                return {"content": "correction", "usage": {}}
            return {"content": "你说得对，Python 是解释型语言", "usage": {}}
        async def is_available(self):
            return True

    class MockStream:
        def __init__(self):
            self.events = []
        async def emit(self, t, d):
            self.events.append((t, d))

    class MockLearning(LearningPort):
        async def learn(self, experience):
            learned.append(experience)
        async def get_lessons(self, context, limit=3):
            return []

    stream = MockStream()
    brain = Brain(llm=MockLLM(), stream=stream, learning=MockLearning())

    loop = asyncio.get_event_loop()
    loop.run_until_complete(brain.process("test", "Python 是什么类型的语言"))
    loop.run_until_complete(brain.process("test", "不对，Python 是解释型语言"))

    assert len(learned) >= 1, f"应触发学习，实际 {len(learned)} 条"
    info_events = [e for e in stream.events if e[0] == "info" and ("学习" in str(e[1]) or "纠正" in str(e[1]) or "学会" in str(e[1]))]
    assert len(info_events) >= 1, f"应有学习通知, 实际events={stream.events}"
