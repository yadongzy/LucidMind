"""S22: HTTP API 通道 — RESTful 对话接口（无需 WebSocket）。

用途: 第三方集成、Telegram Bot webhook、自动化脚本调用。
"""
from fastapi import APIRouter
from pydantic import BaseModel

from logs import get_logger

logger = get_logger("channel")
router = APIRouter(prefix="/api/chat", tags=["chat"])

# 延迟绑定
_brain_factory = None


def init(brain_factory):
    """注入 Brain 工厂函数。"""
    global _brain_factory
    _brain_factory = brain_factory


class ChatRequest(BaseModel):
    message: str
    session_id: str = "http_default"
    attachments: list[dict] = []


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    thinking: list[str] = []


@router.post("", response_model=ChatResponse)
async def http_chat(req: ChatRequest):
    """HTTP 对话端点 — 同步返回完整回复。支持 attachments（图片/文件）。"""
    from adapters.stream.collect_stream import CollectStreamAdapter
    from adapters.channel.websocket_channel import _compose_with_attachments
    if not _brain_factory:
        return ChatResponse(reply="Brain 未初始化", session_id=req.session_id)

    user_input = req.message or ""
    if req.attachments:
        user_input = _compose_with_attachments(user_input, req.attachments)

    collector = CollectStreamAdapter()
    brain = _brain_factory(collector)
    await brain.process(req.session_id, user_input)

    logger.info(f"HTTP 对话: session={req.session_id}, input={user_input[:80]}, attachments={len(req.attachments)}, reply={len(collector.reply)}字")
    return ChatResponse(reply=collector.reply, session_id=req.session_id, thinking=collector.thinking)
