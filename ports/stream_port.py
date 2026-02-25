"""Stream Port — 思维流输出的接口."""

from abc import ABC, abstractmethod
from typing import Any


class StreamPort(ABC):
    """思维流端口。Brain 通过此接口向用户展示思考过程。"""

    @abstractmethod
    async def emit(self, event_type: str, data: Any) -> None:
        """发送一个思维流事件。

        Args:
            event_type: 事件类型 ("thinking" | "tool_call" | "response" | "error" | "complete")
            data: 事件数据
        """
        ...
