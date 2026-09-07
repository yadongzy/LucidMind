"""任务调度器 — OODA闭环的核心引擎。核心队列操作（入队/出队/状态流转）。

工具函数（清理/淘汰/间隔/状态查询）在 task_dispatcher_utils.py。
"""
import uuid
from datetime import datetime
from typing import Optional

from logs import get_logger
from task_model import Checkpoint, FailureReason, TaskStatus, transition
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
    idempotency_key: Optional[str] = None,
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

    # 显式幂等键优先；旧调用方继续使用内容去重，保持迁移兼容。
    content_key = content[:200]
    for t in tasks:
        same_explicit_key = (
            idempotency_key is not None
            and t.get("idempotency_key") == idempotency_key
        )
        same_legacy_content = (
            idempotency_key is None
            and t["status"] == "ready"
            and t["content"][:200] == content_key
        )
        if same_explicit_key or same_legacy_content:
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
        "version": 0,
        "idempotency_key": idempotency_key,
        "lease_owner": None,
        "lease_expires_at": None,
        "attempts": [],
        "checkpoints": [],
        "failure_reason": None,
        "cancel_requested": False,
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
# _PRIORITY_ORDER 统一从 task_dispatcher_utils 导入（此处不再重复定义）


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
    transition(chosen, TaskStatus.RUNNING)
    chosen["running_at"] = datetime.now().isoformat()
    _save_store(store)
    logger.info(f"🎯 出队: {chosen['id']} priority={chosen['priority']} content={chosen['content'][:40]}")
    return chosen


# ═══════════════════════════════════════════════
# 状态流转
# ═══════════════════════════════════════════════

def update_task_progress(task_id: str, progress: str):
    """推送任务执行中间状态（对标 OpenClaw onAgentEvent 实时推送）。"""
    store = _load_store()
    for t in store["tasks"]:
        if t["id"] == task_id:
            t["progress"] = progress[:200]
            transition(t, TaskStatus.RUNNING)
            if not t.get("running_at"):
                t["running_at"] = datetime.now().isoformat()
            _save_store(store)
            _notify("task_progress", t)
            return
    logger.debug(f"⚠️ 更新进度失败: 任务 {task_id} 不存在")


def write_checkpoint(
    task_id: str,
    name: str,
    payload: Optional[dict] = None,
) -> Optional:
    """在阶段边界原子追加检查点，并返回序列化结果。"""
    if not name or not name.strip():
        raise ValueError("检查点名称不能为空")
    store = _load_store()
    for task in store.get("tasks", []):
        if task["id"] != task_id:
            continue
        checkpoint = Checkpoint(
            name=name.strip(),
            created_at=datetime.now().isoformat(),
            payload=payload or {},
        ).to_dict()
        task.setdefault("checkpoints", []).append(checkpoint)
        task["updated_at"] = checkpoint["created_at"]
        _save_store(store)
        _notify("task_checkpoint", task)
        return checkpoint
    return None


def latest_checkpoint(task_id: str) -> Optional:
    """读取最后一个有效检查点，不修改持久化状态。"""
    store = _load_store()
    for task in store.get("tasks", []):
        if task["id"] == task_id:
            checkpoints = task.get("checkpoints") or []
            return dict(checkpoints[-1]) if checkpoints else None
    return None


def recover_orphaned_tasks(*, enable_recovery: bool = False) -> list:
    """扫描失效租约的 running 任务；默认只报告，显式开启后才恢复。

    有检查点的任务回到 ready 等待新 attempt；无检查点的任务进入 blocked，
    避免未知外部副作用被自动重复执行。
    """
    store = _load_store()
    now = datetime.now()
    findings = []
    changed = False
    for task in store.get("tasks", []):
        if task.get("status") != TaskStatus.RUNNING.value:
            continue
        expires_at = task.get("lease_expires_at")
        lease_expired = not expires_at
        if expires_at:
            try:
                lease_expired = datetime.fromisoformat(expires_at) <= now
            except (TypeError, ValueError):
                lease_expired = True
        if not lease_expired:
            continue
        has_checkpoint = bool(task.get("checkpoints"))
        action = "resume" if has_checkpoint else "manual_review"
        findings.append({"task_id": task["id"], "action": action})
        if not enable_recovery:
            continue
        transition(task, TaskStatus.READY if has_checkpoint else TaskStatus.BLOCKED)
        task["running_at"] = None
        task["lease_owner"] = None
        task["lease_expires_at"] = None
        task["failure_reason"] = FailureReason.SYSTEM_INTERRUPTED.value
        task["last_error"] = (
            "检测到孤儿任务，已从最后检查点等待恢复"
            if has_checkpoint
            else "检测到孤儿任务且无检查点，需要人工确认副作用"
        )
        changed = True
    if changed:
        _save_store(store)
    return findings


def is_cancel_requested(task_id: str) -> bool:
    """读取协作式取消标记；任务不存在时按未取消处理。"""
    store = _load_store()
    return any(
        t["id"] == task_id and bool(t.get("cancel_requested"))
        for t in store.get("tasks", [])
    )


