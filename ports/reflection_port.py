"""Reflection Port — 自省接口。

Brain 通过此接口感知用户行为模式、检测重复、反思自身表现。
"""

from abc import ABC, abstractmethod
from typing import Any


class ReflectionPort(ABC):
    """自省端口：用户行为分析 + 重复检测 + 工具循环检测 + 反思。"""

    @abstractmethod
    async def on_user_message(self, session_id: str, message: str) -> dict[str, Any]:
        """用户消息到达时调用。返回分析结果（重复检测、行为模式等）。"""
        ...

    @abstractmethod
    async def on_tool_call(self, session_id: str, tool_name: str, params: dict) -> dict[str, Any]:
        """工具调用时调用。返回循环检测结果。"""
        ...

    @abstractmethod
    async def get_reflection(self, session_id: str) -> str:
        """获取当前反思摘要，注入 system prompt。"""
        ...
