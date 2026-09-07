"""S30-S33: Brain 生命周期管理 — 单例/Daemon/Soul/Goals/Teaching。"""
import asyncio
from fastapi import APIRouter
from pydantic import BaseModel
from brain_daemon import BrainDaemon
from identity.soul_engine import SoulEngine
from identity.goals import GoalSystem
from teacher_channel import TeacherChannel
from logs import get_logger

logger = get_logger("brain_init")
router = APIRouter(prefix="/api/brain", tags=["brain"])

soul_engine = SoulEngine()
goal_system = GoalSystem()
teacher = TeacherChannel()
daemon: BrainDaemon | None = None
_brain_ref = None  # Brain 单例引用
_ws_channel_ref = None  # WebSocket 通道引用


def set_ws_channel(ws_ch):
    global _ws_channel_ref
    _ws_channel_ref = ws_ch


def set_brain(brain):
    global _brain_ref
    _brain_ref = brain


async def awaken(brain=None) -> dict:
    """唤醒大脑 — 启动后台思考 + 注入目标。"""
    global daemon, _brain_ref
    b = brain or _brain_ref
    if not b:
        return {"status": "error", "message": "Brain not initialized"}
    if daemon and daemon._running:
        return {"status": "already_awake"}
    _brain_ref = b
    teacher.set_brain(b)
    daemon = BrainDaemon(b, interval=60, soul_engine=soul_engine, goal_system=goal_system,
                         teacher_channel=teacher, ws_channel=_ws_channel_ref)
    await daemon.start()
    goals_ctx = goal_system.get_context_for_brain()
    if goals_ctx:
        b._goal_context = goals_ctx
        logger.info(f"🎯 注入 {len(goal_system.get_active_goals())} 个目标")
    # S59: 启动 Cron 调度器（回调由 main.py 在 _startup 中注册）
    try:
        from api.cron import start_cron_scheduler
        asyncio.create_task(start_cron_scheduler())
        logger.info("⏰ Cron 调度器已启动")
    except Exception as e:
        logger.warning(f"Cron 启动失败: {e}")
    logger.info("🧠 大脑已完全醒来 — Daemon + Soul + Goals + Cron + Teacher 就绪")
    return {"status": "awake", "goals": len(goal_system.get_active_goals()),
            "soul_lines": soul_engine.get_soul().count("\n"), "daemon": "running",
            "teacher": "connected"}


@router.get("/status")
async def brain_status():
    """大脑生命状态。"""
    return {
        "awake": _brain_ref._awake if _brain_ref else False,
        "daemon": daemon.get_status() if daemon else {"running": False},
        "goals": {"active": len(goal_system.get_active_goals()), "total": len(goal_system.get_all())},
        "soul_evolutions": len(soul_engine.get_evolution_history()),
    }


@router.post("/awaken")
async def api_awaken():
    """唤醒大脑。"""
    return await awaken()


@router.post("/sleep")
async def api_sleep():
    """让大脑休眠。"""
    global daemon
    if daemon:
        await daemon.stop()
    # 同时停掉 cron 调度循环，防止下次 awaken 重复启动导致任务双倍触发
    try:
        from api.cron import stop_cron_scheduler
        stop_cron_scheduler()
    except Exception:
        pass
    if _brain_ref:
        _brain_ref._awake = False
    return {"status": "sleeping"}


@router.post("/pause")
async def api_pause():
    """暂停大脑任务驱动（自检和教学继续）。"""
    if daemon:
        daemon._paused = True
        logger.info("⏸ 大脑任务已暂停")
    return {"status": "ok", "paused": True}


@router.post("/resume")
async def api_resume():
    """恢复大脑任务驱动。"""
    if daemon:
        daemon._paused = False
        logger.info("▶ 大脑任务已恢复")
    return {"status": "ok", "paused": False}


@router.post("/confirm")
async def api_confirm(req: dict | None = None):
    """用户确认执行大脑的计划。"""
    req = req or {}
    if daemon:
        plan = req.get("plan", "")
        daemon.confirm_plan(plan)
    return {"status": "ok", "confirmed": True}


@router.post("/skip")
async def api_skip():
    """跳过大脑当前待确认的计划。"""
    if daemon:
        daemon._pending_plan = None
        daemon._user_confirmed = False
        logger.info("⏭ 用户跳过当前计划")
    return {"status": "ok", "skipped": True}


@router.post("/interval")
async def api_interval(req: dict):
    """设置大脑思考间隔。"""
    if daemon and "interval" in req:
        daemon._interval = int(req["interval"])
        logger.info(f"⏱ 思考间隔设为 {daemon._interval}s")
    return {"status": "ok", "interval": daemon._interval if daemon else 300}


@router.post("/auto-ask")
async def api_auto_ask(req: dict):
    """设置大脑是否自动向老师提问。"""
    enabled = req.get("enabled", True)
    if daemon and daemon._teacher:
        daemon._teacher._auto_ask_enabled = enabled
        logger.info(f"🎓 自动提问: {'开' if enabled else '关'}")
    return {"status": "ok", "enabled": enabled}


@router.get("/goals")
async def api_goals():
    """获取目标列表。"""
    return {"goals": goal_system.get_all()}


@router.post("/goals")
async def api_add_goal(content: str, goal_type: str = "short_term"):
    """添加目标。"""
    g = goal_system.add_goal(content, goal_type)
    return {"goal": g}


@router.get("/soul/history")
async def api_soul_history():
    """灵魂进化历史。"""
    return {"history": soul_engine.get_evolution_history()}


@router.get("/thoughts")
async def api_thoughts():
    """后台思考日志。"""
    if daemon:
        return {"thoughts": daemon._thought_log[-10:]}
    return {"thoughts": []}


# ─── 教学通道 API（Cascade 用这些接口与大脑沟通）───

@router.get("/teaching/inbox")
async def teaching_inbox():
    """老师(Cascade)读取大脑发来的消息。"""
    return {"messages": teacher.get_inbox(unread_only=False),
            "pending": len(teacher.get_inbox(unread_only=True))}


class TeacherReply(BaseModel):
    msg_id: int
    answer: str
    action: str = ""
    exercise: str = ""


@router.post("/teaching/reply")
async def teaching_reply(req: TeacherReply):
    """老师(Cascade)回复大脑的消息。"""
    msg = teacher.reply_to_brain(req.msg_id, req.answer, req.action, req.exercise)
    return {"status": "ok", "reply": msg}


@router.get("/teaching/status")
async def teaching_status():
    """教学通道状态（含成长阶段）。"""
    status = teacher.get_status()
    try:
        from growth_stage import get_current_stage, STAGES
        stage_data = get_current_stage()
        stage_num = stage_data.get("stage_num", 1)
        stage_info = STAGES.get(stage_num, STAGES[1])
        status["growth_stage"] = {
            "name": stage_info["name"], "label": stage_info["label"],
            "lesson_count": stage_data.get("lesson_count", 0),
            "teacher_freq": stage_info["teacher_freq"],
        }
    except Exception:
        status["growth_stage"] = {"name": "unknown"}
    return status
