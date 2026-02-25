"""异步任务队列 — 后台执行长任务，前端查询状态。"""

import asyncio
import time
import uuid
from typing import Any

from fastapi import APIRouter
from logs import get_logger

logger = get_logger("tasks")

router = APIRouter()

# 任务存储（内存，重启后丢失，足够用）
_tasks: dict[str, dict[str, Any]] = {}
_queue: asyncio.Queue | None = None
_worker_started = False


def _ensure_worker():
    """确保后台 worker 已启动。"""
    global _queue, _worker_started
    if _queue is None:
        _queue = asyncio.Queue()
    if not _worker_started:
        _worker_started = True
        asyncio.get_event_loop().create_task(_worker_loop())


async def _worker_loop():
    """后台 worker：从队列取任务并执行。"""
    while True:
        task_id, coro = await _queue.get()
        task = _tasks.get(task_id)
        if not task:
            continue
        task["status"] = "running"
        task["started_at"] = time.time()
        logger.info(f"任务开始: {task_id} — {task['description']}")
        try:
            result = await coro
            task["status"] = "done"
            task["result"] = result
            logger.info(f"任务完成: {task_id}")
        except Exception as e:
            task["status"] = "failed"
            task["error"] = str(e)
            logger.error(f"任务失败: {task_id} — {e}")
        finally:
            task["finished_at"] = time.time()
            _queue.task_done()


async def submit_task(description: str, coro) -> str:
    """提交一个异步任务到队列。返回 task_id。"""
    _ensure_worker()
    task_id = uuid.uuid4().hex[:10]
    _tasks[task_id] = {
        "id": task_id,
        "description": description,
        "status": "pending",
        "created_at": time.time(),
        "started_at": None,
        "finished_at": None,
        "result": None,
        "error": None,
    }
    await _queue.put((task_id, coro))
    logger.info(f"任务入队: {task_id} — {description}")
    return task_id


@router.get("/api/tasks")
async def list_tasks():
    """列出所有任务。"""
    tasks = sorted(_tasks.values(), key=lambda t: t["created_at"], reverse=True)
    return {"tasks": tasks[:20], "total": len(_tasks)}


@router.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    """查询单个任务状态。"""
    task = _tasks.get(task_id)
    if not task:
        return {"error": "Task not found"}
    return task
