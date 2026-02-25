"""任务调度器 — OODA闭环的核心引擎。核心队列操作（入队/出队/状态流转）。

工具函数（清理/淘汰/间隔/状态查询）在 task_dispatcher_utils.py。
"""
import uuid
from datetime import datetime
from typing import Optional

from logs import get_logger
from task_dispatcher_utils import (
    load_store as _load_store, save_store as _save_store,
    load_store, save_store,
    MAX_TASK_QUEUE, _PRIORITY_ORDER,
    release_stuck_tasks, compute_interval, cleanup_completed,
    auto_expire, get_queue_status, get_daily_state,
    set_daily_check_done, is_daily_check_done,
    set_monthly_check_done, is_monthly_check_done,
)

logger = get_logger("dispatcher")

# ═══════════════════════════════════════════════
# 通知钩子：外部订阅任务变更事件
# ═══════════════════════════════════════════════
_notify_hooks: list = []

def register_notify_hook(hook):
    """注册任务变更通知回调。hook(event: str, task: dict)"""
    _notify_hooks.append(hook)

def _notify(event: str, task: dict):
    """触发所有已注册的通知钩子。"""
    for hook in _notify_hooks:
        try:
            hook(event, task)
        except Exception as e:
            logger.debug(f"通知钩子异常: {e}")


# ═══════════════════════════════════════════════
# 入队：信息分类（三层闸门第1层）
# ═══════════════════════════════════════════════

def enqueue(
    content: str,
    task_type: str = "task",
    priority: str = "P2",
    source: str = "system",
    parent_id: Optional[str] = None,
    timeout_s: int = 120,
    max_retries: int = 3,
) -> dict:
    """将一个任务/学习项入队。

    Args:
        content: 任务描述
        task_type: "task" / "learn" / "memo"
        priority: P0-P3（任务）/ L0-L3（学习）
        source: "user" / "teacher" / "self_check" / "engine" / "task_driven"
        parent_id: L0学习子任务指向父任务ID
        timeout_s: 超时秒数
        max_retries: 最大重试次数
    Returns:
        创建的任务字典
    """
    store = _load_store()
    tasks = store.get("tasks", [])

    # 去重：相同内容的ready任务不重复入队（防积压）
    content_key = content[:200]
    for t in tasks:
        if t["status"] == "ready" and t["content"][:200] == content_key:
            logger.debug(f"⏭️ 跳过重复入队: {content_key[:40]}")
            return t

    # 队列上限检查
    active = [t for t in tasks if t["status"] not in ("completed", "failed", "escalated")]
    if len(active) >= MAX_TASK_QUEUE:
        # 溢出：最低优先级移入备忘录
        _overflow_to_memo(store)

    task = {
        "id": str(uuid.uuid4())[:8],
        "type": task_type,
        "priority": priority,
        "source": source,
        "content": content[:500],
        "status": "ready",
        "parent_id": parent_id,
        "created_at": datetime.now().isoformat(),
        "running_at": None,
        "completed_at": None,
        "retries": 0,
        "max_retries": max_retries,
        "last_error": None,
        "timeout_s": timeout_s,
    }

    tasks.append(task)
    store["tasks"] = tasks
    _save_store(store)
    logger.info(f"📥 入队: {task['id']} type={task_type} priority={priority} source={source}")
    _notify("task_created", task)
    return task


def enqueue_from_teacher(content: str) -> dict:
    """老师消息入队（P1教学优先）。"""
    return enqueue(content, task_type="task", priority="P1", source="teacher")


def enqueue_from_user(content: str) -> dict:
    """用户消息入队（P1用户任务）。"""
    return enqueue(content, task_type="task", priority="P1", source="user")


def enqueue_self_check_issue(desc: str, severity: str) -> dict:
    """自检问题入队。"""
    p = "P0" if severity in ("fatal", "severe") else "P3"
    return enqueue(desc, task_type="task", priority=p, source="self_check")


def enqueue_learning(content: str, priority: str = "L2",
                     source: str = "engine", parent_id: Optional[str] = None) -> dict:
    """学习任务入队。"""
    return enqueue(content, task_type="learn", priority=priority,
                   source=source, parent_id=parent_id, timeout_s=180)


# ═══════════════════════════════════════════════
# 出队：取最高优先级任务
# ═══════════════════════════════════════════════

_PRIORITY_ORDER = {
    "P0": 0, "P1": 1, "P2": 2, "P3": 3,
    "L0": 4, "L1": 5, "L2": 6, "L3": 7,
}


