"""Collector Stream — 收集 Brain 输出文本，用于非 WebSocket 通道（Telegram/飞书等）。"""

from typing import Any
from ports.stream_port import StreamPort


class CollectorStreamAdapter(StreamPort):
    """将 Brain 的流式输出收集到内存中，供一次性获取。"""

    def __init__(self):
        self._chunks: list[str] = []
        self._complete = False

    async def emit(self, event_type: str, data: Any) -> None:
        if event_type == "response" and data:
            self._chunks.append(str(data))
        elif event_type == "complete":
            self._complete = True

    def get_text(self) -> str:
        return "".join(self._chunks)

    @property
    def complete(self) -> bool:
        return self._complete
