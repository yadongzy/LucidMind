"""Cascade Inject API — 大脑通过 HTTP 把消息写入 teacher_inbox。

大脑调用此端点 → 消息写入 teacher_inbox.json → Cascade 通过 skill 读取并回复。
跨平台兼容（Windows/macOS/Linux），不依赖 GUI 自动化。
"""

from fastapi import APIRouter
from pydantic import BaseModel
from logs import get_logger

logger = get_logger("api.cascade_inject")
router = APIRouter()


class InjectRequest(BaseModel):
    message: str


@router.post("/api/cascade/inject")
async def cascade_inject(req: InjectRequest):
    """大脑通过 HTTP 把消息写入 teacher_inbox（跨平台）。"""
    message = req.message.strip()
    if not message:
        return {"status": "error", "detail": "消息不能为空"}

    try:
        from teacher_channel import TeacherChannel
        from api.brain_init import teacher
        msg = teacher.send_to_teacher(
            msg_type="question",
            content=message,
            context="via cascade_inject API",
            urgency="normal",
        )
        logger.info(f"消息已写入 inbox: #{msg['id']} {message[:80]}")
        return {"status": "ok", "injected": True, "msg_id": msg["id"]}

    except Exception as e:
        logger.error(f"注入失败: {e}")
        return {"status": "error", "detail": str(e)}
