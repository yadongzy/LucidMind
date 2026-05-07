"""Goal Tracker — 轻量目标追踪器（只读状态记录，不排队不调度不执行）。

方案D核心组件：
- Chat路径 → brain.process()直连 → 步骤实时推送 → Goal Tracker记录状态
- Daemon路径 → task_dispatcher不变
- 两者互不干扰，无并发竞争

设计原则（David Harel Statecharts）：
- Goal Tracker 是只读记录器，不参与调度和执行
- 状态转换由调用方（websocket_channel）决定
- 通过 WebSocket 广播实时推送步骤事件到前端
"""

import asyncio
import json
import time
import uuid

from logs import get_logger

logger = get_logger("goal_tracker")

# ---------- 全局状态 ----------
_goals: dict[str, dict] = {}          # goal_id → goal
_session_goals: dict[str, str] = {}   # session_id → active goal_id
_ws_channel = None                     # WebSocket通道引用（由 api/main.py 注入）


def set_ws_channel(ch):
    """注入 WebSocket 通道用于广播 goal 更新事件。"""
    global _ws_channel
    _ws_channel = ch


def create_goal(session_id: str, description: str) -> str:
    """创建新目标，返回 goal_id。"""
    goal_id = f"goal_{uuid.uuid4().hex[:8]}"
    goal = {
        "id": goal_id,
        "session_id": session_id,
        "description": description[:200],
        "steps": [],
        "status": "running",
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    _goals[goal_id] = goal
    _session_goals[session_id] = goal_id
    _broadcast("goal_created", goal)
    logger.info(f"🎯 目标创建: {goal_id} [{description[:40]}]")
    return goal_id


def add_step(goal_id: str, step_name: str, detail: str = ""):
    """记录一个执行步骤（实时推送到前端）。"""
    goal = _goals.get(goal_id)
    if not goal:
        return
    step = {"name": step_name, "detail": detail[:100], "ts": time.time()}
    goal["steps"].append(step)
    goal["updated_at"] = time.time()
    _broadcast("goal_step", goal)


def complete_goal(goal_id: str):
    """标记目标完成。"""
    goal = _goals.get(goal_id)
    if not goal or goal["status"] != "running":
        return
    goal["status"] = "completed"
    goal["updated_at"] = time.time()
    sid = goal.get("session_id")
    if sid:
        _session_goals.pop(sid, None)
    _broadcast("goal_completed", goal)
    logger.info(f"✅ 目标完成: {goal_id}")


def fail_goal(goal_id: str, reason: str = ""):
    """标记目标失败。"""
    goal = _goals.get(goal_id)
    if not goal or goal["status"] != "running":
        return
    goal["status"] = "failed"
    goal["error"] = reason[:200]
    goal["updated_at"] = time.time()
    sid = goal.get("session_id")
    if sid:
        _session_goals.pop(sid, None)
    _broadcast("goal_failed", goal)
    logger.warning(f"❌ 目标失败: {goal_id} [{reason[:60]}]")


def get_session_goal(session_id: str) -> str | None:
    """获取会话的活跃目标 ID。"""
    gid = _session_goals.get(session_id)
    if gid and _goals.get(gid, {}).get("status") == "running":
        return gid
    _session_goals.pop(session_id, None)
    return None


def get_goals() -> list[dict]:
    """返回所有目标（供API/前端查询）。"""
    return sorted(_goals.values(), key=lambda g: g.get("created_at", 0), reverse=True)


def _broadcast(event: str, goal: dict):
    """通过 WebSocket 广播目标更新到所有连接（最佳努力）。"""
    ch = _ws_channel
    if not ch:
        return
    msg = json.dumps({"type": "goal_update", "event": event, "goal": goal}, default=str)
    try:
        loop = asyncio.get_running_loop()
        for ws in list(getattr(ch, '_connections', {}).values()):
            loop.create_task(_safe_send(ws, msg))
    except RuntimeError:
        pass


async def _safe_send(ws, msg: str):
    """安全发送 WebSocket 消息。"""
    try:
        await ws.send_text(msg)
    except Exception:
        pass