def request_task_cancel(task_id: str) -> bool:
    """请求在下一个安全点取消任务，不强杀正在进行的外部副作用。"""
    store = _load_store()
    for t in store.get("tasks", []):
        if t["id"] != task_id:
            continue
        if t["status"] in ("completed", "failed", "escalated", "cancelled"):
            return False
        t["cancel_requested"] = True
        t["updated_at"] = datetime.now().isoformat()
        _save_store(store)
        _notify("task_cancel_requested", t)
        return True
    return False


def cancel_task(task_id: str, reason: str = "任务已取消") -> bool:
    """在执行安全点落盘最终取消状态。"""
    store = _load_store()
    for t in store.get("tasks", []):
        if t["id"] != task_id:
            continue
        if t["status"] == "cancelled":
            return True
        transition(t, TaskStatus.CANCELLED)
        t["running_at"] = None
        t["completed_at"] = datetime.now().isoformat()
        t["failure_reason"] = "cancelled"
        t["last_error"] = reason[:200]
        _save_store(store)
        _notify("task_cancelled", t)
        return True
    return False


def complete_task(task_id: str):
    """标记任务完成。"""
    store = _load_store()
    for t in store["tasks"]:
        if t["id"] == task_id:
            transition(t, TaskStatus.COMPLETED)
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
                transition(t, TaskStatus.ESCALATED)
                logger.warning(f"🆘 上报: {task_id} retries={t['retries']} error={error[:60]}")
                _notify_escalation(t)
                _notify("task_escalated", t)
                # 子任务escalated后也需检查父任务是否可恢复
                if t.get("parent_id"):
                    _resume_parent(store, t["parent_id"])
            else:
                transition(t, TaskStatus.READY)
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
            transition(t, TaskStatus.BLOCKED)
            t["running_at"] = None
            t["last_error"] = reason[:200]
            logger.info(f"🚫 阻塞: {task_id} reason={reason[:60]}")
            _notify("task_blocked", t)
            break
    _save_store(store)


def _resume_parent(store: dict, parent_id: str):
    """检查所有子任务是否完成，全部完成后聚合结果并恢复父任务。"""
    # 找到所有子任务
    siblings = [t for t in store["tasks"] if t.get("parent_id") == parent_id]
    if not siblings:
        # 无子任务，直接恢复
        for t in store["tasks"]:
            if t["id"] == parent_id and t["status"] == "blocked":
                transition(t, TaskStatus.READY)
                t["running_at"] = None
                logger.info(f"♻️ 恢复父任务: {parent_id}")
        return

    # 检查是否所有子任务都已结束（completed/failed/escalated）
    done_statuses = {"completed", "failed", "escalated"}
    all_done = all(s["status"] in done_statuses for s in siblings)
    if not all_done:
        pending = [s for s in siblings if s["status"] not in done_statuses]
        logger.debug(f"⏳ 父任务 {parent_id} 还有 {len(pending)} 个子任务未完成")
        return

    # 所有子任务已完成 — 聚合结果
    completed = [s for s in siblings if s["status"] == "completed"]
    failed = [s for s in siblings if s["status"] in ("failed", "escalated")]
    summary = f"子任务完成: {len(completed)}/{len(siblings)}成功"
    if failed:
        fail_msgs = "; ".join(f"{s['content'][:30]}:{s.get('last_error','')[:30]}" for s in failed[:3])
        summary += f", {len(failed)}失败[{fail_msgs}]"

    for t in store["tasks"]:
        if t["id"] == parent_id and t["status"] == "blocked":
            if failed:
                # 有子任务失败 — 父任务标记失败
                transition(
                    t,
                    TaskStatus.FAILED
                    if len(failed) == len(siblings)
                    else TaskStatus.READY,
                )
                t["last_error"] = summary[:200]
            else:
                # 全部成功 — 父任务标记完成
                transition(t, TaskStatus.COMPLETED)
                t["completed_at"] = datetime.now().isoformat()
            t["running_at"] = None
            t["progress"] = summary[:200]
            logger.info(f"🔀 父任务聚合: {parent_id} — {summary}")


def _overflow_to_memo(store: dict):
    """队列溢出时，最低优先级移入备忘录。"""
    from task_dispatcher_utils import MAX_MEMO
    tasks = store.get("tasks", [])
    active = [t for t in tasks if t["status"] not in ("completed", "failed", "escalated")]
    active.sort(key=lambda t: _PRIORITY_ORDER.get(t["priority"], 99), reverse=True)
    memo = store.setdefault("memo", [])
    while len(active) > MAX_TASK_QUEUE - 5:
        overflow = active.pop(0)
        transition(overflow, TaskStatus.MEMO)
        memo.append(overflow)
        tasks.remove(overflow)
        logger.info(f"📦 溢出到备忘录: {overflow['id']} priority={overflow['priority']}")
    if len(memo) > MAX_MEMO:
        removed = len(memo) - MAX_MEMO
        store["memo"] = memo[-MAX_MEMO:]
        logger.info(f"🗑️ 备忘录清理: 删除{removed}条最旧记录")
