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


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    thinking: list[str] = []


@router.post("", response_model=ChatResponse)
async def http_chat(req: ChatRequest):
    """HTTP 对话端点 — 同步返回完整回复。"""
    from adapters.stream.collect_stream import CollectStreamAdapter
    if not _brain_factory:
        return ChatResponse(reply="Brain 未初始化", session_id=req.session_id)

    collector = CollectStreamAdapter()
    brain = _brain_factory(collector)
    await brain.process(req.session_id, req.message)

    logger.info(f"HTTP 对话: session={req.session_id}, input={req.message[:50]}, reply={len(collector.reply)}字")
    return ChatResponse(reply=collector.reply, session_id=req.session_id, thinking=collector.thinking)
