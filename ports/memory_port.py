"""Memory Port — 记忆存取的接口."""

from abc import ABC, abstractmethod
from typing import Any


class MemoryPort(ABC):
    """记忆端口。Brain 通过此接口存取记忆。"""

    @abstractmethod
    async def save(self, key: str, value: Any, category: str = "general") -> None:
        """保存一条记忆。"""
        ...

    @abstractmethod
    async def recall(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """根据查询检索相关记忆。"""
        ...

    @abstractmethod
    async def get_context(self, session_id: str) -> list[dict[str, Any]]:
        """获取指定会话的对话历史。"""
        ...

    @abstractmethod
    async def save_message(self, session_id: str, message: dict[str, Any]) -> None:
        """保存一条对话消息到会话历史。"""
        ...
