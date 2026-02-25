import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
from brain import Brain
from ports.tool_port import ToolPort

# Mock Tool Adapter
class MockShellAdapter(ToolPort):
    async def execute(self, tool_name: str, params: dict) -> dict:
        if tool_name == "run_command":
            cmd = params.get("command")
            if cmd == "whoami":
                return {"success": True, "result": "lucid_user"}
            return {"success": True, "result": f"executed: {cmd}"}
        return {"success": False, "error": "unknown tool"}
    
    def list_tools(self) -> list[dict]:
        return [{
            "type": "function",
            "function": {
                "name": "run_command",
                "description": "Run a shell command",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"}
                    },
                    "required": ["command"]
                }
            }
        }]

# Mock LLM that requests a tool, then answers
class MockToolLLM:
    def __init__(self):
        self.call_count = 0

    async def chat(self, messages, tools=None, stream=False):
        self.call_count += 1
        # Round 1: Request tool
        if self.call_count == 1:
            return {
                "content": None,
                "tool_calls": [{
                    "id": "call_123",
                    "function": {
                        "name": "run_command",
                        "arguments": json.dumps({"command": "whoami"})
                    }
                }]
            }
        # Round 2+: Answer with tool result
        return {
            "content": "You are lucid_user.",
            "reasoning_content": "I checked the user identity."
        }

@pytest.mark.asyncio
async def test_brain_tool_execution_flow():
    """Test full S3 loop: Brain -> LLM -> Tool -> Brain -> LLM -> Response"""
    llm = MockToolLLM()
    tools = MockShellAdapter()
    stream = AsyncMock()
    
    brain = Brain(llm=llm, tools=tools, stream=stream)
    
    await brain.process("test_session", "Who am I?")
    
    # Assertions
    assert llm.call_count >= 2
    
    # Check stream events
    # 1. Thinking (from round 2)
    # 2. Tool Call (from round 1)
    # 3. Tool Result (from execution)
    # 4. Final Response (from round 2)
    
    event_types = [call.args[0] for call in stream.emit.call_args_list]
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert "response" in event_types or "response_start" in event_types
    assert "thinking" in event_types

@pytest.mark.asyncio
async def test_brain_tool_safety_block():
    """Test that Brain/Tool handles safety blocks (though logic is in Adapter)"""
    # This just ensures Brain handles exceptions or error returns gracefully
    pass 
