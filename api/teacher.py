"""Teacher API — Cascade 老师向大脑前端推送消息 + 写入 outbox 让 daemon 执行。"""

from fastapi import APIRouter
from pydantic import BaseModel
from logs import get_logger

logger = get_logger("api.teacher")
router = APIRouter()

_ws_channel = None
_teacher_channel = None


def init(ws_channel, teacher_channel=None):
    """注入 WebSocket 通道和 TeacherChannel 引用。"""
    global _ws_channel, _teacher_channel
    _ws_channel = ws_channel
    _teacher_channel = teacher_channel


class TeacherMessage(BaseModel):
    message: str
    session_id: str = "default"


@router.post("/api/teacher/send")
async def teacher_send(req: TeacherMessage):
    """Cascade 老师发消息：推送前端 + 写入 outbox（daemon 自动执行）。"""
    if not _ws_channel:
        return {"status": "error", "sent": False, "detail": "通道未初始化"}
    sent = False
    for conn_id, ws in list(_ws_channel._connections.items()):
        try:
            await ws.send_json({"type": "response", "data": req.message})
            await ws.send_json({"type": "complete", "data": None})
            sent = True
        except Exception:
            pass

    # 同时写入 outbox，让 daemon 的 process_teacher_replies 能读到并执行
    if _teacher_channel:
        _teacher_channel.reply_to_brain(
            inbox_msg_id=0,
            answer=req.message,
            action=req.message,
        )
        logger.info(f"老师回复已写入 outbox + 推送前端: {req.message[:50]}")

    # 唤醒 Daemon 立即处理老师消息
    try:
        from api.brain_init import daemon as _daemon
        if _daemon:
            _daemon.wake()
    except Exception:
        pass

    if sent:
        return {"status": "ok", "sent": True}
    return {"status": "error", "sent": False, "detail": "无活跃WebSocket连接"}


class _CollectorStream:
    """轻量级流收集器 — 收集 Brain 的流式输出，不推送到前端。"""
    def __init__(self):
        self.events = []
    async def emit(self, event_type: str, data=None):
        self.events.append({"type": event_type, "data": str(data)[:500] if data else ""})


@router.post("/api/teacher/direct")
async def teacher_direct(req: TeacherMessage):
    """直接执行教学指令 — 绕过 Daemon 队列，同步调用 Brain.process()。
    
    用于加速教学：不排队、不等轮询，直接LLM执行并返回结果。
    """
    from api.brain_init import _brain_ref
    if not _brain_ref:
        return {"status": "error", "detail": "Brain 未初始化"}
    
    old_stream = getattr(_brain_ref, '_stream', None)
    collector = _CollectorStream()
    _brain_ref.set_stream(collector)
    
    sid = f"teach_{req.session_id}"
    try:
        await _brain_ref.process(sid, req.message)
        # 提取最终回复
        response_parts = [e["data"] for e in collector.events if e["type"] in ("response", "response_delta")]
        response = "".join(response_parts)
        # 提取思考过程
        thinking = "".join(e["data"] for e in collector.events if e["type"] == "thinking")
        # 记录到 inbox（让老师能看到回复）
        if _teacher_channel:
            _teacher_channel.send_to_teacher(
                msg_type="report",
                content=response[:500] if response else "(无回复)",
                context=f"direct_teach: {req.message[:100]}",
                urgency="low"
            )
    except Exception as e:
        response = f"执行失败: {e}"
        thinking = ""
    finally:
        # 保留session历史，让后续消息能检测到纠正（需要前一条助手回复做上下文）
        if old_stream:
            _brain_ref.set_stream(old_stream)
    
    return {
        "status": "ok",
        "response": response,
        "thinking": thinking[:300] if thinking else "",
        "events_count": len(collector.events),
    }
