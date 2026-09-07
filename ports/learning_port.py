"""Learning Port — 经验学习的接口."""

from abc import ABC, abstractmethod
from typing import Any


class LearningPort(ABC):
    """学习端口。Brain 通过此接口记录和检索经验教训。"""

    @abstractmethod
    async def learn(self, experience: dict[str, Any]) -> None:
        """记录一条经验。

        Args:
            experience: {"type": str, "input": str, "lesson": str, "timestamp": str}
        """
        ...

    @abstractmethod
    async def get_lessons(self, context: str, limit: int = 3) -> list[dict[str, Any]]:
        """根据当前上下文检索相关经验教训。"""
        ...
