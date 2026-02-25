"""LLM Port — 与大语言模型对话的接口."""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Any


class LLMPort(ABC):
    """大语言模型端口。Brain 通过此接口与任何 LLM 对话。"""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
    ) -> dict[str, Any] | AsyncIterator[str]:
        """发送消息给 LLM，返回回复。

        Args:
            messages: 对话消息列表 [{"role": "user", "content": "..."}]
            tools: 可用工具定义列表（可选）
            stream: 是否流式返回

        Returns:
            非流式: {"content": "...", "tool_calls": [...]} 
            流式: 异步迭代器，逐 token 返回
        """
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """检查此 LLM 是否可用。"""
        ...
