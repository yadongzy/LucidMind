"""CLI Stream Adapter — 将思维流输出到终端。"""

import sys
from typing import Any

from ports.stream_port import StreamPort
from logs import get_logger

logger = get_logger("stream")

# ANSI 颜色
_COLORS = {
    "thinking": "\033[36m",   # 青色
    "tool_call": "\033[33m",  # 黄色
    "tool_result": "\033[90m",  # 灰色
    "info": "\033[90m",       # 灰色
    "response": "\033[32m",   # 绿色
    "error": "\033[31m",      # 红色
    "complete": "",
}
_RESET = "\033[0m"
_LABELS = {
    "thinking": "💭 思考",
    "tool_call": "🔧 工具",
    "tool_result": "📋 结果",
    "info": "ℹ️  信息",
    "response": "🤖 回复",
    "error": "❌ 错误",
    "complete": "",
}


class CLIStreamAdapter(StreamPort):
    """终端思维流适配器。将 Brain 的思考过程输出到 stdout。"""

    def __init__(self, show_thinking: bool = True):
        self._show_thinking = show_thinking

    async def emit(self, event_type: str, data: Any) -> None:
        if event_type == "complete":
            return
        if event_type == "thinking" and not self._show_thinking:
            return

        color = _COLORS.get(event_type, "")
        label = _LABELS.get(event_type, event_type)
        text = str(data) if data else ""

        if event_type == "response":
            print(f"\n{color}{label}:{_RESET}\n{text}\n")
        elif text:
            # 截断过长内容
            display = text[:500] + "..." if len(text) > 500 else text
            print(f"{color}{label}: {display}{_RESET}")

        logger.debug(f"CLI 输出: type={event_type}, len={len(text)}")
