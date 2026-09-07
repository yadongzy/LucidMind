"""CollectStreamAdapter — 收集所有流事件到内存（用于 HTTP API 通道）。"""
from ports.stream_port import StreamPort
from logs import get_logger

logger = get_logger("stream")


class CollectStreamAdapter(StreamPort):
    """将所有 stream 事件收集到内存，供 HTTP 同步返回。"""

    def __init__(self):
        self.reply = ""
        self.thinking: list[str] = []
        self._events: list[tuple[str, str]] = []

    async def emit(self, event_type: str, data: str) -> None:
        self._events.append((event_type, data))
        if event_type == "response":
            self.reply = data
        elif event_type == "response_delta":
            self.reply += data
        elif event_type == "thinking":
            self.thinking.append(data)
