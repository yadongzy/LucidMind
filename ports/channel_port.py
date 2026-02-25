"""Channel Port — 接收用户输入的接口."""

from abc import ABC, abstractmethod
from typing import Any, Callable, Awaitable


class ChannelPort(ABC):
    """通道端口。Brain 通过此接口接收来自不同渠道的用户输入。"""

    @abstractmethod
    async def start(self, on_message: Callable[[str, str], Awaitable[None]]) -> None:
        """启动通道，注册消息回调。

        Args:
            on_message: 回调函数 (session_id, user_input) -> None
        """
        ...

    @abstractmethod
    async def stop(self) -> None:
        """停止通道。"""
        ...