def dequeue() -> Optional[dict]:
    """取出最高优先级的ready任务，标记为running。

    任务队列永远优先于学习队列（P < L）。
    Returns:
        任务字典，或None（队列为空）
    """
    store = _load_store()
    tasks = store.get("tasks", [])

    ready = [t for t in tasks if t["status"] == "ready"]
    if not ready:
        return None

    # 按优先级排序，同优先级按创建时间
    ready.sort(key=lambda t: (
        _PRIORITY_ORDER.get(t["priority"], 99),
        t["created_at"]
    ))

    chosen = ready[0]
    chosen["status"] = "running"
    chosen["running_at"] = datetime.now().isoformat()
    _save_store(store)
    logger.info(f"🎯 出队: {chosen['id']} priority={chosen['priority']} content={chosen['content'][:40]}")
    return chosen


# ═══════════════════════════════════════════════
# 状态流转
# ═══════════════════════════════════════════════

def complete_task(task_id: str):
    """标记任务完成。"""
    store = _load_store()
    for t in store["tasks"]:
        if t["id"] == task_id:
            t["status"] = "completed"
            t["completed_at"] = datetime.now().isoformat()
            t["running_at"] = None
            logger.info(f"✅ 完成: {task_id}")
            # 如果有父任务，恢复父任务
            if t.get("parent_id"):
                _resume_parent(store, t["parent_id"])
            _notify("task_completed", t)
            break
    _save_store(store)


def fail_task(task_id: str, error: str):
    """标记任务失败，自动重试或上报。"""
    store = _load_store()
    for t in store["tasks"]:
        if t["id"] == task_id:
            t["retries"] = t.get("retries", 0) + 1
            t["last_error"] = error[:200]
            t["running_at"] = None
            if t["retries"] >= t.get("max_retries", 3):
                t["status"] = "escalated"
                logger.warning(f"🆘 上报: {task_id} retries={t['retries']} error={error[:60]}")
                _notify_escalation(t)
                _notify("task_escalated", t)
            else:
                t["status"] = "ready"
                logger.info(f"🔄 重试: {task_id} retries={t['retries']} error={error[:60]}")
                _notify("task_retried", t)
            break
    _save_store(store)


def _notify_escalation(task: dict):
    """上报已耗尽重试的任务给老师/用户（任务逻辑.md §七.1）。"""
    try:
        from teacher_channel import TeacherChannel
        from api.brain_init import teacher
        teacher.send_to_teacher(
            msg_type="help",
            content=f"任务上报: {task['content'][:150]}",
            context=f"重试{task.get('retries',0)}次仍失败。错误: {task.get('last_error','')[:100]}",
            urgency="high",
        )
        logger.info(f"📨 已上报老师: {task['id']}")
    except Exception as e:
        logger.debug(f"上报老师失败(可能未初始化): {e}")


def block_task(task_id: str, reason: str):
    """标记任务阻塞（触发任务驱动学习）。"""
    store = _load_store()
    for t in store["tasks"]:
        if t["id"] == task_id:
            t["status"] = "blocked"
            t["running_at"] = None
            t["last_error"] = reason[:200]
            logger.info(f"🚫 阻塞: {task_id} reason={reason[:60]}")
            _notify("task_blocked", t)
            break
    _save_store(store)


def _resume_parent(store: dict, parent_id: str):
    """恢复被阻塞的父任务。"""
    for t in store["tasks"]:
        if t["id"] == parent_id and t["status"] == "blocked":
            t["status"] = "ready"
            t["running_at"] = None
            logger.info(f"♻️ 恢复父任务: {parent_id}")


def _overflow_to_memo(store: dict):
    """队列溢出时，最低优先级移入备忘录。"""
    from task_dispatcher_utils import MAX_MEMO
    tasks = store.get("tasks", [])
    active = [t for t in tasks if t["status"] not in ("completed", "failed", "escalated")]
    active.sort(key=lambda t: _PRIORITY_ORDER.get(t["priority"], 99), reverse=True)
    memo = store.setdefault("memo", [])
    while len(active) > MAX_TASK_QUEUE - 5:
        overflow = active.pop(0)
        overflow["status"] = "memo"
        memo.append(overflow)
        tasks.remove(overflow)
        logger.info(f"📦 溢出到备忘录: {overflow['id']} priority={overflow['priority']}")
    if len(memo) > MAX_MEMO:
        removed = len(memo) - MAX_MEMO
        store["memo"] = memo[-MAX_MEMO:]
        logger.info(f"🗑️ 备忘录清理: 删除{removed}条最旧记录")
