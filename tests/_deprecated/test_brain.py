"""Brain 核心单元测试（S0 骨架 + S1 LLM + S2 思维流）。

从原 test_brain.py 拆分，符合第三条代码边界（≤300行）。
工具测试见 test_tools.py，高级功能测试见 test_advanced.py。
"""

import pytest
import asyncio


# === S0: 骨架测试 ===

def test_ports_importable():
    """所有 Port 接口可导入。"""
    from ports.llm_port import LLMPort
    from ports.tool_port import ToolPort
    from ports.memory_port import MemoryPort
    from ports.stream_port import StreamPort
    from ports.channel_port import ChannelPort
    from ports.learning_port import LearningPort

    assert LLMPort is not None
    assert ToolPort is not None
    assert MemoryPort is not None
    assert StreamPort is not None
    assert ChannelPort is not None
    assert LearningPort is not None


def test_brain_importable():
    """Brain 类可导入。"""
    from brain import Brain
    assert Brain is not None


def test_api_health():
    """API 健康检查端点存在。"""
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"


# === S1: LLM + Stream 适配器测试 ===

def test_deepseek_adapter_importable():
    """DeepSeek 适配器可导入且实现 LLMPort。"""
    from adapters.llm.deepseek import DeepSeekAdapter
    from ports.llm_port import LLMPort

    adapter = DeepSeekAdapter(api_key="test-key")
    assert isinstance(adapter, LLMPort)


def test_websocket_stream_importable():
    """WebSocket Stream 适配器可导入且实现 StreamPort。"""
    from adapters.stream.websocket_stream import WebSocketStreamAdapter
    from ports.stream_port import StreamPort

    # WebSocketStreamAdapter 需要一个 WebSocket 对象，这里只测导入
    assert WebSocketStreamAdapter is not None


def test_brain_with_thinking():
    """LLM 返回 <think> 标签时，Brain 提取真实思考并分流。"""
    from brain import Brain
    from ports.llm_port import LLMPort
    from ports.stream_port import StreamPort

    class MockLLM(LLMPort):
        async def chat(self, messages, tools=None, stream=False, **kwargs):
            return {
                "content": "<think>用户在打招呼，简短回复即可。</think>\n你好！",
                "usage": {"total_tokens": 50},
            }
        async def is_available(self):
            return True

    class MockStream(StreamPort):
        def __init__(self):
            self.events = []
        async def emit(self, event_type, data):
            self.events.append((event_type, data))

    mock_stream = MockStream()
    brain = Brain(llm=MockLLM(), stream=mock_stream)

    asyncio.get_event_loop().run_until_complete(
        brain.process("test-session", "你好")
    )

    types = [e[0] for e in mock_stream.events]
    # 有真实思考 → thinking 事件存在
    assert "thinking" in types
    # 系统信息（耗时/tokens）→ info 事件
    assert "info" in types
    assert "response" in types
    assert "complete" in types

    # thinking 内容来自 LLM，不是模板
    thinking_data = [e[1] for e in mock_stream.events if e[0] == "thinking"][0]
    assert "用户在打招呼" in thinking_data

    # response 不含 <think> 标签
    response_data = [e[1] for e in mock_stream.events if e[0] == "response"][0]
    assert "<think>" not in response_data
    assert "你好" in response_data


def test_brain_no_thinking():
    """LLM 不返回思考时，不伪造 thinking 事件。"""
    from brain import Brain
    from ports.llm_port import LLMPort
    from ports.stream_port import StreamPort

    class MockLLM(LLMPort):
        async def chat(self, messages, tools=None, stream=False, **kwargs):
            return {"content": "直接回复"}
        async def is_available(self):
            return True

    class MockStream(StreamPort):
        def __init__(self):
            self.events = []
        async def emit(self, event_type, data):
            self.events.append((event_type, data))

    mock_stream = MockStream()
    brain = Brain(llm=MockLLM(), stream=mock_stream)

    asyncio.get_event_loop().run_until_complete(
        brain.process("test-session", "你好")
    )

    types = [e[0] for e in mock_stream.events]
    # 没有思考内容 → 没有 thinking 事件（不伪造）
    assert "thinking" not in types
    # 仍然有 info 和 response
    assert "info" in types
    assert "response" in types
    assert "complete" in types


def test_brain_reasoning_content():
    """LLM 返回 reasoning_content 字段时（如 DeepSeek-R1），优先使用。"""
    from brain import Brain
    from ports.llm_port import LLMPort
    from ports.stream_port import StreamPort

    class MockLLM(LLMPort):
        async def chat(self, messages, tools=None, stream=False, **kwargs):
            return {
                "content": "你好！",
                "reasoning_content": "这是一个简单的问候，不需要工具。",
            }
        async def is_available(self):
            return True

    class MockStream(StreamPort):
        def __init__(self):
            self.events = []
        async def emit(self, event_type, data):
            self.events.append((event_type, data))

    mock_stream = MockStream()
    brain = Brain(llm=MockLLM(), stream=mock_stream)

    asyncio.get_event_loop().run_until_complete(
        brain.process("test-session", "你好")
    )

    thinking_data = [e[1] for e in mock_stream.events if e[0] == "thinking"][0]
    assert "简单的问候" in thinking_data


def test_brain_error_handling():
    """Brain 在 LLM 调用失败时发送 error 事件。"""
    from brain import Brain
    from ports.llm_port import LLMPort
    from ports.stream_port import StreamPort

    class FailingLLM(LLMPort):
        async def chat(self, messages, tools=None, stream=False, **kwargs):
            raise ConnectionError("API 连接失败")
        async def is_available(self):
            return False

    class MockStream(StreamPort):
        def __init__(self):
            self.events = []
        async def emit(self, event_type, data):
            self.events.append((event_type, data))

    mock_stream = MockStream()
    brain = Brain(llm=FailingLLM(), stream=mock_stream)

    asyncio.get_event_loop().run_until_complete(
        brain.process("test-session", "你好")
    )

    types = [e[0] for e in mock_stream.events]
    assert "error" in types
    assert "complete" in types
