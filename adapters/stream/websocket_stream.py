"""WebSocket Stream Adapter — 通过 WebSocket 向前端推送思维流。"""

import json
from typing import Any

from fastapi import WebSocket

from ports.stream_port import StreamPort
from logs import get_logger

logger = get_logger("stream")


class WebSocketStreamAdapter(StreamPort):
    """WebSocket 思维流适配器。将 Brain 的思考过程实时推送给前端。
    S59: 支持连接池模式 — 通过 ws_holder 获取最新活跃连接，
    避免旧连接断开后回复丢失。
    """

    def __init__(self, websocket: WebSocket, ws_holder: dict | None = None):
        self.ws = websocket
        self._holder = ws_holder  # {"ws": WebSocket} — 外部维护的活跃连接引用
        self._closed = False
        self._error_count = 0

    async def emit(self, event_type: str, data: Any) -> None:
        """发送思维流事件到 WebSocket。通过 ws_holder 自动路由到最新连接。"""
        # S59: 优先使用 holder 中的最新连接
        ws = self._holder["ws"] if self._holder and self._holder.get("ws") else self.ws
        # 连接已更新时重置错误状态（页面刷新后新连接可用）
        if ws is not self.ws and self._closed:
            self._closed = False
            self._error_count = 0
            logger.info(f"[STREAM] 连接已更新，重置错误状态 → ws={id(ws)}")
        if self._closed:
            return
        ws_id = id(ws)
        try:
            message = json.dumps(
                {"type": event_type, "data": data},
                ensure_ascii=False,
            )
            await ws.send_text(message)
            self._error_count = 0
            if event_type != "response_delta":
                logger.info(f"[STREAM] ✅ type={event_type} → ws={ws_id} data={str(data)[:80]}")
        except Exception as e:
            self._error_count += 1
            if self._error_count <= 3:
                logger.warning(f"WebSocket 发送失败: type={event_type}, ws={ws_id}, 错误={e}")
            if self._error_count == 3:
                logger.warning("WebSocket 连续3次发送失败，后续静默跳过")
            if "close" in str(e).lower() or "disconnect" in str(e).lower():
                self._closed = True
